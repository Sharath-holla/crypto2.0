# Local model readiness — October 12, 2026

Observed Windows 11 Home, Ryzen 5 5600H (6 cores / 12 threads), 7.34 GiB usable RAM with approximately 0.73 GiB free at inspection, Radeon RX 6500M reporting approximately 4 GiB VRAM, integrated graphics reporting 0.5 GiB, and 327.5 GiB free on C:. Memory pressure is the immediate constraint. Values are a snapshot, not a sustained inference benchmark.

No `ollama`, `lms` or `llama-server` command was found on PATH; ports 11434 and 1234 were not listening. No installed local model was verified. Only known runtime locations/services were inspected; unrelated personal directories were not searched. Docker CLI exists, but its daemon was unavailable (missing Docker engine pipe). No runtime, model weights or embeddings were installed or downloaded.

| Candidate, exact Ollama tag | Published download | Estimated runtime RAM at a small context | Suggested experiment and limitations |
| --- | --- | --- | --- |
| [qwen3:0.6b](https://ollama.com/library/qwen3:0.6b) | 523 MB, Q4_K_M | Roughly 1–2 GiB | First low-resource instruction/JSON smoke test; very limited reasoning and coding reliability. |
| [qwen2.5-coder:1.5b](https://ollama.com/library/qwen2.5-coder:1.5b) | 986 MB, Q4_K_M | Roughly 2–4 GiB | Small coding/debugging experiment after freeing RAM; planning, tool use and review quality require measurement. |
| [qwen3:1.7b](https://ollama.com/library/qwen3:1.7b) | 1.4 GB, Q4_K_M | Roughly 2–4 GiB | Broader instruction/structured-planning experiment; slower and more demanding than 0.6b, with no reliability claim. |

Download sizes were checked against the official registry. RAM ranges are engineering estimates including runtime/context overhead, not measurements. Start with one logical inference at a time, a 2048-token runtime window and short bounded prompts after installation is explicitly authorized and RAM is freed. A larger advertised model context is not a promise that this machine can run it. Aiventra checks the effective Ollama window before dispatch; a larger project prompt must wait or be reduced, not silently truncated to fit a recommendation.

Use CPU as the initial compatibility baseline. RX 6500M is not listed in Ollama's documented Windows ROCm GPU list; [official GPU documentation](https://docs.ollama.com/gpu) describes Vulkan support for additional hardware. Actual acceleration on this card remains unverified. Do not change drivers or enable a backend as part of this assessment.

These are experiments, not adequate independent enterprise reviewers by assumption. No throughput, quality, benchmark score, real orchestration or successful inference has been observed. Runtime installation and an exact model download require owner authorization. Remote credentials must be entered through encrypted Settings, never recovered from chat; discovery alone does not permit remote inference under ZERO_COST_ONLY.
