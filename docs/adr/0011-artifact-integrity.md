# ADR-0011: Artifact integrity

* Status: Accepted · Date: 2026-11-26

## Decision
`scripts/build_lambda.py` produces deterministic zips (fixed timestamps,
sorted entries) per service with a SHA-256 manifest. The build workflow adds a
CycloneDX SBOM and GitHub build-provenance attestations. Deployment verifies
manifest checksums and attestations **before** uploading to an S3 key named by
the hash, then publishes immutable Lambda versions. Terraform plans are
applied only after verifying the plan checksum and source commit.
Lambda code signing (AWS Signer) is a documented future enhancement.
