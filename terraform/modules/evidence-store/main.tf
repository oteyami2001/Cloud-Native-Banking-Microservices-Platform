# Audit evidence bucket: private, versioned, SSE-KMS (AWS managed key with
# bucket keys), TLS-only, writes restricted to the audit and reconciliation
# roles. Object Lock is OFF by default: it would block cleanup (ADR-0012).

resource "aws_s3_bucket" "this" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    id     = "evidence-retention"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_retention_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
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
  statement {
    sid       = "DenyUnencryptedWrites"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }
  statement {
    sid       = "OnlyEvidenceWritersMayWrite"
    effect    = "Deny"
    actions   = ["s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.this.arn}/evidence/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "ArnNotLike"
      variable = "aws:PrincipalArn"
      values   = var.writer_role_arns
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket     = aws_s3_bucket.this.id
  policy     = data.aws_iam_policy_document.bucket.json
  depends_on = [aws_s3_bucket_public_access_block.this]
}
