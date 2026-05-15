# SPDX-License-Identifier: Apache-2.0
# ---------------------------------------------------------------------------
# Data-plane resources — knowledge graph, object storage, vector index.
#
# **Phase 1 status:** STUB. No resources declared yet.
# **Phase 6 scope:**
#   - Knowledge graph (Phase 2 dependency):
#       * If var.neo4j_managed = true:
#           - GCP → Neo4j AuraDB instance (Professional tier in prod)
#           - AWS → Neo4j Enterprise via AWS Marketplace
#       * Otherwise: self-hosted Neo4j StatefulSet in the workload cluster,
#         backed by a Persistent Volume Claim against the regional disk class
#   - Object storage for downloaded datasets and model artifacts:
#       * GCP → google_storage_bucket "argus-${var.environment}-data"
#               with uniform bucket-level access + versioning
#       * AWS → aws_s3_bucket with the same naming + versioning, plus
#               aws_s3_bucket_public_access_block locking down ACL access
#   - Vector index for Phase 4 RAG retrieval (deferred decision — likely
#     pgvector on managed Postgres, or a managed Pinecone instance with
#     the cost gate in front)
#   - Backup policy:
#       * Daily snapshot of the Neo4j DB to a separate bucket / replica
#       * 30-day retention by default; staging + prod override per env
# ---------------------------------------------------------------------------
