# NovaBank Digital serverless platform composition, shared by dev/staging/prod.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  p          = var.name_prefix
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  t          = module.dynamodb.table_arns
  fn_arn     = "arn:aws:lambda:${local.region}:${local.account_id}:function:${local.p}"

  # Route key => owning service + required OAuth scopes (contracts/openapi.yaml).
  routes = {
    "POST /v1/customers"                    = { service = "customer", scopes = ["novabank/write"] }
    "GET /v1/customers/me"                  = { service = "customer", scopes = ["novabank/read"] }
    "PATCH /v1/customers/me"                = { service = "customer", scopes = ["novabank/write"] }
    "POST /v1/accounts"                     = { service = "account", scopes = ["novabank/write"] }
    "GET /v1/accounts"                      = { service = "account", scopes = ["novabank/read"] }
    "GET /v1/accounts/{id}"                 = { service = "account", scopes = ["novabank/read"] }
    "GET /v1/accounts/{id}/balance"         = { service = "account", scopes = ["novabank/read"] }
    "GET /v1/accounts/{id}/transactions"    = { service = "account", scopes = ["novabank/read"] }
    "POST /v1/transfers"                    = { service = "transfer", scopes = ["novabank/write"] }
    "GET /v1/transfers/{id}"                = { service = "transfer", scopes = ["novabank/read"] }
    "POST /v1/admin/transfers/{id}/approve" = { service = "transfer", scopes = ["novabank/admin"] }
    "POST /v1/admin/transfers/{id}/reject"  = { service = "transfer", scopes = ["novabank/admin"] }
    "GET /v1/admin/fraud-alerts"            = { service = "fraud", scopes = ["novabank/admin"] }
    "GET /v1/admin/reconciliation"          = { service = "audit", scopes = ["novabank/admin"] }
    "GET /v1/admin/audit/transfers/{id}"    = { service = "audit", scopes = ["novabank/admin"] }
    "GET /v1/notifications"                 = { service = "notification", scopes = ["novabank/read"] }
  }

  common_env = {
    ENVIRONMENT                      = var.environment
    CUSTOMERS_TABLE                  = module.dynamodb.table_names["customers"]
    ACCOUNTS_TABLE                   = module.dynamodb.table_names["accounts"]
    LEDGER_TABLE                     = module.dynamodb.table_names["ledger"]
    TRANSFERS_TABLE                  = module.dynamodb.table_names["transfers"]
    IDEMPOTENCY_TABLE                = module.dynamodb.table_names["idempotency"]
    FRAUD_TABLE                      = module.dynamodb.table_names["fraud"]
    OUTBOX_TABLE                     = module.dynamodb.table_names["outbox"]
    NOTIFICATIONS_TABLE              = module.dynamodb.table_names["notifications"]
    AUDIT_TABLE                      = module.dynamodb.table_names["audit"]
    EVENT_BUS_NAME                   = "${local.p}-events"
    EVIDENCE_BUCKET                  = local.evidence_bucket
    EXPECTED_ISSUER                  = module.identity.issuer
    ALLOWED_CLIENT_IDS               = module.identity.spa_client_id
    SANDBOX_OPENING_BALANCES_ENABLED = tostring(var.sandbox_opening_balances)
  }

  evidence_bucket = "${local.p}-evidence-${local.account_id}"
  ops_topic_arn   = "arn:aws:sns:${local.region}:${local.account_id}:${local.p}-ops-alerts"
  outbox_put      = { sid = "OutboxAppend", actions = ["dynamodb:PutItem"], resources = [local.t["outbox"]] }
  identity_lookup = {
    sid        = "ResolveIdentityOnly"
    actions    = ["dynamodb:GetItem"]
    resources  = [local.t["customers"]]
    conditions = [{ test = "ForAllValues:StringLike", variable = "dynamodb:LeadingKeys", values = ["IDENTITY#*"] }]
  }
  invoke = { for s in ["ledger", "fraud", "account"] : s => "${local.fn_arn}-${s}:live" }

  services = {
    customer = {
      handler = "services.customer.handler.handler"
      env     = {}
      policy = [
        { sid = "Customers", actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], resources = [local.t["customers"]] },
        local.outbox_put,
      ]
    }
    account = {
      handler = "services.account.handler.handler"
      env     = { LEDGER_FUNCTION_NAME = "${local.p}-ledger:live" }
      policy = [
        { sid = "Accounts", actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"], resources = [local.t["accounts"], "${local.t["accounts"]}/index/GSI1"] },
        local.outbox_put, local.identity_lookup,
        { sid = "InvokeLedger", actions = ["lambda:InvokeFunction"], resources = [local.invoke.ledger] },
      ]
    }
    ledger = {
      handler = "services.ledger.handler.handler"
      env     = {}
      policy = [
        { sid = "LedgerTable", actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"], resources = [local.t["ledger"]] },
        {
          sid        = "PostingIdempotency", actions = ["dynamodb:PutItem"], resources = [local.t["idempotency"]],
          conditions = [{ test = "ForAllValues:StringLike", variable = "dynamodb:LeadingKeys", values = ["POSTING#*"] }]
        },
        { sid = "TransferStateOnPosting", actions = ["dynamodb:UpdateItem"], resources = [local.t["transfers"]] },
        local.outbox_put,
      ]
    }
    transfer = {
      handler = "services.transfer.handler.handler"
      env = {
        LEDGER_FUNCTION_NAME  = "${local.p}-ledger:live"
        FRAUD_FUNCTION_NAME   = "${local.p}-fraud:live"
        ACCOUNT_FUNCTION_NAME = "${local.p}-account:live"
      }
      policy = [
        { sid = "Transfers", actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], resources = [local.t["transfers"]] },
        {
          sid        = "RequestIdempotency", actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"],
          resources  = [local.t["idempotency"]],
          conditions = [{ test = "ForAllValues:StringLike", variable = "dynamodb:LeadingKeys", values = ["CUSTOMER#*"] }]
        },
        local.outbox_put, local.identity_lookup,
        { sid = "InvokeDependencies", actions = ["lambda:InvokeFunction"], resources = [local.invoke.ledger, local.invoke.fraud, local.invoke.account] },
      ]
    }
    fraud = {
      handler = "services.fraud.handler.handler"
      env     = { FRAUD_FAULT_INJECTION = var.fault_injection.fraud }
      policy = [
        { sid = "FraudTable", actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"], resources = [local.t["fraud"], "${local.t["fraud"]}/index/GSI1"] },
        local.outbox_put,
      ]
    }
    notification = {
      handler = "services.notification.handler.handler"
      env     = { OPS_TOPIC_ARN = local.ops_topic_arn, NOTIFICATION_FAULT_INJECTION = var.fault_injection.notification }
      policy = [
        { sid = "Notifications", actions = ["dynamodb:PutItem", "dynamodb:Query"], resources = [local.t["notifications"], "${local.t["notifications"]}/index/GSI1"] },
        local.identity_lookup,
        { sid = "Queue", actions = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], resources = [module.notification_queue.queue_arn] },
        { sid = "OpsAlerts", actions = ["sns:Publish"], resources = [local.ops_topic_arn] },
      ]
    }
    audit = {
      handler = "services.audit.handler.handler"
      env     = {}
      policy = [
        { sid = "AuditTable", actions = ["dynamodb:PutItem", "dynamodb:Query"], resources = [local.t["audit"]] },
        { sid = "Evidence", actions = ["s3:PutObject"], resources = ["arn:aws:s3:::${local.evidence_bucket}/evidence/events/*"] },
        { sid = "Queue", actions = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], resources = [module.audit_queue.queue_arn] },
      ]
    }
    outbox-publisher = {
      handler = "workers.outbox_publisher.handler.handler"
      env     = {}
      policy = [
        { sid = "Stream", actions = ["dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:ListStreams"], resources = ["${local.t["outbox"]}/stream/*"] },
        { sid = "MarkPublished", actions = ["dynamodb:UpdateItem"], resources = [local.t["outbox"]] },
        { sid = "Publish", actions = ["events:PutEvents"], resources = ["arn:aws:events:${local.region}:${local.account_id}:event-bus/${local.p}-events"] },
        { sid = "OnFailure", actions = ["sqs:SendMessage"], resources = ["arn:aws:sqs:${local.region}:${local.account_id}:${local.p}-outbox-stream-failures"] },
      ]
    }
    outbox-reconciliation = {
      handler = "workers.outbox_reconciliation.handler.handler"
      env     = {}
      policy = [
        { sid = "Outbox", actions = ["dynamodb:Query", "dynamodb:GetItem", "dynamodb:UpdateItem"], resources = [local.t["outbox"], "${local.t["outbox"]}/index/PendingIndex"] },
        { sid = "Publish", actions = ["events:PutEvents"], resources = ["arn:aws:events:${local.region}:${local.account_id}:event-bus/${local.p}-events"] },
      ]
    }
    ledger-reconciliation = {
      handler = "workers.ledger_reconciliation.handler.handler"
      env     = {}
      policy = [
        { sid = "ReadLedger", actions = ["dynamodb:Scan"], resources = [local.t["ledger"], local.t["transfers"]] },
        { sid = "Report", actions = ["dynamodb:PutItem"], resources = [local.t["audit"]] },
        local.outbox_put,
        { sid = "Evidence", actions = ["s3:PutObject"], resources = ["arn:aws:s3:::${local.evidence_bucket}/evidence/reconciliation/*"] },
      ]
    }
  }
}

