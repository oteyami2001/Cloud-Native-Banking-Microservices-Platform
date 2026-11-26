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

denied=0
printf '%-45s %-14s %s\n' ACTION DECISION SCP
for chunk_start in $(seq 0 10 $(( ${#ACTIONS[@]} - 1 ))); do
  chunk=("${ACTIONS[@]:$chunk_start:10}")
  out="$(aws iam simulate-principal-policy --policy-source-arn "$ROLE_ARN" --action-names "${chunk[@]}" \
    --query 'EvaluationResults[].[EvalActionName,EvalDecision,OrganizationsDecisionDetail.AllowedByOrganizations]' \
    --output text 2>&1)" || { echo "Simulator unavailable: $out"; exit 2; }
  while read -r action decision scp; do
    printf '%-45s %-14s %s\n' "$action" "$decision" "${scp:-n/a}"
    [ "$scp" = "False" ] && denied=$((denied + 1))
  done <<< "$out"
done
echo
if [ "$denied" -eq 0 ]; then
  echo "No SCP denials found for the simulated actions."
else
  echo "$denied action(s) denied by an SCP. Share this output before applying."
fi
