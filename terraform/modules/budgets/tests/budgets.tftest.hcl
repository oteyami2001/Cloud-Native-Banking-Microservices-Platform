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
  project_tag         = "Cloud-Native-Banking-Microservices-Platform"
  notification_emails = ["alerts@example.com"]
}

run "budget" {
  command = plan
  assert {
    condition     = aws_budgets_budget.project.limit_amount == "25.00" && aws_budgets_budget.project.time_unit == "MONTHLY"
    error_message = "Monthly USD 25 budget expected."
  }
  assert {
    condition     = length(aws_budgets_budget.project.notification) == 4
    error_message = "50/80/100% actual and 100% forecast notifications expected."
  }
}

run "rejects_excessive_budget" {
  command = plan
  variables {
    monthly_limit_usd = 10000
  }
  expect_failures = [var.monthly_limit_usd]
}
