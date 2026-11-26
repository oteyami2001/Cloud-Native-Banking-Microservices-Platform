variable "name_prefix" { type = string }
variable "outbox_stream_arn" { type = string }
variable "publisher_alias_arn" { type = string }

variable "schedules" {
  type = map(object({
    expression    = string
    alias_arn     = string
    function_name = string
  }))
}

variable "schedules_enabled" {
  type    = bool
  default = true
}
