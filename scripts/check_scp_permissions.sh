#!/usr/bin/env bash
# Read-only pre-flight: will the Organization's SCPs allow the actions that the
# Phase 7/8 Terraform apply needs? Uses the IAM policy simulator, whose results
# include an Organizations (SCP) decision. Creates nothing.
#
# Usage (CloudShell): bash scripts/check_scp_permissions.sh [role-name]
set -uo pipefail
export AWS_PAGER=""
ROLE_NAME="${1:-$(aws sts get-caller-identity --query Arn --output text | awk -F/ '{print $2}')}"
ROLE_ARN="$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text 2>/dev/null)"
if [ -z "$ROLE_ARN" ]; then
  echo "Cannot read role $ROLE_NAME (iam:GetRole denied?). Pre-flight not possible; apply bootstrap first and watch for AccessDenied."
  exit 2
fi
echo "Simulating as $ROLE_ARN"

ACTIONS=(
  # bootstrap
  s3:CreateBucket s3:PutBucketPolicy s3:PutBucketVersioning s3:PutEncryptionConfiguration
  s3:PutBucketPublicAccessBlock s3:PutLifecycleConfiguration s3:PutBucketOwnershipControls
  iam:CreateRole iam:PutRolePolicy iam:AttachRolePolicy iam:GetOpenIDConnectProvider
  iam:CreatePolicy iam:PutRolePermissionsBoundary iam:PassRole iam:TagRole
  # workload
  dynamodb:CreateTable dynamodb:UpdateContinuousBackups dynamodb:TagResource
  lambda:CreateFunction lambda:CreateAlias lambda:AddPermission lambda:CreateEventSourceMapping lambda:PublishVersion
  apigateway:POST apigateway:PATCH
  cognito-idp:CreateUserPool cognito-idp:CreateUserPoolDomain cognito-idp:CreateUserPoolClient
  cognito-idp:CreateResourceServer cognito-idp:CreateGroup
  events:CreateEventBus events:PutRule events:PutTargets events:CreateArchive
  sqs:CreateQueue sqs:SetQueueAttributes sns:CreateTopic sns:Subscribe
  cloudfront:CreateDistribution cloudfront:CreateOriginAccessControl cloudfront:CreateResponseHeadersPolicy
  logs:CreateLogGroup logs:PutRetentionPolicy cloudwatch:PutMetricAlarm cloudwatch:PutDashboard
  budgets:ModifyBudget xray:PutTraceSegments kms:GenerateDataKey
)

REGION="${AWS_REGION:-us-east-2}"
TAG_VALUE="Cloud-Native-Banking-Microservices-Platform"
CTX_REGION="ContextKeyName=aws:RequestedRegion,ContextKeyValues=$REGION,ContextKeyType=string"
CTX_TAG="ContextKeyName=aws:RequestTag/Project,ContextKeyValues=$TAG_VALUE,ContextKeyType=string"
CTX_TAGKEYS="ContextKeyName=aws:TagKeys,ContextKeyValues=Project,ContextKeyType=stringList"

# Without context keys the simulator treats a missing key (e.g. the region) as
# not matching, so region- or tag-conditioned SCP denies show up as false
# positives. Each mode adds the request context a real API call would carry.
run_mode() {
  local label="$1"; shift
  local denied_list=() allowed=0
  for chunk_start in $(seq 0 10 $(( ${#ACTIONS[@]} - 1 ))); do
    local chunk=("${ACTIONS[@]:$chunk_start:10}")
    local out
    out="$(aws iam simulate-principal-policy --policy-source-arn "$ROLE_ARN" --action-names "${chunk[@]}" "$@" \
      --query 'EvaluationResults[].[EvalActionName,EvalDecision,OrganizationsDecisionDetail.AllowedByOrganizations]' \
      --output text 2>&1)" || { echo "Simulator unavailable: $out"; return 2; }
    while read -r action decision scp; do
      if [ "$scp" = "False" ]; then denied_list+=("$action"); else allowed=$((allowed + 1)); fi
    done <<< "$out"
  done
  echo "== $label: ${#denied_list[@]} denied by SCP, $allowed allowed"
  for a in "${denied_list[@]}"; do echo "   DENIED $a"; done
}

run_mode "1. no request context"
run_mode "2. with aws:RequestedRegion=$REGION" --context-entries "$CTX_REGION"
run_mode "3. with region + Project tag on request" --context-entries "$CTX_REGION" "$CTX_TAG" "$CTX_TAGKEYS"
echo
echo "Interpretation: if mode 2 or 3 shows 0 denied, the SCP is region/tag-conditioned and the real apply will be allowed."
