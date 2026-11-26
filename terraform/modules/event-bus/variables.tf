variable "name_prefix" { type = string }

variable "routes" {
  type = map(object({
    detail_types = list(string)
    queue_arn    = string
  }))
}

variable "delivery_dlq_arn" {
  type        = string
  description = "SQS DLQ for events EventBridge could not deliver to a target."
}

variable "archive_retention_days" {
  type    = number
  default = 30
}
