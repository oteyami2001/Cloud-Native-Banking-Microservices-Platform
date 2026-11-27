#!/usr/bin/env bash
# Rebuild and deploy the whole NovaBank Digital dev environment from AWS CloudShell.
#
# What it does, in order (each step that changes AWS asks you to type "yes" first):
#   0. Checks the account and region, installs Terraform, Python 3.11 deps and Node 22 into /tmp
#   1. Bootstrap: state bucket, artifact bucket, GitHub OIDC roles (terraform/bootstrap)
#   2. Dev infrastructure: ~182 resources (terraform/envs/dev), plan shown before apply
#   3. Seeds the synthetic funding account GL-1000 (idempotent)
#   4. Builds the 10 Lambda packages and deploys them with health check + automatic rollback
#   5. Builds the React frontend in Cognito mode, uploads it, invalidates CloudFront
#   6. Optionally creates a customer and a fraud-reviewer user in Cognito
#   7. Runs a smoke test and prints the URLs and the GitHub variables to update
#
# Safe to re-run: Terraform only changes what differs, seeding and user creation skip
# what already exists, and a re-deploy just publishes new Lambda versions.
#
# Usage (in CloudShell):
#   bash rebuild_from_cloudshell.sh            # clones the repository into /tmp and runs
#   bash scripts/rebuild_from_cloudshell.sh    # or run it from inside a clone
#
# Everything is installed under /tmp because the CloudShell home directory is only 1 GB.
# Synthetic data only. Never put real personal or financial data into this sandbox.

set -euo pipefail

REGION="${REGION:-us-east-2}"
EXPECTED_ACCOUNT="${EXPECTED_ACCOUNT:-666102401492}"
REPO_URL="${REPO_URL:-https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform.git}"
BRANCH="${BRANCH:-main}"
TF_VERSION="1.13.4"
NODE_VERSION="22.12.0"
WORK="/tmp/novabank-rebuild"
NAME_PREFIX="novabank-dev"

export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"
export TF_PLUGIN_CACHE_DIR="$WORK/tf-plugin-cache"
export TF_IN_AUTOMATION=1

bold() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
die() { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
confirm() {
  local answer
  printf '\n\033[33m%s\033[0m\nType "yes" to continue, anything else to stop: ' "$1"
  read -r answer
  [ "$answer" = "yes" ] || die "Stopped by user. Nothing further was changed."
}

# ---------------------------------------------------------------- 0. Pre-flight
bold "0. Pre-flight checks"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text) || die "AWS credentials not available. Run this in AWS CloudShell."
info "Account: $ACCOUNT   Region: $REGION"
[ "$ACCOUNT" = "$EXPECTED_ACCOUNT" ] || die "This script is pinned to account $EXPECTED_ACCOUNT but you are in $ACCOUNT. Set EXPECTED_ACCOUNT=$ACCOUNT to override deliberately."

STATE_BUCKET="novabank-tfstate-${ACCOUNT}-${REGION}"
ARTIFACT_BUCKET="novabank-artifacts-${ACCOUNT}-${REGION}"

mkdir -p "$WORK/bin" "$TF_PLUGIN_CACHE_DIR"
export PATH="$WORK/bin:$WORK/node/bin:$PATH"

# Repository: use the current clone if we are inside one, otherwise clone into /tmp.
if git rev-parse --show-toplevel >/dev/null 2>&1 && [ -f "$(git rev-parse --show-toplevel)/terraform/bootstrap/main.tf" ]; then
  SRC_REPO="$(git rev-parse --show-toplevel)"
  info "Using repository at $SRC_REPO"
else
  SRC_REPO="$WORK/repo"
  if [ -d "$SRC_REPO/.git" ]; then
    git -C "$SRC_REPO" fetch -q origin "$BRANCH" && git -C "$SRC_REPO" checkout -q --detach FETCH_HEAD
  else
    git clone -q --branch "$BRANCH" "$REPO_URL" "$SRC_REPO"
  fi
  info "Cloned $REPO_URL ($BRANCH) into $SRC_REPO"
fi
cd "$SRC_REPO"
COMMIT=$(git rev-parse HEAD)
info "Commit: $COMMIT"