module "security" {
  source               = "../security"
  name_prefix          = local.p
  create_project_trail = var.create_project_trail
}

module "dynamodb" {
  source              = "../dynamodb"
  name_prefix         = local.p
  enable_pitr         = var.enable_pitr
  deletion_protection = var.deletion_protection
}

module "identity" {
  source            = "../identity"
  name_prefix       = local.p
  domain_prefix     = "${local.p}-${substr(local.account_id, 8, 4)}"
  callback_urls     = concat(["http://localhost:5173/callback"], var.frontend_enabled ? ["${module.frontend[0].site_url}/callback"] : [])
  logout_urls       = concat(["http://localhost:5173/"], var.frontend_enabled ? ["${module.frontend[0].site_url}/"] : [])
  mfa_configuration = var.mfa_configuration
}

module "service" {
  source                   = "../lambda-service"
  for_each                 = local.services
  name                     = each.key
  name_prefix              = local.p
  handler                  = each.value.handler
  environment              = merge(local.common_env, each.value.env)
  policy_statements        = each.value.policy
  reserved_concurrency     = var.reserved_concurrency
  log_retention_days       = var.log_retention_days
  permissions_boundary_arn = module.security.permissions_boundary_arn
  tracing_enabled          = var.tracing_enabled
  timeout_seconds          = contains(["ledger-reconciliation", "outbox-reconciliation"], each.key) ? 120 : 10
}

