variable "name" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.name))
    error_message = "name must be lowercase kebab-case."
  }
}

variable "name_prefix" { type = string }

variable "handler" {
  type        = string
  description = "Python handler path, e.g. services.ledger.handler.handler."
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "policy_statements" {
  description = "Least-privilege IAM statements for this service only."
  type = list(object({
    sid       = string
    actions   = list(string)
    resources = list(string)
    conditions = optional(list(object({
      test     = string
      variable = string
      values   = list(string)
    })), [])
  }))
  default = []
}

variable "memory_mb" {
  type    = number
  default = 256
}

variable "timeout_seconds" {
  type    = number
  default = 10
}

variable "reserved_concurrency" {
  type        = number
  description = "-1 = unreserved. Low values cap cost and blast radius in dev."
  default     = -1
}

variable "log_retention_days" {
  type    = number
  default = 14
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "log_retention_days must be a CloudWatch Logs supported value."
  }
}

variable "logs_kms_key_arn" {
  type    = string
  default = null
}

variable "tracing_enabled" {
  type    = bool
  default = true
}

variable "permissions_boundary_arn" {
  type    = string
  default = null
}
