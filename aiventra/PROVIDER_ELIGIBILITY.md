# Provider eligibility

Current enforcement: [ZERO_COST_AI_POLICY.md](ZERO_COST_AI_POLICY.md).

| State | Meaning | Inference permitted |
| --- | --- | --- |
| DETERMINISTIC_TEST | Explicit fixture, no live model | Fixture only |
| LOCAL_AVAILABLE | Recently inspected installed GGUF; rechecked on each call | Trusted local Ollama only |
| PAID_BLOCKED | Positive registered token price | No |
| UNKNOWN_COST_BLOCKED | Missing zero-billing proof, stale local proof or cloud alias | No |
| PROVIDER_UNAVAILABLE | Disabled configuration or unavailable local metadata | No |

VERIFIED_FREE / VERIFIED_FREE_LIMITED, QUOTA_EXHAUSTED, CREDENTIAL_INVALID and CAPABILITY_UNSUPPORTED are future entitlement-verifier classifications, not fabricated account facts. Existing gateway capability/context/quality/data-sensitivity checks still apply in addition to spending policy. No external provider is currently approved for inference under this policy.

Owner UI: Models & providers → Zero-cost inference policy. Local verification reads tags/show metadata without inference or downloads. Resume saved work queues only an eligible, unexpired, reconciled workflow. Rejections retain saved work and display the backend error.

No provider keys were installed or used during this milestone. Credentials disclosed in chat must be revoked/replaced before any later provider connection.