# Synchronous internal calls: only the named callers may invoke the alias.
resource "aws_lambda_permission" "internal" {
  for_each = {
    "account-ledger"   = { caller = "account", callee = "ledger" }
    "transfer-ledger"  = { caller = "transfer", callee = "ledger" }
    "transfer-fraud"   = { caller = "transfer", callee = "fraud" }
    "transfer-account" = { caller = "transfer", callee = "account" }
  }
  statement_id  = "AllowInvokeFrom-${each.value.caller}"
  action        = "lambda:InvokeFunction"
  function_name = module.service[each.value.callee].function_name
  qualifier     = "live"
  principal     = module.service[each.value.caller].role_arn
}

module "api" {
  source                    = "../api-gateway"
  name_prefix               = local.p
  jwt_issuer                = module.identity.issuer
  jwt_audiences             = [module.identity.spa_client_id]
  routes                    = local.routes
  service_alias_invoke_arns = { for k, m in module.service : k => m.alias_invoke_arn }
  service_function_names    = { for k, m in module.service : k => m.function_name }
  cors_allowed_origins      = concat(["http://localhost:5173"], var.frontend_enabled ? [module.frontend[0].site_url] : [])
  throttle_burst            = var.api_throttle_burst
  throttle_rate             = var.api_throttle_rate
  log_retention_days        = var.log_retention_days
}

