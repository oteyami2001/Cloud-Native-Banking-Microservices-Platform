variable "name_prefix" { type = string }
variable "jwt_issuer" { type = string }
variable "jwt_audiences" { type = list(string) }

variable "routes" {
  description = "Route key => { service, scopes }."
  type = map(object({
    service = string
    scopes  = list(string)
  }))
}

variable "service_alias_invoke_arns" { type = map(string) }
variable "service_function_names" { type = map(string) }

variable "cors_allowed_origins" {
  type    = list(string)
  default = ["http://localhost:5173"]
}

variable "throttle_burst" {
  type    = number
  default = 50
}

variable "throttle_rate" {
  type    = number
  default = 25
}

variable "log_retention_days" {
  type    = number
  default = 14
}
