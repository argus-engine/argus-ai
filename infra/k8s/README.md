<!-- SPDX-License-Identifier: Apache-2.0 -->
# infra/k8s/

Kubernetes manifests for the Argus platform.

**Phase 1 status:** stub. Manifests land in Phase 6 together with the Terraform
modules that provision the clusters they run on. Local development uses the
`docker-compose.yml` at the repo root, not k8s.

Intended layout (Phase 6):

```
k8s/
├── base/                      # plain manifests (kustomize base)
└── overlays/
    ├── local/                 # kind / minikube
    ├── gcp/                   # GKE-specific patches
    └── aws/                   # EKS-specific patches
```