module "notification_queue" {
  source                = "../queues"
  name_prefix           = local.p
  name                  = "notification"
  eventbridge_rule_arns = [module.event_bus.rule_arns["notification"]]
}

module "audit_queue" {
  source                = "../queues"
  name_prefix           = local.p
  name                  = "audit"
  eventbridge_rule_arns = [module.event_bus.rule_arns["audit"]]
}

module "delivery_dlq" {
  source      = "../queues"
  name_prefix = local.p
  name        = "eventbridge-delivery"
}

module "event_bus" {
  source           = "../event-bus"
  name_prefix      = local.p
  delivery_dlq_arn = module.delivery_dlq.queue_arn
  routes = {
    notification = {
      detail_types = ["CustomerCreated", "AccountCreated", "TransferCompleted", "TransferRejected", "TransferPendingReview", "FraudAlertRaised"]
      queue_arn    = module.notification_queue.queue_arn
    }
    audit = {
      detail_types = [
        "CustomerCreated", "AccountCreated", "OpeningBalancePosted", "TransferRequested", "TransferPendingReview",
        "TransferCompleted", "TransferRejected", "TransferReversed", "FraudScreeningCompleted", "FraudAlertRaised", "ReconciliationCompleted",
      ]
      queue_arn = module.audit_queue.queue_arn
    }
  }
}

resource "aws_lambda_event_source_mapping" "consumer" {
  for_each = {
    notification = module.notification_queue.queue_arn
    audit        = module.audit_queue.queue_arn
  }
  event_source_arn                   = each.value
  function_name                      = module.service[each.key].alias_arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 2
  function_response_types            = ["ReportBatchItemFailures"]
  scaling_config {
    maximum_concurrency = 2
  }
}

module "outbox" {
  source              = "../outbox"
  name_prefix         = local.p
  outbox_stream_arn   = module.dynamodb.outbox_stream_arn
  publisher_alias_arn = module.service["outbox-publisher"].alias_arn
  schedules_enabled   = var.schedules_enabled
  schedules = {
    outbox-reconciliation = {
      expression    = "rate(5 minutes)"
      alias_arn     = module.service["outbox-reconciliation"].alias_arn
      function_name = module.service["outbox-reconciliation"].function_name
    }
    ledger-reconciliation = {
      expression    = "rate(1 hour)"
      alias_arn     = module.service["ledger-reconciliation"].alias_arn
      function_name = module.service["ledger-reconciliation"].function_name
    }
  }
}

module "evidence" {
  source      = "../evidence-store"
  bucket_name = local.evidence_bucket
  writer_role_arns = concat(
    [module.service["audit"].role_arn, module.service["ledger-reconciliation"].role_arn],
    # The GitHub cleanup role must be able to empty the bucket on destroy (T30).
    ["arn:aws:iam::${local.account_id}:role/novabank-github-cleanup"],
    var.evidence_admin_role_arns,
  )
  force_destroy = var.evidence_force_destroy
}

module "frontend" {
  count           = var.frontend_enabled ? 1 : 0
  source          = "../frontend"
  name_prefix     = local.p
  bucket_name     = "${local.p}-site-${local.account_id}"
  csp_connect_src = ["https://*.execute-api.${local.region}.amazonaws.com", "https://*.amazoncognito.com"]
  web_acl_arn     = var.web_acl_arn
}

module "observability" {
  source                    = "../observability"
  name_prefix               = local.p
  region                    = local.region
  api_id                    = module.api.api_id
  function_names            = [for k in keys(local.services) : "${local.p}-${k}"]
  queue_names               = [module.notification_queue.queue_name, module.audit_queue.queue_name]
  dlq_names                 = [module.notification_queue.dlq_name, module.audit_queue.dlq_name, module.delivery_dlq.queue_name]
  stream_failure_queue_name = module.outbox.stream_failure_queue_name
  alert_email               = var.alert_email
}

module "budgets" {
  count               = var.budget_enabled ? 1 : 0
  source              = "../budgets"
  name_prefix         = local.p
  project_tag         = var.project_tag
  monthly_limit_usd   = var.monthly_budget_usd
  notification_emails = var.alert_email == null ? [] : [var.alert_email]
}
