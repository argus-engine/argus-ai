# SPDX-License-Identifier: Apache-2.0
# ---------------------------------------------------------------------------
# Argus Terraform root configuration — orchestrates the per-resource-group
# files in this directory (network.tf, compute.tf, data.tf, iam.tf).
#
# **Phase 1 status:** STUB. No resources are declared yet.
# **Lands in Phase 6:** the full multi-cloud rollout — see
# `infra/terraform/README.md` for the intended module layout and
# `docs/PROJECT_CONTEXT.md` for the phase plan.
# ---------------------------------------------------------------------------

locals {
  name_prefix = "argus-${var.environment}"

  common_tags = merge(
    var.tags,
    {
      environment = var.environment
      managed_by  = "terraform"
    },
  )
}

# ---------------------------------------------------------------------------
# Cloud-specific module wiring lands here in Phase 6.
#
# module "argus" {
#   source = "./modules/${var.cloud_provider}/argus"
#
#   environment      = var.environment
#   region           = var.region
#   image_tag        = var.argus_image_tag
#   enable_gpu_pool  = var.enable_gpu_pool
#   neo4j_managed    = var.neo4j_managed
#   tags             = local.common_tags
# }
# ---------------------------------------------------------------------------
