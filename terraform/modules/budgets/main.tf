# Monthly cost budget filtered on the Project tag. A budget is an ALERT, not a
# spending cap. Requires the Project tag to be activated as a cost allocation tag.

resource "aws_budgets_budget" "project" {
  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.monthly_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = [format("user:Project$%s", var.project_tag)]
  }

  dynamic "notification" {
    for_each = var.notification_emails == [] ? [] : [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.notification_emails
    }
  }

  dynamic "notification" {
    for_each = var.notification_emails == [] ? [] : [1]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 100
      threshold_type             = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = var.notification_emails
    }
  }
}
