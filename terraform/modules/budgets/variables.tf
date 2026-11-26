variable "name_prefix" { type = string }
variable "project_tag" { type = string }

variable "monthly_limit_usd" {
  type    = number
  default = 25
  validation {
    condition     = var.monthly_limit_usd > 0 && var.monthly_limit_usd <= 500
    error_message = "monthly_limit_usd must be between 0 and 500."
  }
}

variable "notification_emails" {
  type    = list(string)
  default = []
}
