terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.70" }
    archive = { source = "hashicorp/archive", version = "~> 2.7" }
  }

  # Partial configuration: bucket/region come from backend.hcl (see
  # backend.hcl.example). Native S3 locking (use_lockfile) — no DynamoDB lock table.
  backend "s3" {
    key          = "novabank/dev/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
