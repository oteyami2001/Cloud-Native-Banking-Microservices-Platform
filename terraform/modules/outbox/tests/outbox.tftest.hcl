mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-2" }
  }
}

variables {
  name_prefix         = "novabank-dev"
  outbox_stream_arn   = "arn:aws:dynamodb:us-east-2:123456789012:table/novabank-dev-outbox/stream/2026"
  publisher_alias_arn = "arn:aws:lambda:us-east-2:123456789012:function:novabank-dev-outbox-publisher:live"
  schedules = {
    ledger-reconciliation = { expression = "rate(1 hour)", alias_arn = "arn:aws:lambda:us-east-2:123456789012:function:x:live", function_name = "x" }
  }
}

run "bounded_retries_and_partial_batches" {
  command = plan
  assert {
    condition     = aws_lambda_event_source_mapping.publisher.maximum_retry_attempts == 5 && aws_lambda_event_source_mapping.publisher.bisect_batch_on_function_error
    error_message = "Publisher needs bounded retries and bisect-on-error."
  }
  assert {
    condition     = contains(aws_lambda_event_source_mapping.publisher.function_response_types, "ReportBatchItemFailures")
    error_message = "Publisher must report partial batch failures."
  }
  assert {
    condition     = aws_cloudwatch_event_rule.schedule["ledger-reconciliation"].state == "ENABLED"
    error_message = "Reconciliation must be scheduled."
  }
}
