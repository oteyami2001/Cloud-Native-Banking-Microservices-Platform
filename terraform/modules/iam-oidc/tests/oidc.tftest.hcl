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
  name_prefix       = "novabank"
  region            = "us-east-2"
  github_repository = "oteyami2001/Cloud-Native-Banking-Microservices-Platform"
  state_bucket      = "novabank-tfstate-123456789012-us-east-2"
  artifact_bucket   = "novabank-artifacts-123456789012-us-east-2"
}

run "separate_roles_bound_to_repo_and_environments" {
  command = plan
  assert {
    condition     = toset(keys(aws_iam_role.github)) == toset(["plan", "apply", "deploy", "cleanup"])
    error_message = "Separate plan/apply/deploy/cleanup roles expected."
  }
  assert {
    condition     = alltrue([for s in local.roles["apply"] : endswith(s, ":environment:dev")]) && alltrue([for s in local.roles["cleanup"] : endswith(s, ":environment:cleanup")])
    error_message = "Privileged roles must only trust protected environments."
  }
  assert {
    condition     = !anytrue([for k in ["apply", "deploy", "cleanup"] : anytrue([for s in local.roles[k] : strcontains(s, "pull_request")])])
    error_message = "Pull requests must never assume privileged roles."
  }
  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 1
    error_message = "Provider is created when none exists."
  }
  assert {
    condition     = toset(keys(aws_iam_role_policy.state)) == toset(["apply", "cleanup"])
    error_message = "Only apply and cleanup may write Terraform state."
  }
  assert {
    condition = anytrue([
      for st in data.aws_iam_policy_document.state_plan.statement :
      st.effect == "Deny" && contains(st.actions, "s3:GetObject")
    ])
    error_message = "The plan role must be denied object reads outside the project state."
  }
  assert {
    condition = alltrue([
      for st in data.aws_iam_policy_document.state_plan.statement :
      contains(coalesce(st.actions, []), "s3:PutObject") ? alltrue([for r in st.resources : endswith(r, ".tflock")]) : true
    ])
    error_message = "The plan role may only write lock files."
  }
}

run "immutable_id_subjects" {
  command = plan
  variables {
    github_owner_id      = "157901928"
    github_repository_id = "1465571609"
  }
  assert {
    condition     = local.roles["apply"] == ["repo:oteyami2001@157901928/Cloud-Native-Banking-Microservices-Platform@1465571609:environment:dev"]
    error_message = "Apply role must trust the exact immutable-ID subject for the dev environment."
  }
  assert {
    condition     = !anytrue([for k, subs in local.roles : anytrue([for s in subs : strcontains(s, "repo:oteyami2001/")])])
    error_message = "Name-based subjects must not be trusted when IDs are supplied."
  }
}

run "rejects_non_numeric_ids" {
  command = plan
  variables {
    github_owner_id = "oteyami2001"
  }
  expect_failures = [var.github_owner_id]
}

run "reuses_existing_provider" {
  command = plan
  variables {
    existing_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  }
  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "An existing provider must be reused, not duplicated."
  }
}

run "rejects_bad_repository" {
  command = plan
  variables {
    github_repository = "not a repo"
  }
  expect_failures = [var.github_repository]
}
