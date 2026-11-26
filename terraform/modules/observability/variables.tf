variable "name_prefix" { type = string }
variable "region" { type = string }
variable "api_id" { type = string }
variable "function_names" { type = list(string) }
variable "queue_names" { type = list(string) }
variable "dlq_names" { type = list(string) }
variable "stream_failure_queue_name" { type = string }

variable "alert_email" {
  type        = string
  description = "Optional e-mail for alarm notifications (subscription must be confirmed)."
  default     = null
}
