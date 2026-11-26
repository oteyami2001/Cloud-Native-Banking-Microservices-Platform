# GitHub Actions OIDC federation with separate least-privilege roles.
#
# * plan     — read-only; usable from pull requests of THIS repository only.
# * apply    — Terraform apply; only from the protected "dev" environment.
# * deploy   — publish Lambda versions, move aliases, sync the frontend bucket;
#              only from the protected environment.
# * cleanup  — terraform destroy; only from the protected "cleanup" environment.
#
# An existing account-level GitHub OIDC provider is reused when its ARN is
# supplied (an account can have only one provider per URL).

data "aws_caller_identity" "current" {}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.existing_oidc_provider_arn == null ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"] # ignored by AWS for this provider; required by older APIs
}

locals {
  provider_arn = coalesce(var.existing_oidc_provider_arn, try(aws_iam_openid_connect_provider.github[0].arn, null))
  # GitHub may issue subjects in the immutable-ID format
  # "repo:<owner>@<owner_id>/<name>@<repo_id>:..." (observed for this repository
  # via CloudTrail, 2026-11-26). When IDs are supplied only that exact form is
  # trusted, so a renamed or re-created repository cannot assume the roles.
  repo_parts = split("/", var.github_repository)
  repo = (var.github_owner_id != null && var.github_repository_id != null
    ? "repo:${local.repo_parts[0]}@${var.github_owner_id}/${local.repo_parts[1]}@${var.github_repository_id}"
  : "repo:${var.github_repository}")
  roles = {
    plan    = ["${local.repo}:pull_request", "${local.repo}:ref:refs/heads/main", "${local.repo}:environment:${var.plan_environment}"]
    apply   = ["${local.repo}:environment:${var.apply_environment}"]
    deploy  = ["${local.repo}:environment:${var.apply_environment}"]
    cleanup = ["${local.repo}:environment:${var.cleanup_environment}"]
  }
}

data "aws_iam_policy_document" "trust" {
  for_each = local.roles
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = each.value
    }
  }
}

resource "aws_iam_role" "github" {
  for_each             = local.roles
  name                 = "${var.name_prefix}-github-${each.key}"
  assume_role_policy   = data.aws_iam_policy_document.trust[each.key].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.github["plan"].name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "state" {
  statement {
    sid       = "StateBucket"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.state_bucket}"]
  }
  statement {
    sid       = "StateObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.state_bucket}/${var.state_key_prefix}*"]
  }
}

resource "aws_iam_role_policy" "state" {
  for_each = toset(["apply", "cleanup"])
  name     = "terraform-state"
  role     = aws_iam_role.github[each.key].id
  policy   = data.aws_iam_policy_document.state.json
}

# The plan role is reachable from pull requests, so it may READ state but only
# write/delete the native S3 lock objects (<key>.tflock) that a plan creates.
data "aws_iam_policy_document" "state_plan" {
  statement {
    sid       = "StateBucket"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.state_bucket}"]
  }
  statement {
    sid       = "ReadState"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.state_bucket}/${var.state_key_prefix}*"]
  }
  statement {
    sid       = "LockFilesOnly"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.state_bucket}/${var.state_key_prefix}*.tflock"]
  }
  # ReadOnlyAccess would otherwise allow reading every S3 object in the account
  # (including other projects' Terraform state). Plans only need bucket
  # configuration, never object contents outside this project's state.
  statement {
    sid           = "DenyObjectReadsOutsideProjectState"
    effect        = "Deny"
    actions       = ["s3:GetObject", "s3:GetObjectVersion"]
    not_resources = ["arn:aws:s3:::${var.state_bucket}/${var.state_key_prefix}*"]
  }
}

resource "aws_iam_role_policy" "state_plan" {
  name   = "terraform-state-read"
  role   = aws_iam_role.github["plan"].id
  policy = data.aws_iam_policy_document.state_plan.json
}

# Apply/cleanup need broad create rights on project resources. They are
# constrained to project-named resources and the region, and denied the ability
# to touch the OIDC provider or the bootstrap state bucket itself.
data "aws_iam_policy_document" "apply" {
  statement {
    sid = "ProjectServices"
    actions = [
      "apigateway:*", "cognito-idp:*", "dynamodb:*", "events:*", "lambda:*", "logs:*", "sqs:*", "sns:*",
      "s3:*", "cloudfront:*", "cloudwatch:*", "budgets:*", "xray:*", "cloudtrail:DescribeTrails", "cloudtrail:GetTrailStatus",
    ]
    resources = ["*"]
    condition {
      test     = "StringEqualsIfExists"
      variable = "aws:RequestedRegion"
      values   = [var.region, "us-east-1"] # CloudFront/Budgets are global (us-east-1)
    }
  }
  statement {
    sid = "ProjectRoles"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:TagRole", "iam:UntagRole", "iam:UpdateAssumeRolePolicy",
      "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
      "iam:PutRolePermissionsBoundary", "iam:CreatePolicy", "iam:DeletePolicy", "iam:GetPolicy", "iam:GetPolicyVersion",
      "iam:ListPolicyVersions", "iam:CreatePolicyVersion", "iam:DeletePolicyVersion", "iam:ListInstanceProfilesForRole", "iam:TagPolicy",
    ]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.name_prefix}-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.name_prefix}-*",
    ]
  }
  statement {
    sid       = "PassOnlyProjectRolesToLambda"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.name_prefix}-*"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }
  statement {
    sid       = "ProtectStateBucketConfiguration"
    effect    = "Deny"
    actions   = ["s3:DeleteBucket", "s3:PutBucketPolicy", "s3:PutBucketVersioning", "s3:PutEncryptionConfiguration"]
    resources = ["arn:aws:s3:::${var.state_bucket}"]
  }
  statement {
    sid       = "ProtectGitHubRoles"
    effect    = "Deny"
    actions   = ["iam:*"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.name_prefix}-github-*"]
  }
}

resource "aws_iam_role_policy" "apply" {
  for_each = toset(["apply", "cleanup"])
  name     = "project-infrastructure"
  role     = aws_iam_role.github[each.key].id
  policy   = data.aws_iam_policy_document.apply.json
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid = "PublishLambdaReleases"
    actions = [
      "lambda:UpdateFunctionCode", "lambda:PublishVersion", "lambda:UpdateAlias", "lambda:GetAlias",
      "lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:ListVersionsByFunction",
    ]
    resources = ["arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:${var.name_prefix}-*"]
  }
  statement {
    sid       = "ArtifactBucket"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.artifact_bucket}", "arn:aws:s3:::${var.artifact_bucket}/*"]
  }
  statement {
    sid     = "FrontendSync"
    actions = ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    # Site buckets are named <prefix>-<env>-site-<account>, e.g. novabank-dev-site-123456789012.
    resources = ["arn:aws:s3:::${var.name_prefix}-*-site-*", "arn:aws:s3:::${var.name_prefix}-*-site-*/*"]
  }
  statement {
    sid       = "FrontendInvalidate"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = ["arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/*"]
  }
  statement {
    sid       = "RunOperationalJobs"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:${var.name_prefix}-*-ledger-reconciliation:live"]
  }
  # Per-version Lambda error metrics drive automatic rollback. GetMetricData has
  # no resource-level permissions, so "*" is required (read-only).
  statement {
    sid       = "ReadMetricsForRollback"
    actions   = ["cloudwatch:GetMetricData"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy"
  role   = aws_iam_role.github["deploy"].id
  policy = data.aws_iam_policy_document.deploy.json
}
