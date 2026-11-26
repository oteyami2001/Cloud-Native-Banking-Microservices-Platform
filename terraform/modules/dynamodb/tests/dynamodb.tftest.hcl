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
}

run "tables" {
  command = plan
  assert {
    condition     = length(aws_dynamodb_table.this) == 9 && alltrue([for t in aws_dynamodb_table.this : t.billing_mode == "PAY_PER_REQUEST"])
    error_message = "Nine on-demand tables expected."
  }
  assert {
    condition     = aws_dynamodb_table.this["ledger"].point_in_time_recovery[0].enabled
    error_message = "Ledger must have PITR."
  }
  assert {
    condition     = aws_dynamodb_table.this["outbox"].stream_enabled && aws_dynamodb_table.this["outbox"].stream_view_type == "NEW_IMAGE"
    error_message = "Outbox must stream NEW_IMAGE."
  }
  assert {
    condition     = !aws_dynamodb_table.this["notifications"].point_in_time_recovery[0].enabled
    error_message = "Derived notification data does not need PITR."
  }
}

run "pitr_can_be_disabled" {
  command = plan
  variables {
    enable_pitr = false
  }
  assert {
    condition     = !aws_dynamodb_table.this["ledger"].point_in_time_recovery[0].enabled
    error_message = "enable_pitr=false must disable PITR."
  }
}

run "invalid_prefix" {
  command = plan
  variables {
    name_prefix = "Bad Prefix"
  }
  expect_failures = [var.name_prefix]
}