# Terraform
if ! terraform version 2>/dev/null | grep -q "v${TF_VERSION}"; then
  info "Installing Terraform $TF_VERSION"
  arch=$(uname -m); case "$arch" in x86_64) tfarch=amd64 ;; aarch64) tfarch=arm64 ;; *) die "Unsupported CPU $arch" ;; esac
  curl -fsSLo "$WORK/terraform.zip" "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_${tfarch}.zip"
  python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extract('terraform', sys.argv[2])" "$WORK/terraform.zip" "$WORK/bin"
  chmod +x "$WORK/bin/terraform"
fi
info "$(terraform version | head -1)"

# Python 3.11 with boto3 and PyYAML (CloudShell's default python3 is too old for the code)
if ! command -v python3.11 >/dev/null; then
  info "Installing Python 3.11"
  sudo dnf install -y -q python3.11 python3.11-pip >/dev/null
fi
python3.11 -m pip --version >/dev/null 2>&1 || sudo dnf install -y -q python3.11-pip >/dev/null
if ! PYTHONPATH="$WORK/pydeps" python3.11 -c "import boto3, yaml" 2>/dev/null; then
  info "Installing boto3 and PyYAML into $WORK/pydeps"
  python3.11 -m pip install -q --target "$WORK/pydeps" boto3==1.44.12 PyYAML
fi
export PYTHONPATH="$WORK/pydeps"
info "$(python3.11 --version), boto3 $(python3.11 -c 'import boto3; print(boto3.__version__)')"

# Node 22 (Vite 7 needs a recent Node)
if ! node --version 2>/dev/null | grep -q '^v22\.'; then
  info "Installing Node $NODE_VERSION"
  arch=$(uname -m); case "$arch" in x86_64) narch=x64 ;; aarch64) narch=arm64 ;; *) die "Unsupported CPU $arch" ;; esac
  curl -fsSLo "$WORK/node.tar.xz" "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${narch}.tar.xz"
  rm -rf "$WORK/node" && mkdir -p "$WORK/node"
  tar -xJf "$WORK/node.tar.xz" -C "$WORK/node" --strip-components=1
fi
info "Node $(node --version), npm $(npm --version)"

# ---------------------------------------------------------------- 1. Bootstrap
bold "1. Bootstrap (state bucket, artifact bucket, GitHub OIDC roles)"
OIDC_ARN=$(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?ends_with(Arn, 'token.actions.githubusercontent.com')].Arn | [0]" --output text)
[ "$OIDC_ARN" = "None" ] && OIDC_ARN=""
info "Existing GitHub OIDC provider: ${OIDC_ARN:-none (Terraform will create one)}"

export TF_DATA_DIR="$WORK/tfdata-bootstrap"
BOOT_DIR="$SRC_REPO/terraform/bootstrap"
if aws s3api head-bucket --bucket "$STATE_BUCKET" 2>/dev/null; then
  info "State bucket $STATE_BUCKET already exists"
  if [ ! -f "$BOOT_DIR/terraform.tfstate" ]; then
    if aws s3api head-object --bucket "$STATE_BUCKET" --key novabank/bootstrap/terraform.tfstate >/dev/null 2>&1; then
      aws s3 cp --only-show-errors "s3://$STATE_BUCKET/novabank/bootstrap/terraform.tfstate" "$BOOT_DIR/terraform.tfstate"
      info "Restored bootstrap state from s3://$STATE_BUCKET/novabank/bootstrap/terraform.tfstate"
    else
      die "The bootstrap resources exist but their Terraform state backup is missing. Do not re-create them; restore terraform/bootstrap/terraform.tfstate first."
    fi
  fi
fi

BOOT_VARS=(-var "expected_account_id=$ACCOUNT" -var "region=$REGION")
[ -n "$OIDC_ARN" ] && BOOT_VARS+=(-var "existing_oidc_provider_arn=$OIDC_ARN")
terraform -chdir="$BOOT_DIR" init -input=false -upgrade=false >/dev/null
set +e
terraform -chdir="$BOOT_DIR" plan -input=false -detailed-exitcode -out="$WORK/bootstrap.tfplan" "${BOOT_VARS[@]}" > "$WORK/bootstrap-plan.txt"
rc=$?
set -e
[ $rc -eq 1 ] && { cat "$WORK/bootstrap-plan.txt"; die "Bootstrap plan failed."; }
grep -E "^Plan:|No changes" "$WORK/bootstrap-plan.txt" | sed 's/^/  /'
if [ $rc -eq 2 ]; then
  info "Full plan: $WORK/bootstrap-plan.txt"
  confirm "Apply the bootstrap plan above to account $ACCOUNT?"
  terraform -chdir="$BOOT_DIR" apply -input=false "$WORK/bootstrap.tfplan"
  aws s3 cp --only-show-errors --sse aws:kms "$BOOT_DIR/terraform.tfstate" "s3://$STATE_BUCKET/novabank/bootstrap/terraform.tfstate"
  info "Bootstrap state backed up to S3"
