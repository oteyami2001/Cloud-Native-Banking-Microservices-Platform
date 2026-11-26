# NEGATIVE FIXTURE — deliberately insecure. Never applied.
# security-scan.yml asserts that Checkov FAILS on this directory (scenario T25).
resource "aws_s3_bucket" "public" {
  bucket = "novabank-insecure-fixture"
}

resource "aws_s3_bucket_public_access_block" "public" {
  bucket                  = aws_s3_bucket.public.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_dynamodb_table" "no_pitr" {
  name         = "novabank-insecure-ledger"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  attribute {
    name = "PK"
    type = "S"
  }
}

data "aws_iam_policy_document" "admin" {
  statement {
    actions   = ["*"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "admin" {
  name   = "novabank-insecure-admin"
  policy = data.aws_iam_policy_document.admin.json
}
