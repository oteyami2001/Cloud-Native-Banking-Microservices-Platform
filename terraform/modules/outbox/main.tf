# Transactional outbox wiring: DynamoDB stream -> publisher Lambda, with
# bounded retries, bisect-on-error, partial batch responses and an on-failure
# SQS destination; plus scheduled outbox and ledger reconciliation jobs.

resource "aws_sqs_queue" "stream_failures" {
  name                      = "${var.name_prefix}-outbox-stream-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_lambda_event_source_mapping" "publisher" {
  event_source_arn                   = var.outbox_stream_arn
  function_name                      = var.publisher_alias_arn
  starting_position                  = "TRIM_HORIZON"
  batch_size                         = 25
  maximum_batching_window_in_seconds = 1
  maximum_retry_attempts             = 5
  maximum_record_age_in_seconds      = 3600
  bisect_batch_on_function_error     = true
  function_response_types            = ["ReportBatchItemFailures"]

  filter_criteria {
    filter {
      pattern = jsonencode({ eventName = ["INSERT"] })
    }
  }

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.stream_failures.arn
    }
  }
}

resource "aws_cloudwatch_event_rule" "schedule" {
  for_each            = var.schedules
  name                = "${var.name_prefix}-${each.key}"
  schedule_expression = each.value.expression
  state               = var.schedules_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "schedule" {
  for_each = var.schedules
  rule     = aws_cloudwatch_event_rule.schedule[each.key].name
  arn      = each.value.alias_arn
  input    = jsonencode({ trigger = "schedule" })
}

resource "aws_lambda_permission" "schedule" {
  for_each      = var.schedules
  statement_id  = "AllowSchedule-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = each.value.function_name
  qualifier     = "live"
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[each.key].arn
}