fi

# ---------------------------------------------------------------- 2. Dev infrastructure
bold "2. Dev infrastructure (terraform/envs/dev)"
export TF_DATA_DIR="$WORK/tfdata-dev"
DEV_DIR="$SRC_REPO/terraform/envs/dev"
DEV_VARS=(-var "expected_account_id=$ACCOUNT" -var "region=$REGION" -var "evidence_force_destroy=true")
terraform -chdir="$DEV_DIR" init -input=false -lockfile=readonly \
  -backend-config="bucket=$STATE_BUCKET" -backend-config="region=$REGION" >/dev/null
set +e
terraform -chdir="$DEV_DIR" plan -input=false -lock-timeout=5m -detailed-exitcode -out="$WORK/dev.tfplan" "${DEV_VARS[@]}" > "$WORK/dev-plan.txt"
rc=$?
set -e
[ $rc -eq 1 ] && { tail -40 "$WORK/dev-plan.txt"; die "Dev plan failed."; }
grep -E "^Plan:|No changes" "$WORK/dev-plan.txt" | sed 's/^/  /'
if [ $rc -eq 2 ]; then
  info "Full plan: $WORK/dev-plan.txt  (read it with: less $WORK/dev-plan.txt)"
  confirm "Apply the dev plan above? A first build creates about 182 resources and takes 10-20 minutes (CloudFront is the slowest)."
  terraform -chdir="$DEV_DIR" apply -input=false -lock-timeout=5m "$WORK/dev.tfplan"
fi

terraform -chdir="$DEV_DIR" output -json platform > "$WORK/platform.json"
out() { python3.11 -c "import json,sys; d=json.load(open(sys.argv[1])); v=d; [v:=v[k] for k in sys.argv[2:]]; print(v)" "$WORK/platform.json" "$@"; }
API_URL=$(out api_endpoint)
SITE_URL=$(out site_url)
COGNITO_DOMAIN=$(out cognito_domain)
CLIENT_ID=$(out spa_client_id)
USER_POOL_ID=$(out user_pool_id)
FRONTEND_BUCKET=$(out frontend_bucket)
DISTRIBUTION_ID=$(out frontend_distribution_id)
LEDGER_TABLE=$(out table_names ledger)
IDEMPOTENCY_TABLE=$(out table_names idempotency)
info "API: $API_URL"
info "Site: $SITE_URL"

# ---------------------------------------------------------------- 3. Seed GL-1000
bold "3. Seed the synthetic funding account GL-1000"
if aws dynamodb get-item --table-name "$LEDGER_TABLE" --key '{"PK":{"S":"ACCOUNT#GL-1000"},"SK":{"S":"BALANCE"}}' --query 'Item.PK.S' --output text 2>/dev/null | grep -q GL-1000; then
  info "GL-1000 already exists, skipping"
else
  LEDGER_TABLE="$LEDGER_TABLE" IDEMPOTENCY_TABLE="$IDEMPOTENCY_TABLE" python3.11 scripts/seed_demo_data.py
fi

# ---------------------------------------------------------------- 4. Services
bold "4. Build and deploy the 10 Lambda services"
rm -rf "$WORK/dist"
python3.11 scripts/build_lambda.py --out "$WORK/dist" --version "$COMMIT"
python3.11 scripts/verify_artifacts.py "$WORK/dist/manifest.json"
confirm "Deploy the packages above to the $NAME_PREFIX functions? Each deploy waits 2 minutes and rolls back automatically on errors."
NAME_PREFIX="$NAME_PREFIX" ARTIFACT_BUCKET="$ARTIFACT_BUCKET" \
  python3.11 scripts/deploy_lambda.py --manifest "$WORK/dist/manifest.json" --services all

