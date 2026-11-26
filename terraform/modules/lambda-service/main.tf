# One banking microservice = one Lambda function, one IAM role, one log group
# and one "live" alias.
#
# Ownership boundary (ADR-0010): Terraform creates the function from a
# placeholder package and owns configuration. The deploy-services workflow owns
# code, published versions and the alias target. ignore_changes prevents a
# later terraform apply from rolling an application release back.

terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.70" }
    archive = { source = "hashicorp/archive", version = "~> 2.7" }
  }
}

data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/.placeholder-${var.name}.zip"
  source {
    filename = "placeholder.py"
    content  = "def handler(event, context):\n    raise RuntimeError('No release deployed yet')\n"
  }
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name                 = "${var.name_prefix}-${var.name}"
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  permissions_boundary = var.permissions_boundary_arn
}

data "aws_iam_policy_document" "service" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
  statement {
    sid       = "Tracing"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"] # X-Ray does not support resource-level permissions
  }
  dynamic "statement" {
    for_each = var.policy_statements
    content {
      sid       = statement.value.sid
      actions   = statement.value.actions
      resources = statement.value.resources
      dynamic "condition" {
        for_each = lookup(statement.value, "conditions", [])
        content {
          test     = condition.value.test
          variable = condition.value.variable
          values   = condition.value.values
        }
      }
    }
  }
}

resource "aws_iam_role_policy" "service" {
  name   = "service"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.service.json
}

resource "aws_cloudwatch_log_group" "this" {
  #checkov:skip=CKV_AWS_158:Logs contain no secrets or PII; CMK optional via logs_kms_key_arn
  #checkov:skip=CKV_AWS_338:Retention is configurable; 14 days in dev for cost
  name              = "/aws/lambda/${var.name_prefix}-${var.name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn
}

resource "aws_lambda_function" "this" {
  #checkov:skip=CKV_AWS_116:Synchronous and stream/SQS invocations use queue DLQs and on-failure destinations instead
  #checkov:skip=CKV_AWS_117:ADR-0001: no customer VPC in the serverless MVP (avoids NAT/endpoint cost)
  #checkov:skip=CKV_AWS_173:No secrets in environment variables; AWS managed key encryption at rest
  #checkov:skip=CKV_AWS_272:Integrity enforced by SHA-256 manifest and GitHub build attestations (ADR-0011)
  function_name                  = "${var.name_prefix}-${var.name}"
  role                           = aws_iam_role.this.arn
  runtime                        = "python3.13"
  architectures                  = ["arm64"]
  handler                        = var.handler
  filename                       = data.archive_file.placeholder.output_path
  source_code_hash               = data.archive_file.placeholder.output_base64sha256
  memory_size                    = var.memory_mb
  timeout                        = var.timeout_seconds
  reserved_concurrent_executions = var.reserved_concurrency
  publish                        = true

  environment {
    variables = merge(var.environment, {
      SERVICE_NAME = var.name
      LOG_LEVEL    = "INFO"
    })
  }

  tracing_config {
    mode = var.tracing_enabled ? "Active" : "PassThrough"
  }

  logging_config {
    log_format = "Text" # services already emit JSON lines
    log_group  = aws_cloudwatch_log_group.this.name
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash, s3_bucket, s3_key, s3_object_version, publish]
  }

  depends_on = [aws_iam_role_policy.service]
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.this.function_name
  function_version = aws_lambda_function.this.version

  lifecycle {
    ignore_changes = [function_version, routing_config]
  }
}
