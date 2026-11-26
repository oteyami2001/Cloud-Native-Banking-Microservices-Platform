# Bootstrap (applied once, manually, with local state — docs/bootstrap-runbook.md):
#   * encrypted, versioned Terraform state bucket with native S3 locking
#   * private, versioned artifact bucket for immutable Lambda packages
#   * GitHub OIDC roles (plan / apply / deploy / cleanup)
# Separated from workload state so destroying the workload never removes the
# state or CI identity.

terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.70" }
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.expected_account_id]
  default_tags {
    tags = { Project = var.project_tag, Environment = "bootstrap", ManagedBy = "terraform" }
  }
}

locals {
  state_bucket    = "novabank-tfstate-${var.expected_account_id}-${var.region}"
  artifact_bucket = "novabank-artifacts-${var.expected_account_id}-${var.region}"
}

resource "aws_s3_bucket" "b" {
  for_each = { state = local.state_bucket, artifacts = local.artifact_bucket }
  bucket   = each.value
}

resource "aws_s3_bucket_public_access_block" "b" {
  for_each                = aws_s3_bucket.b
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "b" {
  for_each = aws_s3_bucket.b
  bucket   = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "b" {
  for_each = aws_s3_bucket.b
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "b" {
  for_each = aws_s3_bucket.b
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "b" {
  for_each = aws_s3_bucket.b
  bucket   = each.value.id
  rule {
    id     = "noncurrent-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

data "aws_iam_policy_document" "tls_only" {
  for_each = aws_s3_bucket.b
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [each.value.arn, "${each.value.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "b" {
  for_each   = aws_s3_bucket.b
  bucket     = each.value.id
  policy     = data.aws_iam_policy_document.tls_only[each.key].json
  depends_on = [aws_s3_bucket_public_access_block.b]
}

module "github_oidc" {
  source                     = "../modules/iam-oidc"
  name_prefix                = "novabank"
  region                     = var.region
  github_repository          = var.github_repository
  existing_oidc_provider_arn = var.existing_oidc_provider_arn
  state_bucket               = local.state_bucket
  artifact_bucket            = local.artifact_bucket
}
