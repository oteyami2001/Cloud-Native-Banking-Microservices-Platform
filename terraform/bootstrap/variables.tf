variable "expected_account_id" {
  type = string
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

variable "github_repository" {
  type    = string
  default = "oteyami2001/Cloud-Native-Banking-Microservices-Platform"
}

variable "existing_oidc_provider_arn" {
  type        = string
  description = "Set when scripts/discover_aws.sh finds an existing token.actions.githubusercontent.com provider."
  default     = null
}
