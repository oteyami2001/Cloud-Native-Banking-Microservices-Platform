# Custom event bus for committed domain events, routed to consumer queues.
# Rule ARNs are computed locally so queue policies can reference them without
# a dependency cycle.

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "aws_cloudwatch_event_bus" "this" {
  name = "${var.name_prefix}-events"
}

locals {
  rule_names = { for k, _ in var.routes : k => "${var.name_prefix}-${k}" }
  rule_arns  = { for k, n in local.rule_names : k => "arn:aws:events:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:rule/${aws_cloudwatch_event_bus.this.name}/${n}" }
}

resource "aws_cloudwatch_event_rule" "route" {
  for_each       = var.routes
  name           = local.rule_names[each.key]
  event_bus_name = aws_cloudwatch_event_bus.this.name
  event_pattern = jsonencode({
    source      = ["novabank.banking"]
    detail-type = each.value.detail_types
  })
}

resource "aws_cloudwatch_event_target" "route" {
  for_each       = var.routes
  rule           = aws_cloudwatch_event_rule.route[each.key].name
  event_bus_name = aws_cloudwatch_event_bus.this.name
  arn            = each.value.queue_arn
  retry_policy {
    maximum_event_age_in_seconds = 86400
    maximum_retry_attempts       = 185
  }
  dead_letter_config {
    arn = var.delivery_dlq_arn
  }
}

# Retain everything for replay during incident recovery (low volume, low cost).
resource "aws_cloudwatch_event_archive" "this" {
  name             = "${var.name_prefix}-archive"
  event_source_arn = aws_cloudwatch_event_bus.this.arn
  retention_days   = var.archive_retention_days
}
