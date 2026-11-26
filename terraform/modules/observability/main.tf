# Operational dashboard and alarms (pattern reused from the AIOps project).
# Custom metrics come from CloudWatch EMF log lines in namespace NovaBank/Banking
# with low-cardinality dimensions only.

# Not encrypted with alias/aws/sns on purpose: CloudWatch alarms cannot publish
# to topics using the AWS managed SNS key (its key policy cannot be extended),
# so alarms would fail silently. Messages carry only alarm names, transfer IDs
# and scores (no customer data). A customer managed key is the prod option.
resource "aws_sns_topic" "ops" {
  #checkov:skip=CKV_AWS_26:CloudWatch alarms cannot use alias/aws/sns; payloads contain no customer data
  name = "${var.name_prefix}-ops-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == null ? 0 : 1
  topic_arn = aws_sns_topic.ops.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

locals {
  ns = "NovaBank/Banking"
  alarms = merge(
    { for fn in var.function_names : "lambda-errors-${fn}" => {
      namespace  = "AWS/Lambda", metric = "Errors", stat = "Sum", threshold = 1, period = 300,
      dimensions = { FunctionName = fn }, description = "Lambda errors in ${fn}"
    } },
    { for fn in var.function_names : "lambda-throttles-${fn}" => {
      namespace  = "AWS/Lambda", metric = "Throttles", stat = "Sum", threshold = 1, period = 300,
      dimensions = { FunctionName = fn }, description = "Lambda throttling in ${fn}"
    } },
    { for q in var.dlq_names : "dlq-${q}" => {
      namespace  = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible", stat = "Maximum", threshold = 1, period = 300,
      dimensions = { QueueName = q }, description = "Messages in dead-letter queue ${q}"
    } },
    { for q in var.queue_names : "queue-age-${q}" => {
      namespace  = "AWS/SQS", metric = "ApproximateAgeOfOldestMessage", stat = "Maximum", threshold = 300, period = 300,
      dimensions = { QueueName = q }, description = "Oldest message in ${q} older than 5 minutes"
    } },
    {
      "api-5xx" = {
        namespace  = "AWS/ApiGateway", metric = "5xx", stat = "Sum", threshold = 5, period = 300,
        dimensions = { ApiId = var.api_id, Stage = "$default" }, description = "API 5xx responses"
      }
      "api-latency-p95" = {
        namespace  = "AWS/ApiGateway", metric = "Latency", stat = "p95", threshold = 2000, period = 300,
        dimensions = { ApiId = var.api_id, Stage = "$default" }, description = "API p95 latency above 2s"
      }
      "reconciliation-discrepancies" = {
        namespace  = local.ns, metric = "ReconciliationDiscrepancies", stat = "Maximum", threshold = 1, period = 3600,
        dimensions = { Service = "ledger-reconciliation" }, description = "Ledger reconciliation found discrepancies"
      }
      "outbox-pending-age" = {
        namespace  = local.ns, metric = "OutboxOldestPendingAgeSeconds", stat = "Maximum", threshold = 600, period = 900,
        dimensions = { Service = "outbox-reconciliation" }, description = "Outbox event unpublished for over 10 minutes"
      }
      "outbox-dead" = {
        namespace  = local.ns, metric = "OutboxEventsFailedPermanently", stat = "Sum", threshold = 1, period = 900,
        dimensions = { Service = "outbox-reconciliation" }, description = "Outbox events failed permanently"
      }
      "stream-failures" = {
        namespace  = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible", stat = "Maximum", threshold = 1, period = 300,
        dimensions = { QueueName = var.stream_failure_queue_name }, description = "Outbox stream batches exhausted retries"
      }
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "this" {
  for_each            = local.alarms
  alarm_name          = "${var.name_prefix}-${each.key}"
  alarm_description   = each.value.description
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  dimensions          = each.value.dimensions
  statistic           = contains(["Sum", "Maximum", "Minimum", "Average", "SampleCount"], each.value.stat) ? each.value.stat : null
  extended_statistic  = contains(["Sum", "Maximum", "Minimum", "Average", "SampleCount"], each.value.stat) ? null : each.value.stat
  period              = each.value.period
  evaluation_periods  = 1
  threshold           = each.value.threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops.arn]
  ok_actions          = [aws_sns_topic.ops.arn]
}

resource "aws_cloudwatch_dashboard" "ops" {
  dashboard_name = "${var.name_prefix}-operations"
  dashboard_body = jsonencode({
    widgets = [
      { type = "text", x = 0, y = 0, width = 24, height = 1, properties = { markdown = "## NovaBank Digital — Operations Center (synthetic data)" } },
      { type = "metric", x = 0, y = 1, width = 12, height = 6, properties = {
        title = "Transfers", region = var.region, stat = "Sum", period = 300,
        metrics = [
          [local.ns, "TransferRequested", "Service", "transfer"],
          [local.ns, "TransferCompleted", "Service", "transfer"],
          [local.ns, "TransferPendingReview", "Service", "transfer"],
          [local.ns, "TransferFailedClosed", "Service", "transfer"],
        ]
      } },
      { type = "metric", x = 12, y = 1, width = 12, height = 6, properties = {
        title = "API requests, errors and latency", region = var.region, period = 300,
        metrics = [
          ["AWS/ApiGateway", "Count", "ApiId", var.api_id, "Stage", "$default", { stat = "Sum" }],
          ["AWS/ApiGateway", "4xx", "ApiId", var.api_id, "Stage", "$default", { stat = "Sum" }],
          ["AWS/ApiGateway", "5xx", "ApiId", var.api_id, "Stage", "$default", { stat = "Sum" }],
          ["AWS/ApiGateway", "Latency", "ApiId", var.api_id, "Stage", "$default", { stat = "p95", yAxis = "right" }],
        ]
      } },
      { type = "metric", x = 0, y = 7, width = 8, height = 6, properties = {
        title = "Ledger integrity", region = var.region, stat = "Sum", period = 300,
        metrics = [
          [local.ns, "JournalPosted", "JournalType", "TRANSFER", "Service", "ledger"],
          [local.ns, "LedgerTransactionConflict", "Service", "ledger"],
          [local.ns, "DuplicatePostingPrevented", "Service", "ledger"],
          [local.ns, "InsufficientFunds", "Service", "ledger"],
          [local.ns, "ReconciliationDiscrepancies", "Service", "ledger-reconciliation", { stat = "Maximum" }],
        ]
      } },
      { type = "metric", x = 8, y = 7, width = 8, height = 6, properties = {
        title = "Fraud screening", region = var.region, stat = "Sum", period = 300,
        metrics = [
          [local.ns, "FraudScreening", "Decision", "APPROVED", "Service", "fraud"],
          [local.ns, "FraudScreening", "Decision", "PENDING_REVIEW", "Service", "fraud"],
          [local.ns, "FraudScreening", "Decision", "REJECTED", "Service", "fraud"],
        ]
      } },
      { type = "metric", x = 16, y = 7, width = 8, height = 6, properties = {
        title = "Outbox and queues", region = var.region, period = 300,
        metrics = concat(
          [[local.ns, "OutboxOldestPendingAgeSeconds", "Service", "outbox-reconciliation", { stat = "Maximum" }]],
          [for q in var.queue_names : ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", q, { stat = "Maximum" }]],
          [for q in var.dlq_names : ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", q, { stat = "Maximum" }]]
        )
      } },
      { type = "metric", x = 0, y = 13, width = 24, height = 6, properties = {
        title = "Lambda errors and throttles", region = var.region, stat = "Sum", period = 300,
        metrics = concat(
          [for fn in var.function_names : ["AWS/Lambda", "Errors", "FunctionName", fn]],
          [for fn in var.function_names : ["AWS/Lambda", "Throttles", "FunctionName", fn]]
        )
      } },
    ]
  })
}
