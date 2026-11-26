variable "name_prefix" {
  type = string
  validation {
    condition     = can(regex("^novabank-(dev|staging|prod)$", var.name_prefix))
    error_message = "name_prefix must be novabank-dev, novabank-staging or novabank-prod."
  }
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
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
  type        = bool
  description = "Allow documented synthetic opening deposits on account creation."
  default     = true
}

variable "fault_injection" {
  description = "Controlled failure injection for validation scenarios (honoured only in local/dev)."
  type = object({
    fraud        = optional(string, "off")
    notification = optional(string, "off")
  })
  default = {}
  validation {
    condition     = contains(["off", "unavailable"], var.fault_injection.fraud) && contains(["off", "fail"], var.fault_injection.notification)
    error_message = "fault_injection.fraud must be off|unavailable and notification off|fail."
  }
}

variable "reserved_concurrency" {
  type        = number
  description = "Per-function reserved concurrency (-1 = unreserved). Caps runaway cost in dev."
  default     = -1
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "tracing_enabled" {
  type    = bool
  default = true
}

variable "api_throttle_burst" {
  type    = number
  default = 50
}

variable "api_throttle_rate" {
  type    = number
  default = 25
}

variable "schedules_enabled" {
  type    = bool
  default = true
}

variable "frontend_enabled" {
  type    = bool
  default = true
}

variable "web_acl_arn" {
  type        = string
  description = "Optional AWS WAF web ACL for CloudFront (subject to cost approval)."
  default     = null
}

variable "create_project_trail" {
  type    = bool
  default = false
}

variable "evidence_admin_role_arns" {
  type        = list(string)
  description = "Additional roles (e.g. GitHub cleanup role) allowed to delete evidence objects."
  default     = []
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
