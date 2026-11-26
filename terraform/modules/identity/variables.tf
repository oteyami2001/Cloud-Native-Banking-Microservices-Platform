variable "name_prefix" { type = string }

variable "domain_prefix" {
  type        = string
  description = "Globally unique Cognito hosted UI domain prefix."
}

variable "callback_urls" { type = list(string) }
variable "logout_urls" { type = list(string) }

variable "mfa_configuration" {
  type    = string
  default = "OPTIONAL"
  validation {
    condition     = contains(["OFF", "OPTIONAL", "ON"], var.mfa_configuration)
    error_message = "mfa_configuration must be OFF, OPTIONAL or ON."
  }
}

variable "admin_create_only" {
  type        = bool
  description = "When true only administrators can create users (recommended for a public demo)."
  default     = true
}

variable "deletion_protection" {
  type    = bool
  default = false
}
