#!/usr/bin/env bash
# Verify that no project-owned resources remain after cleanup (T30).
# Read-only. Prints a Markdown report; exits non-zero if anything remains.
set -uo pipefail
PREFIX="${1:-novabank-dev}"
REGION="${AWS_REGION:-us-east-2}"
export AWS_PAGER=""
remaining=0
unchecked=""
report() {
  local label="$1"; shift
  local raw
  # A failed call (for example AccessDenied) must not be reported as "none".
  if ! raw="$("$@" 2>/dev/null)"; then echo "- ${label}: NOT CHECKED (the AWS call failed; check by hand)"; unchecked="${unchecked}${label}; "; return; fi
  local out; out="$(echo "$raw" | tr '\t' '\n' | grep -E "${PREFIX}" || true)"
  if [ -n "$out" ]; then echo "- **${label}: REMAINING** — $(echo "$out" | tr '\n' ' ')"; remaining=1; else echo "- ${label}: none"; fi
}
echo "## Cleanup verification for \`${PREFIX}\` in ${REGION}"
report "Lambda functions" aws lambda list-functions --region "$REGION" --query "Functions[].FunctionName" --output text
report "DynamoDB tables" aws dynamodb list-tables --region "$REGION" --query "TableNames" --output text
report "SQS queues" aws sqs list-queues --region "$REGION" --queue-name-prefix "$PREFIX" --query "QueueUrls" --output text
report "Event buses" aws events list-event-buses --region "$REGION" --query "EventBuses[].Name" --output text
report "HTTP APIs" aws apigatewayv2 get-apis --region "$REGION" --query "Items[].Name" --output text
report "Cognito pools" aws cognito-idp list-user-pools --max-results 60 --region "$REGION" --query "UserPools[].Name" --output text
report "S3 buckets" aws s3api list-buckets --query "Buckets[].Name" --output text
report "Log groups" aws logs describe-log-groups --region "$REGION" --log-group-name-prefix "/aws/lambda/${PREFIX}" --query "logGroups[].logGroupName" --output text
report "IAM roles" aws iam list-roles --query "Roles[].RoleName" --output text
report "Budgets" aws budgets describe-budgets --account-id "$(aws sts get-caller-identity --query Account --output text)" --query "Budgets[].BudgetName" --output text
report "Tagged resources" aws resourcegroupstaggingapi get-resources --region "$REGION" --tag-filters "Key=Environment,Values=${PREFIX#novabank-}" "Key=Project,Values=Cloud-Native-Banking-Microservices-Platform" --query "ResourceTagMappingList[].ResourceARN" --output text
echo
if [ "$remaining" = "0" ] && [ -n "$unchecked" ]; then echo "**Result: nothing remains in the checks that ran. Not checked: ${unchecked}**"; elif [ "$remaining" = "0" ]; then echo "**Result: no project-owned resources remain.**"; else echo "**Result: resources remain — investigate before closing T30.**"; fi
echo "_DynamoDB PITR backups and CloudWatch metrics age out automatically; the bootstrap state bucket and GitHub roles are intentionally retained._"
exit $remaining
