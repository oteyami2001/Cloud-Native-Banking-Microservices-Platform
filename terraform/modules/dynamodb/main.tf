# Banking tables — keys, indexes and streams mirror shared/schema.py
# (kept in sync by tests/terraform/test_schema_parity.py).

terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.70" }
  }
}

locals {
  tables = {
    customers     = { gsis = [], stream = false }
    accounts      = { gsis = [{ name = "GSI1", pk = "GSI1PK", sk = "GSI1SK" }], stream = false }
    ledger        = { gsis = [], stream = false }
    transfers     = { gsis = [{ name = "GSI1", pk = "GSI1PK", sk = "GSI1SK" }], stream = false }
    idempotency   = { gsis = [], stream = false }
    fraud         = { gsis = [{ name = "GSI1", pk = "GSI1PK", sk = "GSI1SK" }], stream = false }
    outbox        = { gsis = [{ name = "PendingIndex", pk = "pending_partition", sk = "pending_since" }], stream = true }
    notifications = { gsis = [{ name = "GSI1", pk = "GSI1PK", sk = "GSI1SK" }], stream = false }
    audit         = { gsis = [], stream = false }
  }
  # Financial system-of-record tables get PITR when enabled.
  financial = toset(["ledger", "transfers", "idempotency", "accounts", "customers", "outbox", "fraud", "audit"])
}

resource "aws_dynamodb_table" "this" {
  #checkov:skip=CKV_AWS_119:AWS owned key by default (BANK-SEC-006); customer managed key via kms_key_arn when approved
  for_each = local.tables

  name                        = "${var.name_prefix}-${each.key}"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "PK"
  range_key                   = "SK"
  deletion_protection_enabled = var.deletion_protection
  stream_enabled              = each.value.stream
  stream_view_type            = each.value.stream ? "NEW_IMAGE" : null

  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }
  dynamic "attribute" {
    for_each = { for a in flatten([for g in each.value.gsis : [g.pk, g.sk]]) : a => a }
    content {
      name = attribute.value
      type = "S"
    }
  }
  dynamic "global_secondary_index" {
    for_each = each.value.gsis
    content {
      name            = global_secondary_index.value.name
      projection_type = "ALL"
      key_schema {
        attribute_name = global_secondary_index.value.pk
        key_type       = "HASH"
      }
      key_schema {
        attribute_name = global_secondary_index.value.sk
        key_type       = "RANGE"
      }
    }
  }

  point_in_time_recovery {
    enabled = var.enable_pitr && contains(local.financial, each.key)
  }

  # AWS owned key by default (no cost); a customer managed key when supplied.
  server_side_encryption {
    enabled     = var.kms_key_arn != null
    kms_key_arn = var.kms_key_arn
  }

  tags = { DataClassification = "synthetic", Table = each.key }
}
