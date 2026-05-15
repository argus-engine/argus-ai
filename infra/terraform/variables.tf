# SPDX-License-Identifier: Apache-2.0
# ---------------------------------------------------------------------------
# Input variables for the Argus multi-cloud Terraform configuration.
#
# These are declared in Phase 1 so the eventual Phase 6 module wiring has a
# stable contract. Defaults are conservative; staging / production envs
# override via `terraform.tfvars` (see `terraform.tfvars.example`).
# ---------------------------------------------------------------------------

variable "cloud_provider" {
  description = "Which cloud to deploy to: `gcp` or `aws`. Selects the matching module under modules/."
  type        = string
  validation {
    condition     = contains(["gcp", "aws"], var.cloud_provider)
    error_message = "cloud_provider must be \"gcp\" or \"aws\"."
  }
}

variable "environment" {
  description = "Deployment environment: `local`, `dev`, `staging`, `prod`."
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["local", "dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: local, dev, staging, prod."
  }
}

variable "region" {
  description = "Primary cloud region. e.g. `europe-west2` (GCP) or `eu-west-2` (AWS)."
  type        = string
}

variable "project_id" {
  description = "GCP project ID. Required when cloud_provider = \"gcp\"."
  type        = string
  default     = null
}

variable "aws_account_id" {
  description = "AWS account ID. Required when cloud_provider = \"aws\"."
  type        = string
  default     = null
}

variable "argus_image_tag" {
  description = "Docker image tag to deploy. Defaults to `latest` for local + dev; pinned for staging + prod."
  type        = string
  default     = "latest"
}

variable "enable_gpu_pool" {
  description = "Whether to provision a GPU-capable node pool for the predictive head (Phase 3)."
  type        = bool
  default     = false
}

variable "neo4j_managed" {
  description = "Use the cloud's managed Neo4j (AuraDB on GCP, AWS Marketplace listing on AWS) instead of self-hosting."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Common tags / labels applied to every resource that supports them."
  type        = map(string)
  default = {
    project = "argus"
    owner   = "platform"
  }
}
