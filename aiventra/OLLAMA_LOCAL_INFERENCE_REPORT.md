# Phase 6.1 local AI verification

Date: October 12, 2026. Starting repository HEAD: 73706be3db8da3fb5087884cb15078447ff99be3. Scope: existing official Ollama and **qwen3:0.6b only**; no other runtime/model, paid inference, generated PR or deployment is authorized.

## Observed hardware and service

Windows 11 Home Single Language; Ryzen 5 5600H, six cores/twelve logical processors; 7.34 GiB usable RAM; Radeon RX 6500M reports approximately 4 GiB VRAM, integrated Radeon approximately 0.5 GiB; system drive approximately 322 GiB free. These adapter-memory figures do not establish available VRAM or actual inference acceleration. No GPU utilization/CPU inference claim can be made without running a model.

The official existing Ollama executable reports **0.40.3**. The user PATH already includes its installation directory; this task's inherited PATH was stale, so the verified executable path was used without reinstalling or changing the global PATH. Only verified Ollama processes were restarted. Cloud was disabled using the official server configuration and `OLLAMA_NO_CLOUD=1`; the restarted server log confirms cloud disabled. It listens only on **127.0.0.1:11434**, with one concurrent request, one loaded model, 2048 default context and zero keep-alive. Prior named settings were saved privately for recovery. Other applications/security controls/drivers were not modified.

Live GET verification of `/api/version`, `/api/tags` and `/api/ps` succeeded. Both installed and loaded model lists were empty. A genuine owner-registered credential-free Ollama provider is persisted in active SQLite through the authenticated existing API; no fake Qwen catalog row was inserted. Model discovery succeeded with zero model rows. Read-only status accurately reports the low-RAM warning and invokes no inference.

## Resource stop and actual inference counts

Before download, available RAM fluctuated around **0.55–1.13 GiB**, including about 1.03 GiB after stopping only Aiventra's managed services. The owner specification explicitly says to stop before download under unsafe resource shortage. The task requested that the owner free roughly 2 GiB by closing unneeded applications/tabs; no reply or sufficient resource improvement has been observed. Unrelated user processes were not terminated. Regression tests use controlled adapters and separate SQLite databases, and are scheduled conservatively.

**Downloads: zero. Actual inference requests: zero. Successful/failed live model requests: zero/zero.** Model digest/size, tokens, inference latency, throughput, peak inference memory, CPU/GPU utilization, live benchmark validity and Qwen suitability are **not measured**. No actual Lead → BA → CTO handoff or live planning artifact exists from this increment. No production-readiness, independent-model QA, client delivery or generated-PR claim is made.

The local application sets `OLLAMA_MIN_AVAILABLE_MEMORY_MB=1536`, `OLLAMA_THINKING=false`, keep-alive zero and one scheduler worker. Unknown or lower available RAM blocks before inference. This does not replace monitoring during a real bounded run. The configured application context limit remains 8192; its conservative gateway token reservation can exceed a direct 2048-context smoke test. Preserve that admission policy and strict schemas.

## Implemented and controlled verification

The existing provider/gateway/native transport and catalog were extended, not replaced: credential-free registration, owner/tenant-scoped read-only diagnostics, installed metadata/context display, RAM admission, explicit no-thinking requests, reported-model/completion verification and persisted timing/throughput. Requested/selected/attempted/successful models are distinct. Mismatched/malformed identity cannot become accepted live evidence. Fixture tests cover valid/invalid structured output, incomplete responses, native streams, private-thinking exclusion, local-only URLs, unavailable service, resource denial before network, registration and diagnostics authorization, and receipt persistence after SQLite reconnect. Existing cancellation, bounded retries, budgets, project scope, approvals and runner security remain under regression coverage.

TEST_REPORT.md holds exact final test and CI observations. Controlled protocol/response tests are **fixture-tested**, not real Qwen inference. The private browser backend prohibits outbound HTTP, including the owner's Ollama daemon; its unavailable state tests genuine backend/UI integration under that fence.

Final source **ed065c839c1aae56d496a0a1ab187bb995d676c6**: [all six CI jobs passed](https://github.com/Sharath-holla/Aiventra/actions/runs/38241398273), **458 backend / 69 browser checks**, production build/types/audits, restricted Docker execution/recovery and PostgreSQL transfer/restart/separate restoration. Earlier browser failures were corrected and rechecked; TEST_REPORT.md retains that history. Live inference counts remain zero. Missing cached embedding weights were reported without download; real embedding quality is not established by deterministic memory fixtures.

## Actual application restart and preservation

The managed API, worker and Next.js application were restarted. Ollama provider ID **0b224d8a-0dfc-4fde-acfa-33f1c20f0b34** was reused without duplicate registration; live version/tags/status checks still show 0.40.3 and zero installed models. The previous GPT-6.1 Sol preference and single selection-history entry remain. Its earlier Phase 6 workflow has naturally expired into **needs_attention**, reason **Provider wait exceeded workflow deadline**, step zero and zero runs. An older helper expecting an unexpired waiting state failed, prompting inspection of actual scoped evidence; no workflow/deadline was reset or falsely claimed resumed. A fresh explicitly selected disposable Qwen test draft should be used after safe model availability.

Every original **49,679 row ID** remains present across 57 tables; SQLite integrity is OK and foreign-key violations zero. The append-only audit verifies **4,395 events**. These are active SQLite observations, not a PostgreSQL cutover. Next.js reports ready on port 3000 and the API readiness endpoint passes. The actual owner browser tab retains a cached connection-error page; browser URL policy refuses binding that page. Manual reload was requested. This check remains pending; it was not bypassed with another browser or indirect page inspection. Private browser tests remain separately observed evidence.

## Resume after resources are safe

Recheck RAM and installed tags; pull only `qwen3:0.6b` through the verified existing runtime if absent. Record exact digest/size. Run one small CLI prompt and one bounded HTTP request (2048 context, ≤128 output tokens, thinking off, immediate unload); measure resources and stop under pressure. Reconcile the actual registry through existing discovery, then run existing gateway/probe/structured validation, six modest evaluation cases and the bounded logical Lead → BA → CTO handoff. Keep GPT-6.1 Sol globally preferred; explicitly select Qwen only in the disposable project. Save real outputs/receipts, verify restart persistence and classify capability conservatively. Do not weaken validators, bypass context bounds, silently install another model or label shared-model work independent QA.

Official references: [Ollama configuration/cloud controls](https://docs.ollama.com/faq), [generate API](https://docs.ollama.com/api/generate), [chat API](https://docs.ollama.com/api/chat), [authorized Qwen model](https://ollama.com/library/qwen3:0.6b). Advertised package size is not an observed local installation size.
