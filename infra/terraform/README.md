<!-- SPDX-License-Identifier: Apache-2.0 -->
# infra/terraform/

Multi-cloud infrastructure-as-code for the Argus platform.

**Phase 1 status:** stub. No Terraform resources are declared yet — that
work lands in Phase 6 ("Terraform multi-cloud deployment") together with image
push, K8s manifests, and OpenTelemetry / Prometheus / Grafana wiring.

## Intended layout (Phase 6)

```
terraform/
├── modules/
│   ├── argus-service/         # cloud-agnostic service module (k8s deployment + svc)
│   ├── kg/                    # managed graph DB selector (Neo4j AuraDB / self-hosted)
│   └── observability/         # OTEL collector, log sink, metric store
├── envs/
│   ├── gcp/                   # GKE Autopilot, Artifact Registry, Secret Manager
│   ├── aws/                   # EKS, ECR, Secrets Manager
│   └── local/                 # kind / minikube for offline parity
└── README.md
```

## Design rules

- **Every resource lives in a reusable module.** Environments compose modules
  with cloud-specific inputs; no resource is declared directly in `envs/`.
- **State lives in the cloud being provisioned.** GCS for GCP envs, S3 + DynamoDB
  for AWS envs. Local env uses local state.
- **Secrets never live in Terraform variables.** They are pulled at runtime
  from the cloud's native secret store via a workload-identity binding.
- **`terraform plan` is mandatory in CI for every PR that touches `infra/`**.
  `apply` is gated by manual approval.
