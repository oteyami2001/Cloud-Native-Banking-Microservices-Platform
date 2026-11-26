variable "name_prefix" { type = string }
variable "name" { type = string }

variable "visibility_timeout_seconds" {
  type        = number
  description = "Must be at least 6x the consumer Lambda timeout."
  default     = 60
}

variable "max_receive_count" {
  type    = number
  default = 5
}

variable "eventbridge_rule_arns" {
  type    = list(string)
  default = []
}
