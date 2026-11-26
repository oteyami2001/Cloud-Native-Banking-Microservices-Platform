#!/usr/bin/env bash
# Read-only: explain why a GitHub Actions OIDC role assumption was refused.
# Shows the existing provider's audiences and the subject (sub) claim GitHub
# actually sent, from CloudTrail, next to what the role trusts.
set -uo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-us-east-2}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
ROLE="${1:-novabank-github-plan}"
PROVIDER="arn:aws:iam::${ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"

echo "## OIDC provider audiences (must include sts.amazonaws.com)"
aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$PROVIDER" \
  --query '{Url:Url,ClientIDList:ClientIDList}' --output json

echo; echo "## Subjects trusted by $ROLE"
aws iam get-role --role-name "$ROLE" --query 'Role.AssumeRolePolicyDocument.Statement[].Condition' --output json

echo; echo "## Recent AssumeRoleWithWebIdentity attempts (CloudTrail, $REGION and us-east-1)"
for r in "$REGION" us-east-1; do
  aws cloudtrail lookup-events --region "$r" --max-results 20 \
    --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
    --query 'Events[].CloudTrailEvent' --output json 2>/dev/null |
  python3 -c '
import json, sys
for raw in json.load(sys.stdin) or []:
    e = json.loads(raw)
    ui = e.get("userIdentity", {})
    rp = e.get("requestParameters") or {}
    print(e.get("eventTime"), e.get("awsRegion"), "| role:", (rp.get("roleArn") or "").split("/")[-1],
          "| sub:", ui.get("userName"), "| error:", e.get("errorCode"), e.get("errorMessage") or "")
'
done
