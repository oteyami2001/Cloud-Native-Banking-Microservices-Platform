variable "name_prefix" { type = string }
variable "bucket_name" { type = string }

variable "csp_connect_src" {
  type        = list(string)
  description = "API and Cognito origins the SPA may call."
  default     = []
}

variable "web_acl_arn" {
  type        = string
  description = "Optional AWS WAF web ACL (CLOUDFRONT scope, us-east-1). Null = no WAF."
  default     = null
}
