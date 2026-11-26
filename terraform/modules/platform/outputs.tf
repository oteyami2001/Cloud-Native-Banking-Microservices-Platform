output "api_endpoint" { value = module.api.api_endpoint }
output "api_id" { value = module.api.api_id }
output "user_pool_id" { value = module.identity.user_pool_id }
output "spa_client_id" { value = module.identity.spa_client_id }
output "cognito_issuer" { value = module.identity.issuer }
output "cognito_domain" { value = "https://${module.identity.hosted_ui_domain}.auth.${local.region}.amazoncognito.com" }
output "function_names" { value = { for k, m in module.service : k => m.function_name } }
output "table_names" { value = module.dynamodb.table_names }
output "evidence_bucket" { value = module.evidence.bucket_name }
output "event_bus_name" { value = module.event_bus.bus_name }
output "frontend_bucket" { value = try(module.frontend[0].bucket_name, null) }
output "frontend_distribution_id" { value = try(module.frontend[0].distribution_id, null) }
output "site_url" { value = try(module.frontend[0].site_url, null) }
output "dashboard_name" { value = module.observability.dashboard_name }
output "routes" { value = keys(local.routes) }
