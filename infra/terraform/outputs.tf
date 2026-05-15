# SPDX-License-Identifier: Apache-2.0
# ---------------------------------------------------------------------------
# Outputs surfaced by the root configuration.
#
# **Phase 1 status:** STUB. No outputs declared yet — they materialize when
# the resources in network.tf / compute.tf / data.tf / iam.tf do, in Phase 6.
#
# **Planned outputs (Phase 6):**
#   - api_endpoint        : public URL of the Argus API
#   - kg_bolt_uri         : Bolt URI for the knowledge-graph backend
#   - data_bucket_name    : name of the object-storage bucket
#   - cluster_name        : Kubernetes cluster identifier (for kubectl)
#   - cluster_endpoint    : k8s API server endpoint
#   - cluster_ca_cert     : k8s cluster CA certificate (sensitive)
#   - workload_identity_*: service-identity bindings, one per workload
# ---------------------------------------------------------------------------
