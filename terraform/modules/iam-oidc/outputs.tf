output "role_arns" { value = { for k, r in aws_iam_role.github : k => r.arn } }
output "oidc_provider_arn" { value = local.provider_arn }
