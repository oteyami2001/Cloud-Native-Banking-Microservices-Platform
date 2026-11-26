variable "name_prefix" { type = string }
variable "region" { type = string }

variable "github_repository" {
  type        = string
  description = "owner/name"
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must be owner/name."
  }
}

variable "existing_oidc_provider_arn" {
  type        = string
  description = "Reuse the account's existing GitHub OIDC provider instead of creating one."
  default     = null
}

variable "state_bucket" { type = string }

variable "state_key_prefix" {
  type    = string
  default = "novabank/"
}

variable "artifact_bucket" { type = string }

variable "plan_environment" {
  type    = string
  default = "plan"
}

variable "apply_environment" {
  type    = string
  default = "dev"
}

variable "cleanup_environment" {
  type    = string
  default = "cleanup"
}
