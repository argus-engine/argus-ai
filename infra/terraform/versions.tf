# SPDX-License-Identifier: Apache-2.0
# ---------------------------------------------------------------------------
# Terraform + provider version constraints for the Argus multi-cloud stack.
#
# This is the one file in infra/terraform/ that is real and useful in
# Phase 1 — the rest are Phase 6 stubs, but pinning provider versions now
# means anyone who runs `terraform init` against this directory gets a
# deterministic provider set when the resources land.
# ---------------------------------------------------------------------------

terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Backend stays local in Phase 1. Production environments override this
  # in their own `envs/<env>/backend.tf` to point at GCS (for the GCP env)
  # or S3 + DynamoDB (for the AWS env).
}
