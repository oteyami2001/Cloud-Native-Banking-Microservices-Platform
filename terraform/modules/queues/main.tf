# Consumer queue + dead-letter queue. SSE with SQS-managed keys (no KMS cost).

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-${var.name}-dlq"
  message_retention_seconds = 1209600 # 14 days: failed-event retention
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "this" {
  name                       = "${var.name_prefix}-${var.name}"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.this.arn]
  })
}

data "aws_iam_policy_document" "tls_and_sources" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["sqs:*"]
    resources = [aws_sqs_queue.this.arn]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
  dynamic "statement" {
    for_each = length(var.eventbridge_rule_arns) > 0 ? [1] : []
    content {
      sid       = "AllowEventBridgeRules"
      actions   = ["sqs:SendMessage"]
      resources = [aws_sqs_queue.this.arn]
      principals {
        type        = "Service"
        identifiers = ["events.amazonaws.com"]
      }
      condition {
        test     = "ArnEquals"
        variable = "aws:SourceArn"
        values   = var.eventbridge_rule_arns
      }
    }
  }
}

resource "aws_sqs_queue_policy" "this" {
  queue_url = aws_sqs_queue.this.id
  policy    = data.aws_iam_policy_document.tls_and_sources.json
}
