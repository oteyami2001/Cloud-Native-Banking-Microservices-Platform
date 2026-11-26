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

mock_provider "archive" {}

variables {
  name        = "ledger"
  name_prefix = "novabank-dev"
  handler     = "services.ledger.handler.handler"
}

run "runtime_and_tracing" {
  command = plan
  assert {
    condition     = aws_lambda_function.this.runtime == "python3.13" && aws_lambda_function.this.tracing_config[0].mode == "Active"
    error_message = "Python 3.13 with active tracing expected."
  }
  assert {
    condition     = aws_cloudwatch_log_group.this.retention_in_days == 14
    error_message = "Log retention must be bounded."
  }
  assert {
    condition     = aws_lambda_alias.live.name == "live"
    error_message = "A live alias is required for controlled releases."
  }
}

run "rejects_bad_retention" {
  command = plan
  variables {
    log_retention_days = 10
  }
  expect_failures = [var.log_retention_days]
}
