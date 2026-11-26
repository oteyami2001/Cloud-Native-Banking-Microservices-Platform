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
  name_prefix = "novabank-dev"
  name        = "audit"
}

run "dlq_and_encryption" {
  command = plan
  assert {
    condition     = aws_sqs_queue.this.sqs_managed_sse_enabled && aws_sqs_queue.dlq.sqs_managed_sse_enabled
    error_message = "Queues must be encrypted."
  }
  assert {
    condition     = aws_sqs_queue.dlq.message_retention_seconds == 1209600
    error_message = "DLQ must retain failed events for 14 days."
  }
}
