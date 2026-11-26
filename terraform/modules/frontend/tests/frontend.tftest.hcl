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
  name_prefix = "novabank-dev"
  bucket_name = "novabank-dev-site-123456789012"
}

run "private_origin_https_only" {
  command = plan
  assert {
    condition     = aws_s3_bucket_public_access_block.site.block_public_policy && aws_s3_bucket_public_access_block.site.restrict_public_buckets
    error_message = "Frontend bucket must never be public."
  }
  assert {
    condition     = aws_cloudfront_distribution.site.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "CloudFront must redirect HTTP to HTTPS."
  }
  assert {
    condition     = aws_cloudfront_origin_access_control.site.signing_behavior == "always"
    error_message = "Origin Access Control must sign every request."
  }
  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].minimum_protocol_version == "TLSv1.2_2021"
    error_message = "TLS 1.2+ required."
  }
}
