<!-- SPDX-License-Identifier: Apache-2.0 -->
# infra/terraform/

Multi-cloud infrastructure-as-code for the Argus platform.

**Phase 1 status:** stub — version pins and the input-variable contract are
real, but no cloud resources are declared yet. That work lands in **Phase 6
("Terraform multi-cloud deployment")** together with the image-push pipeline,
K8s manifests, and OpenTelemetry / Prometheus / Grafana wiring.

## What's in this directory today

| File | Purpose | Phase 1 state |
|---|---|---|
| `versions.tf` | Terraform + provider version pins (google, google-beta, aws, kubernetes, helm, random) | **real** |
| `variables.tf` | Input-variable contract (cloud, env, region, image tag, GPU toggle, managed-Neo4j toggle, tags) | **real** |
| `terraform.tfvars.example` | Example values; copy to `terraform.tfvars` and fill in | **real** |
| `main.tf` | Root orchestrator — `locals` are populated, module wiring is a commented Phase-6 placeholder | stub |
| `network.tf` | VPC, subnets, firewall / WAF | stub, intent documented |
| `compute.tf` | Managed K8s cluster, default + GPU node pools, cluster addons | stub, intent documented |
| `data.tf` | Managed Neo4j (AuraDB / Marketplace), object storage, vector index | stub, intent documented |
| `iam.tf` | Workload identity (GCP) / IRSA (AWS), least-privilege roles, secret distribution | stub, intent documented |
| `outputs.tf` | Outputs the rest of the platform consumes (api_endpoint, kg_bolt_uri, etc.) | stub, intent documented |

Each stub file carries the Phase-6 scope inline as comments so the
contributor who picks them up has the intended shape in front of them.

## Intended layout (Phase 6)

```
terraform/
├── modules/
│   ├── argus-service/       # cloud-agnostic service module (k8s deployment + svc)
│   ├── kg/                  # managed graph DB selector (AuraDB / self-hosted)
│   └── observability/       # OTEL collector, log sink, metric store
├── envs/
│   ├── gcp/                 # GKE Autopilot, Artifact Registry, Secret Manager
│   ├── aws/                 # EKS, ECR, Secrets Manager
│   └── local/               # kind / minikube for offline parity
├── network.tf  compute.tf  data.tf  iam.tf  outputs.tf
├── main.tf  variables.tf  versions.tf
└── terraform.tfvars.example
```

## Design rules

- **Every resource lives in a reusable module.** Environments compose modules
  with cloud-specific inputs; no resource is declared directly in `envs/`.
- **State lives in the cloud being provisioned.** GCS for GCP envs, S3 +
  DynamoDB for AWS envs. Local env uses local state.
- **Secrets never live in Terraform variables.** They are pulled at runtime
  from the cloud's native secret store via a workload-identity binding.
- **`terraform plan` is mandatory in CI for every PR that touches `infra/`**.
  `apply` is gated by manual approval.

## How to use this in Phase 1

Today, this directory is informational. The contract is:

```bash
# Version-pinning sanity check (requires Terraform >= 1.9.0)
cd infra/terraform
terraform init        # downloads the pinned providers
terraform validate    # validates the empty-but-valid configuration
```

Once Phase 6 lands, `terraform apply` against a populated `terraform.tfvars`
will provision the full stack.
