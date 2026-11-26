# NovaBank Digital — prod environment.

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.expected_account_id] # fail closed on the wrong account

  default_tags {
    tags = {
      Project     = var.project_tag
      Environment = "prod"
      ManagedBy   = "terraform"
      Repository  = "oteyami2001/Cloud-Native-Banking-Microservices-Platform"
      DataClass   = "synthetic"
    }
  }
}

module "platform" {
  source = "../../modules/platform"

  name_prefix              = "novabank-prod"
  environment              = "prod"
  project_tag              = var.project_tag
  enable_pitr              = var.enable_pitr
  deletion_protection      = var.deletion_protection
  mfa_configuration        = var.mfa_configuration
  sandbox_opening_balances = var.sandbox_opening_balances
  fault_injection          = var.fault_injection
  reserved_concurrency     = var.reserved_concurrency
  log_retention_days       = var.log_retention_days
  frontend_enabled         = var.frontend_enabled
  web_acl_arn              = var.web_acl_arn
  evidence_admin_role_arns = var.evidence_admin_role_arns
  evidence_force_destroy   = var.evidence_force_destroy
  alert_email              = var.alert_email
  budget_enabled           = var.budget_enabled
  monthly_budget_usd       = var.monthly_budget_usd
}
