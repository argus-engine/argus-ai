# SPDX-License-Identifier: Apache-2.0
"""FastAPI service layer.

The API is a thin HTTP shell over the platform: it composes the lower layers,
serializes inputs and outputs against the same Pydantic schemas the rest of the
platform uses, and exposes `/health`, `/predict`, `/explain`, and the HITL
endpoints. No business logic lives here — moving logic into the API in order
to "make it faster" is a layering violation.

**Phase 1 surface:** placeholder app exposing `/health` only, so the
docker-compose stack has something to point Streamlit at end-to-end.

**Lands in later phases:**

- `/predict` route (Phase 3, exposing `UncertainPrediction`)
- `/explain` route (Phase 4, attaching RAG-grounded evidence)
- HITL review endpoints (Phase 5)
- OpenTelemetry instrumentation (Phase 6)
- Auth provider gate (deferred per decision G — lands no earlier than Phase 5)
"""
