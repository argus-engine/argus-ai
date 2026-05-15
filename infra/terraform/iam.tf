# SPDX-License-Identifier: Apache-2.0
# ---------------------------------------------------------------------------
# Identity, access management, and secret distribution.
#
# **Phase 1 status:** STUB. No resources declared yet.
# **Phase 6 scope:**
#   - Service identities:
#       * GCP: workload identity binding so each k8s ServiceAccount in the
#         argus namespace authenticates as a dedicated google_service_account
#         (no long-lived JSON keys mounted into the cluster)
#       * AWS: IRSA — IAM Roles for Service Accounts, trust relationship to
#         the EKS OIDC provider
#   - Least-privilege role grants:
#       * argus-api          → read/write on the data bucket; read on the
#                               KG instance; nothing else
#       * argus-ingestion    → write on the data bucket only; outbound to
#                               public APIs (Kaggle / GDELT / EDGAR)
#       * argus-reviewer     → read on the data bucket + KG + RAG vector
#                               index; write on the disagreements stream
#   - Secret distribution:
#       * Secrets land in Secret Manager (GCP) / Secrets Manager (AWS) and
#         are mounted into pods via CSI driver (never via env vars baked
#         into the image — see `docs/responsible_ai.md` governance posture)
#       * `kaggle.json` and OpenAI API key are the two Phase-1-known
#         secrets; others surface as their consumers land
#   - Audit trail:
#       * Cloud-native audit logs forwarded to the observability stack
#       * All IAM changes require a `terraform apply` PR review per
#         `docs/architecture.md` design principle "every external dep is
#         pluggable" — and access is one such dep
# ---------------------------------------------------------------------------
