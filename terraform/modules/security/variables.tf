variable "name_prefix" { type = string }

variable "create_project_trail" {
  type        = bool
  description = "Create a single-region project trail. Leave false when an account/org trail exists."
  default     = false
}
