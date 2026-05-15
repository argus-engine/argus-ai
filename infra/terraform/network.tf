# SPDX-License-Identifier: Apache-2.0
# ---------------------------------------------------------------------------
# Network resources — VPC, subnets, firewall / security groups, NAT.
#
# **Phase 1 status:** STUB. No resources declared yet.
# **Phase 6 scope:**
#   - Single private VPC with a /16 CIDR per region
#   - Three subnets: public (load balancer ingress only), private (workloads),
#     restricted (managed-DB peering only — no public egress)
#   - Cloud NAT (GCP) / NAT gateway (AWS) for outbound from private workloads
#   - Firewall rules:
#       * deny-all default
#       * allow ingress 443 → LB
#       * allow internal pod-to-pod
#       * allow internal pod-to-Neo4j (Bolt 7687) within restricted subnet
#   - Cloud Armor / WAF in front of the public LB
#   - VPC flow logs streamed to the Phase 6 observability stack
# ---------------------------------------------------------------------------
