variable "expected_account_id" {
  type        = string
  description = "AWS account ID this state may manage. Confirm before first apply."
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID."
  }
}

variable "region" {
  type    = string
  default = "us-east-2"
}

variable "project_tag" {
  type    = string
  default = "Cloud-Native-Banking-Microservices-Platform"
}

variable "enable_pitr" {
  type    = bool
  default = true
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "mfa_configuration" {
  type    = string
  default = "OPTIONAL"
}

variable "sandbox_opening_balances" {
  type    = bool
  default = true
}

variable "fault_injection" {
  type = object({
    fraud        = optional(string, "off")
    notification = optional(string, "off")
  })
  default = {}
}

variable "reserved_concurrency" {
  type    = number
  default = -1
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "frontend_enabled" {
  type    = bool
  default = true
}

variable "web_acl_arn" {
  type    = string
  default = null
}

variable "evidence_admin_role_arns" {
  type    = list(string)
  default = []
}

variable "evidence_force_destroy" {
  type    = bool
  default = false
}

variable "alert_email" {
  type    = string
  default = null
}

variable "budget_enabled" {
  type    = bool
  default = true
}

variable "monthly_budget_usd" {
  type    = number
  default = 25
}
