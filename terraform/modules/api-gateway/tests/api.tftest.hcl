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
  name_prefix   = "novabank-dev"
  jwt_issuer    = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_EXAMPLE"
  jwt_audiences = ["client"]
  routes = {
    "GET /v1/accounts"           = { service = "account", scopes = ["novabank/read"] }
    "GET /v1/admin/fraud-alerts" = { service = "fraud", scopes = ["novabank/admin"] }
  }
  service_alias_invoke_arns = { account = "arn:aws:apigateway:us-east-2:lambda:path/a", fraud = "arn:aws:apigateway:us-east-2:lambda:path/f" }
  service_function_names    = { account = "novabank-dev-account", fraud = "novabank-dev-fraud" }
}

run "jwt_everywhere" {
  command = plan
  assert {
    condition     = alltrue([for r in aws_apigatewayv2_route.this : r.authorization_type == "JWT"])
    error_message = "All routes must use the JWT authorizer."
  }
  assert {
    condition     = aws_apigatewayv2_stage.default.default_route_settings[0].throttling_rate_limit == 25 && aws_apigatewayv2_stage.default.default_route_settings[0].throttling_burst_limit == 50
    error_message = "Throttling must be configured."
  }
  assert {
    condition     = !strcontains(aws_apigatewayv2_stage.default.access_log_settings[0].format, "authorization")
    error_message = "Access logs must not capture authorization headers."
  }
  assert {
    condition     = alltrue([for p in aws_lambda_permission.api : p.qualifier == "live"])
    error_message = "API Gateway may only invoke the live alias."
  }
}
