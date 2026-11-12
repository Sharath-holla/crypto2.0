# API and integration reference

FastAPI exposes current schemas through `/openapi.json` and Swagger `/docs`. Obtain a local token with `POST /auth/login` and use `Authorization: Bearer <token>` for business endpoints. The Next.js proxy handles this through a private HttpOnly cookie; provider credentials never pass through it.

| Operation | Endpoint |
|---|---|
| Local authentication/revocation | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Health | `GET /health`, `/health/live`, `/health/ready` |
| Scoped client consulting | `POST /requirements`, `GET /requirements/{id}`, `POST /requirements/{id}/clarify` |
| Evidence | `POST /requirements/{id}/upload`, `POST /requirements/{id}/research` |
| Exact proposal approval | `POST /proposals/{id}/approve` |
| Reject/request changes | `POST /proposals/{id}/decision` |
| Owner snapshot | `GET /state` |
| Workforce | `PATCH /agents/{id}`, `POST /agents/{id}/clone` |
| Providers/models | `POST /providers`, `POST /models`, `PATCH /providers/{id}` |
| Company/project control | `POST /controls`, `PATCH /projects/{id}` |
| Finance | `PATCH /budgets/{id}`, `POST /runs/{id}/reconcile` |
| Engineering | `POST /repositories`, `POST /projects/{id}/coding`, `POST /tasks/{id}/approve` |
| Task/artifact | `POST /projects/{id}/tasks`, `POST /tasks/{id}/cancel`, `GET /artifacts/{id}` |
| Project keyword memory | `GET /memory/search?project_id=...&query=...` |
| Business/client records | `POST /records`, `PATCH /records/{id}`, `POST /clients` |
| Owner commands | `POST /chat` |
| Watchdog/notifications | `POST /monitoring/inspect`, `POST /notifications/{id}/ack` |
| Messages | `POST /messages/{id}/ack` |
| Recovery | `POST /workflows/{id}/retry` |
| Integrity | `GET /audit/verify` |
| Optional workforce | `POST /crypto/activate` |
| External action boundary | `POST /projects/{id}/deploy` currently rejects every deployment |
| Change feed | `GET /events` authenticated SSE, scoped organization revision |

The browser refreshes snapshots every five seconds; direct authenticated SSE is available to API clients. Snapshot collections are currently capped at 300 rows and detailed pagination/search endpoints are pending. Do not expose admin endpoints or runner sockets publicly.

Optimistic writes require the current revision/version. Stale changes return 409. Proposal/coding approvals require exact SHA-256 hashes generated from canonical sorted-key JSON. Proposal repeats with the same selected alternative return the existing project. Changed selections require scope revision.

Full API schema is the authoritative field reference. Monetary fields ending `_micro` are integer USD millionths. All estimates are explicitly labeled; successful HTTP responses do not imply live certification or provider invoicing.

Local JWTs must refer to an existing, unexpired and unrevoked session. Correlation IDs are returned in `X-Request-ID`. Readiness checks migration and worker; registry status only asserts configuration, not live access. Coding input supports `review_policy` and `review_count`, both bound into the repository-change approval hash.
