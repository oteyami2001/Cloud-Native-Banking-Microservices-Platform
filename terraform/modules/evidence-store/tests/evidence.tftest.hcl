mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-2" }
  }
}

variables {
  bucket_name      = "novabank-dev-evidence-123456789012"
  writer_role_arns = ["arn:aws:iam::123456789012:role/novabank-dev-audit"]
}

run "private_versioned_encrypted" {
  command = plan
  assert {
    condition     = aws_s3_bucket_public_access_block.this.block_public_acls && aws_s3_bucket_public_access_block.this.restrict_public_buckets
    error_message = "Evidence bucket must block public access."
  }
  assert {
    condition     = aws_s3_bucket_versioning.this.versioning_configuration[0].status == "Enabled"
    error_message = "Evidence bucket must be versioned."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.this.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "aws:kms"
    error_message = "Evidence must use SSE-KMS."
  }
  assert {
    condition     = !aws_s3_bucket.this.force_destroy
    error_message = "force_destroy must default to false."
  }
}
