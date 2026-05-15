# SPDX-License-Identifier: Apache-2.0
# ---------------------------------------------------------------------------
# Compute resources — Kubernetes cluster, node pools, autoscaling.
#
# **Phase 1 status:** STUB. No resources declared yet.
# **Phase 6 scope:**
#   - Managed Kubernetes:
#       * GCP: GKE Autopilot (preferred — workload identity baked in)
#       * AWS: EKS with managed node groups + IAM Roles for Service Accounts
#   - Default node pool: spot / preemptible, autoscaling 2..10 nodes
#   - GPU node pool (gated by var.enable_gpu_pool):
#       * GCP: nvidia-tesla-t4 minimum, taint nvidia.com/gpu=present:NoSchedule
#       * AWS: g4dn.xlarge or g5.xlarge
#       * Surfaced to the predictive head's Deployment as a nodeSelector +
#         toleration matching the taint
#   - Cluster-level addons:
#       * cert-manager (TLS for ingress)
#       * external-dns (managed-zone records for *.argus.<env>.<domain>)
#       * OpenTelemetry Operator (Phase 6 observability)
#   - The Argus image itself is deployed via the in-cluster Helm release
#     produced by `modules/argus-service/`, not declared here.
# ---------------------------------------------------------------------------
