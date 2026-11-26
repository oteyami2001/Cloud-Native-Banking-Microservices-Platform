# Offline Terraform tests (mocked providers, no AWS credentials).
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
  name_prefix = "novabank-dev"
  environment = "dev"
}

run "routes_and_services" {
  command = plan

  assert {
    condition     = length(output.routes) == 16
    error_message = "Expected 16 API routes (contracts/openapi.yaml)."
  }
  assert {
    condition     = alltrue([for k, v in local.routes : strcontains(k, "/admin/") ? contains(v.scopes, "novabank/admin") : true])
    error_message = "Admin routes must require the novabank/admin scope."
  }
  assert {
    condition     = length(module.service) == 10
    error_message = "Expected 7 services + 3 workers."
  }
  assert {
    condition     = alltrue([for k, m in module.service : m.role_name == "novabank-dev-${k}"])
    error_message = "Each service needs its own project-scoped role."
  }
}

run "budget_defaults_to_25_usd" {
  command = plan
  assert {
    condition     = var.monthly_budget_usd == 25 && length(module.budgets) == 1
    error_message = "Budget alert must default to USD 25."
  }
}

run "rejects_unknown_environment_prefix" {
  command = plan
  variables {
    name_prefix = "bank-test"
  }
  expect_failures = [var.name_prefix]
}

run "rejects_invalid_fault_injection" {
  command = plan
  variables {
    fault_injection = { fraud = "random" }
  }
  expect_failures = [var.fault_injection]
}
