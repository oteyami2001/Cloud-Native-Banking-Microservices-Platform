variable "bucket_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{2,62}$", var.bucket_name))
    error_message = "Invalid S3 bucket name."
  }
}

variable "writer_role_arns" {
  type        = list(string)
  description = "Roles allowed to write or delete evidence (audit service, reconciliation, cleanup)."
}

variable "kms_key_arn" {
  type        = string
  description = "Null = AWS managed aws/s3 key."
  default     = null
}

variable "noncurrent_retention_days" {
  type    = number
  default = 90
}

variable "force_destroy" {
  type        = bool
  description = "Allow terraform destroy of a non-empty bucket (dev cleanup only)."
  default     = false
}