# ---------------------------------------------------------------- 5. Frontend
bold "5. Build and publish the frontend"
rm -rf "$WORK/frontend" && mkdir -p "$WORK/frontend"
tar -C "$SRC_REPO/frontend" --exclude node_modules --exclude dist -cf - . | tar -C "$WORK/frontend" -xf -
(
  cd "$WORK/frontend"
  npm ci --no-audit --no-fund --loglevel=error
  VITE_AUTH_MODE=cognito VITE_API_BASE_URL="$API_URL" VITE_COGNITO_DOMAIN="$COGNITO_DOMAIN" \
    VITE_COGNITO_CLIENT_ID="$CLIENT_ID" VITE_REDIRECT_URI="$SITE_URL/callback" npm run build
)
aws s3 sync --only-show-errors "$WORK/frontend/dist" "s3://$FRONTEND_BUCKET" --delete --cache-control "public,max-age=300"
aws s3 cp --only-show-errors "$WORK/frontend/dist/index.html" "s3://$FRONTEND_BUCKET/index.html" --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/index.html" --query 'Invalidation.Id' --output text >/dev/null
info "Frontend published to s3://$FRONTEND_BUCKET and CloudFront invalidated"

# ---------------------------------------------------------------- 6. Users
bold "6. Sign-in users (optional)"
create_user() { # email group
  local email="$1" group="$2" pw
  if aws cognito-idp admin-get-user --user-pool-id "$USER_POOL_ID" --username "$email" >/dev/null 2>&1; then
    info "$email already exists"
  else
    printf '  Password for %s (min 12 chars, upper, lower, digit, symbol; not shown): ' "$email"
    read -rs pw; echo
    aws cognito-idp admin-create-user --user-pool-id "$USER_POOL_ID" --username "$email" \
      --user-attributes Name=email,Value="$email" Name=email_verified,Value=true --message-action SUPPRESS >/dev/null
    aws cognito-idp admin-set-user-password --user-pool-id "$USER_POOL_ID" --username "$email" --password "$pw" --permanent
    unset pw
    info "Created $email"
  fi
  aws cognito-idp admin-add-user-to-group --user-pool-id "$USER_POOL_ID" --username "$email" --group-name "$group"
  info "$email is in group $group"
}
printf '  Create or check a demo customer and a fraud reviewer now? (yes/no): '
read -r mkusers
if [ "$mkusers" = "yes" ]; then
  printf '  Customer e-mail (one you own, e.g. you+customer@gmail.com): '; read -r cust
  printf '  Reviewer e-mail (must differ, e.g. you+reviewer@gmail.com): '; read -r rev
  [ -n "$cust" ] && create_user "$cust" customers
  [ -n "$rev" ] && create_user "$rev" fraud-reviewers
fi

# ---------------------------------------------------------------- 7. Verify
bold "7. Smoke test"
code=$(curl -s -o /dev/null -w '%{http_code}' "$API_URL/v1/accounts")
info "GET /v1/accounts without a token -> HTTP $code (expected 401)"
code=$(curl -s -o /dev/null -w '%{http_code}' "$SITE_URL/")
info "Website -> HTTP $code (expected 200; a brand-new CloudFront distribution can take a few minutes)"
aws lambda invoke --function-name "${NAME_PREFIX}-ledger-reconciliation:live" \
  --cli-binary-format raw-in-base64-out --payload '{"trigger":"rebuild-check"}' "$WORK/recon.json" >/dev/null
info "Ledger reconciliation: $(python3.11 -c "import json; print(json.load(open('$WORK/recon.json')).get('status'))")"

bold "Done"
cat <<EOF
  Website:        $SITE_URL
  API:            $API_URL
  Cognito domain: $COGNITO_DOMAIN

  If any of these changed (for example after a teardown and rebuild), update the
  repository variables in GitHub (Settings > Secrets and variables > Actions > Variables)
  so the pipelines keep working:
    API_BASE_URL=$API_URL
    COGNITO_DOMAIN=$COGNITO_DOMAIN
    COGNITO_CLIENT_ID=$CLIENT_ID
    SITE_URL=$SITE_URL
    FRONTEND_BUCKET=$FRONTEND_BUCKET
    FRONTEND_DISTRIBUTION_ID=$DISTRIBUTION_ID

  Plans and outputs are in $WORK (cleared when CloudShell restarts).
EOF
