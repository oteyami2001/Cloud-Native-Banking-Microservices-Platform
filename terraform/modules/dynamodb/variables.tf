variable "name_prefix" {
  type        = string
  description = "Prefix such as novabank-dev."
  validation {
    condition     = can(regex("^[a-z0-9-]{3,32}$", var.name_prefix))
    error_message = "name_prefix must be 3-32 lowercase letters, digits or hyphens."
  }
}

variable "enable_pitr" {
  type        = bool
  description = "Enable point-in-time recovery on financial tables (small per-GB cost)."
  default     = true
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "kms_key_arn" {
  type        = string
  description = "Optional customer managed KMS key. Null uses the AWS owned key."
  default     = null
}
