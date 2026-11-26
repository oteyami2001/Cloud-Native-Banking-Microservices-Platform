# Cognito user pool: customer identity, MFA, OAuth 2.0 authorization code + PKCE.

resource "aws_cognito_user_pool" "this" {
  name                     = "${var.name_prefix}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = var.mfa_configuration
  deletion_protection      = var.deletion_protection ? "ACTIVE" : "INACTIVE"

  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 3
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = var.admin_create_only
  }

  user_pool_add_ons {
    advanced_security_mode = "OFF" # paid feature; enable only with approval
  }
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.domain_prefix
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "aws_cognito_resource_server" "api" {
  identifier   = "novabank"
  name         = "NovaBank API"
  user_pool_id = aws_cognito_user_pool.this.id

  scope {
    scope_name        = "read"
    scope_description = "Read own banking data"
  }
  scope {
    scope_name        = "write"
    scope_description = "Create customers, accounts and transfers"
  }
  scope {
    scope_name        = "admin"
    scope_description = "Administrative operations (also requires a group)"
  }
}

# Public SPA client: no client secret, authorization code flow with PKCE only.
resource "aws_cognito_user_pool_client" "spa" {
  name                                 = "${var.name_prefix}-spa"
  user_pool_id                         = aws_cognito_user_pool.this.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "novabank/read", "novabank/write", "novabank/admin"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  access_token_validity                = 15
  id_token_validity                    = 15
  refresh_token_validity               = 8
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }

  depends_on = [aws_cognito_resource_server.api]
}

resource "aws_cognito_user_group" "groups" {
  for_each     = toset(["customers", "fraud-reviewers", "auditors"])
  name         = each.key
  user_pool_id = aws_cognito_user_pool.this.id
  description  = "NovaBank ${each.key}"
}
