# Project security guardrails:
# * A permissions boundary attached to every service role, so even a policy
#   mistake cannot grant IAM, KMS key administration, or access outside the
#   project's resources.
# * Optional project CloudTrail trail (OFF by default: the account may already
#   have an organization trail, and pre-existing security services must not
#   be modified — see docs/security-model.md).

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_iam_policy_document" "boundary" {
  statement {
    sid    = "AllowProjectServiceActions"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem",
      "dynamodb:Query", "dynamodb:Scan", "dynamodb:ConditionCheckItem",
      "dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:ListStreams",
      "events:PutEvents", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:SendMessage",
      "sns:Publish", "s3:PutObject", "s3:GetObject", "lambda:InvokeFunction",
      "logs:CreateLogStream", "logs:PutLogEvents", "xray:PutTraceSegments", "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [data.aws_region.current.region]
    }
  }
  statement {
    sid       = "DenyPrivilegeEscalation"
    effect    = "Deny"
    actions   = ["iam:*", "organizations:*", "kms:CreateKey", "kms:PutKeyPolicy", "kms:ScheduleKeyDeletion", "cloudtrail:*", "config:*", "guardduty:*", "securityhub:*"]
    resources = ["*"]
  }
  statement {
    sid       = "DenyDataPlaneDeletesOnLedger"
    effect    = "Deny"
    actions   = ["dynamodb:DeleteItem", "dynamodb:DeleteTable", "dynamodb:UpdateTable"]
    resources = ["arn:aws:dynamodb:*:${data.aws_caller_identity.current.account_id}:table/${var.name_prefix}-ledger"]
  }
}

resource "aws_iam_policy" "boundary" {
  name        = "${var.name_prefix}-service-boundary"
  description = "Permissions boundary for NovaBank service roles"
  policy      = data.aws_iam_policy_document.boundary.json
}

# ------------------------------------------------------------ optional trail
resource "aws_s3_bucket" "trail" {
  count         = var.create_project_trail ? 1 : 0
  bucket        = "${var.name_prefix}-cloudtrail-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "trail" {
  count                   = var.create_project_trail ? 1 : 0
  bucket                  = aws_s3_bucket.trail[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "trail" {
  count = var.create_project_trail ? 1 : 0
  statement {
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.trail[0].arn]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.trail[0].arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "trail" {
  count  = var.create_project_trail ? 1 : 0
  bucket = aws_s3_bucket.trail[0].id
  policy = data.aws_iam_policy_document.trail[0].json
}

resource "aws_cloudtrail" "project" {
  count                         = var.create_project_trail ? 1 : 0
  name                          = "${var.name_prefix}-trail"
  s3_bucket_name                = aws_s3_bucket.trail[0].id
  include_global_service_events = false
  is_multi_region_trail         = false
  enable_log_file_validation    = true
  depends_on                    = [aws_s3_bucket_policy.trail]
}
