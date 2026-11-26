# HTTP API with a Cognito JWT authorizer. Every route requires a valid access
# token; scopes are enforced per route here AND re-checked in the services.
# Note: AWS WAF cannot be associated with an HTTP API directly (only REST API
# stages, ALB, CloudFront, AppSync, Cognito...). See docs/security-model.md.

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"
  description   = "NovaBank Digital synthetic banking API"

  cors_configuration {
    allow_origins  = var.cors_allowed_origins
    allow_methods  = ["GET", "POST", "PATCH", "OPTIONS"]
    allow_headers  = ["authorization", "content-type", "idempotency-key", "x-correlation-id"]
    expose_headers = ["x-correlation-id"]
    max_age        = 600
  }
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.this.id
  authorizer_type  = "JWT"
  name             = "cognito"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    issuer   = var.jwt_issuer
    audience = var.jwt_audiences
  }
}

locals {
  services = toset([for r in values(var.routes) : r.service])
}

resource "aws_apigatewayv2_integration" "service" {
  for_each               = local.services
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.service_alias_invoke_arns[each.key]
  payload_format_version = "2.0"
  timeout_milliseconds   = 10000
}

resource "aws_apigatewayv2_route" "this" {
  for_each             = var.routes
  api_id               = aws_apigatewayv2_api.this.id
  route_key            = each.key
  target               = "integrations/${aws_apigatewayv2_integration.service[each.value.service].id}"
  authorization_type   = "JWT"
  authorizer_id        = aws_apigatewayv2_authorizer.jwt.id
  authorization_scopes = each.value.scopes
}

resource "aws_cloudwatch_log_group" "access" {
  #checkov:skip=CKV_AWS_158:Access logs exclude headers and bodies; CMK optional
  #checkov:skip=CKV_AWS_338:Retention is configurable; 14 days in dev for cost
  name              = "/aws/apigateway/${var.name_prefix}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = var.throttle_burst
    throttling_rate_limit  = var.throttle_rate
  }

  # Access logs deliberately exclude headers and bodies (no tokens or PII).
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      latencyMs      = "$context.responseLatency"
      integrationMs  = "$context.integrationLatency"
      authorizerErr  = "$context.authorizer.error"
      integrationErr = "$context.integrationErrorMessage"
      sourceIp       = "$context.identity.sourceIp"
      requestTime    = "$context.requestTimeEpoch"
    })
  }
}

resource "aws_lambda_permission" "api" {
  for_each      = local.services
  statement_id  = "AllowApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.service_function_names[each.key]
  qualifier     = "live"
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
