output "state_bucket" { value = local.state_bucket }
output "artifact_bucket" { value = local.artifact_bucket }
output "github_role_arns" { value = module.github_oidc.role_arns }
