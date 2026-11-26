#!/usr/bin/env bash
# Read-only AWS discovery for Phase 0 (safe to run in AWS CloudShell).
# Makes NO changes: only describe/list/get calls. Output contains account
# identifiers — review and redact before sharing publicly.
set -uo pipefail
REGION="${1:-${AWS_REGION:-us-east-2}}"
export AWS_PAGER=""
section() { printf '\n## %s\n' "$1"; }
run() { echo "\$ $*"; "$@" 2>&1 | head -60 || true; }

section "Identity"
run aws sts get-caller-identity
run aws iam list-account-aliases
section "Organizations (may be denied for member accounts)"
run aws organizations describe-organization
run aws organizations list-policies-for-target --target-id "$(aws sts get-caller-identity --query Account --output text)" --filter SERVICE_CONTROL_POLICY
section "Region: $REGION"
section "GitHub OIDC providers"
run aws iam list-open-id-connect-providers
section "Terraform state candidates"
run aws s3api list-buckets --query "Buckets[?contains(Name, 'tfstate') || contains(Name, 'terraform')].Name"
section "CloudTrail"
run aws cloudtrail describe-trails --region "$REGION"
section "Security services (do not modify)"
run aws guardduty list-detectors --region "$REGION"
run aws securityhub describe-hub --region "$REGION"
run aws configservice describe-configuration-recorders --region "$REGION"
run aws accessanalyzer list-analyzers --region "$REGION"
section "Existing workloads"
run aws lambda list-functions --region "$REGION" --query "Functions[].FunctionName"
run aws apigatewayv2 get-apis --region "$REGION" --query "Items[].{Name:Name,Id:ApiId}"
run aws apigateway get-rest-apis --region "$REGION" --query "items[].name"
run aws cognito-idp list-user-pools --max-results 20 --region "$REGION" --query "UserPools[].Name"
run aws dynamodb list-tables --region "$REGION"
run aws events list-event-buses --region "$REGION" --query "EventBuses[].Name"
run aws sqs list-queues --region "$REGION"
run aws cloudfront list-distributions --query "DistributionList.Items[].{Id:Id,Domain:DomainName}"
section "Name collisions with this project (novabank-*)"
run aws resourcegroupstaggingapi get-resources --region "$REGION" --tag-filters Key=Project,Values=Cloud-Native-Banking-Microservices-Platform --query "ResourceTagMappingList[].ResourceARN"
section "Budgets"
run aws budgets describe-budgets --account-id "$(aws sts get-caller-identity --query Account --output text)" --query "Budgets[].{Name:BudgetName,Limit:BudgetLimit.Amount}"
section "Service quotas relevant to the MVP"
run aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384 --region "$REGION"
run aws lambda get-account-settings --region "$REGION" --query "AccountLimit"
section "Month-to-date cost (requires ce:GetCostAndUsage)"
run aws ce get-cost-and-usage --time-period "Start=$(date -u +%Y-%m-01),End=$(date -u -d tomorrow +%Y-%m-%d)" --granularity MONTHLY --metrics UnblendedCost
