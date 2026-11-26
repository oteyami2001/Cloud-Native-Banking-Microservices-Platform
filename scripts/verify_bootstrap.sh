#!/usr/bin/env bash
# Read-only verification that bootstrap resources exist and are hardened.
set -euo pipefail
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGION="${1:-${AWS_REGION:-us-east-2}}"
fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi; }
for b in "novabank-tfstate-$ACCOUNT-$REGION" "novabank-artifacts-$ACCOUNT-$REGION"; do
  check "$b exists" "aws s3api head-bucket --bucket $b"
  check "$b versioning" "aws s3api get-bucket-versioning --bucket $b --query Status --output text | grep -q Enabled"
  check "$b encryption" "aws s3api get-bucket-encryption --bucket $b"
  check "$b public access blocked" "aws s3api get-public-access-block --bucket $b --query 'PublicAccessBlockConfiguration.RestrictPublicBuckets' --output text | grep -q True"
done
for r in plan apply deploy cleanup; do
  check "role novabank-github-$r" "aws iam get-role --role-name novabank-github-$r"
done
exit $fail
