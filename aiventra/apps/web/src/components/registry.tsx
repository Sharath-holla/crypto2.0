"use client";
import { useEffect, useState } from "react";
import { Cpu, Plus, Server } from "lucide-react";
import { api, money } from "@/lib/api";
import { Badge, Button, Empty, Panel, useApp } from "./common";
import { ModelPolicyForm, ProviderControls } from "./provider-controls";
import { NativeExecution } from "./native-execution";
import { FreeModels } from "./free-models";
import { ModelCatalog } from "./model-catalog";
export function Registry() {
  const { state, run, busy } = useApp();
  const [tab, setTab] = useState("models");
  const [show, setShow] = useState(false);
  const [focusProvider, setFocusProvider] = useState("");
  useEffect(() => {
    if (tab === "providers" && focusProvider)
      document
        .getElementById(`provider-config-${focusProvider}`)
        ?.scrollIntoView({ block: "start" });
  }, [tab, focusProvider]);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("openai");
  const [url, setUrl] = useState("https://api.openai.com/v1");
  const [credential, setCredential] = useState("OPENAI_API_KEY");
  const [provider, setProvider] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [quality, setQuality] = useState("70");
  const [context, setContext] = useState("32768");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [source, setSource] = useState("");
  const [capabilities, setCapabilities] = useState("structured,reasoning");
  const [sensitivity, setSensitivity] = useState("internal");
  return (
    <>
      <ModelCatalog
        connect={(providerId) => {
          setTab("providers");
          setShow(!providerId);
          setFocusProvider(providerId || "");
        }}
        configure={(providerId, modelId) => {
          setProvider(providerId);
          setIdentifier(modelId);
          setTab("models");
          setShow(true);
          const existing = state.models.find(
            (m) => m.provider_id === providerId && m.identifier === modelId,
          );
          if (existing) {
            setQuality(String(existing.quality));
            setContext(String(existing.context_tokens || 32768));
            setCapabilities(existing.capabilities.join(","));
            setSource(existing.price_source);
            setInput(String(existing.input_price_micro_per_million / 1000000));
            setOutput(
              String(existing.output_price_micro_per_million / 1000000),
            );
            setSensitivity(existing.sensitivity);
          }
        }}
      />
      <FreeModels />
      <div className="tabs">
        <button
          className={tab === "models" ? "active" : ""}
          onClick={() => {
            setTab("models");
            setShow(false);
          }}
        >
          Model registry
        </button>
        <button
          className={tab === "providers" ? "active" : ""}
          onClick={() => {
            setTab("providers");
            setShow(false);
          }}
        >
          Provider connections
        </button>
        <button
          className={tab === "routing" ? "active" : ""}
          onClick={() => {
            setTab("routing");
            setShow(false);
          }}
        >
          Routing policy
        </button>
        <button
          className={tab === "benchmarks" ? "active" : ""}
          onClick={() => {
            setTab("benchmarks");
            setShow(false);
          }}
        >
          Benchmarks
        </button>
      </div>
      <div className="alert info">
        Live model IDs, capabilities, quality evaluations and current prices
        must be explicitly configured. Consumer subscriptions do not establish
        API access. Store keys in the encrypted server vault or configure a
        dedicated environment credential. Catalog checks and inference evidence
        are separate.
      </div>
      {tab !== "benchmarks" && (
        <Panel
          title="Connection readiness"
          subtitle="Configuration facts; a configured credential is not a verified live connection"
        >
          {state.runtime.providers.map((connection) => (
            <div key={connection.id} className="notification-row">
              <Server size={18} />
              <strong>{connection.name}</strong>
              <Badge>{connection.mode}</Badge>
              <Badge>{connection.status}</Badge>
            </div>
          ))}
        </Panel>
      )}
      {tab === "benchmarks" ? (
        <NativeExecution benchmark />
      ) : tab === "routing" ? (
        <Panel
          title="Quality-aware, cost-aware routing"
          subtitle="Mandatory filters run before scoring"
        >
          <div className="settings-grid">
            {[
              {
                title: "Economy",
                text: "Lowest-cost eligible model meeting capabilities, quality, context and data-sensitivity restrictions.",
              },
              {
                title: "Balanced",
                text: "Cost relative to configured quality and reliability, with latency as a tie breaker.",
              },
              {
                title: "Quality first",
                text: "Highest configured quality among eligible models, then cost.",
              },
              {
                title: "Fastest",
                text: "Lowest observed or configured latency among eligible models.",
              },
            ].map((p) => (
              <div key={p.title}>
                <Cpu />
                <h3>{p.title}</h3>
                <p>{p.text}</p>
              </div>
            ))}
          </div>
          <p>
            Assign policy per employee in the workforce directory. Fallback is
            bounded to three distinct eligible models and never switches a live
            workflow to mock. Freshness expires after 30 days. Manual model
            assignment and scoped allowlists preserve every mandatory filter.
            Task-specific evaluations, recorded latency and versioned benchmarks
            inform routing. Every inference must also pass ZERO_COST_ONLY;
            missing free eligibility preserves the saved workflow.
          </p>
          {state.projects.map((project) => (
            <details key={project.id}>
              <summary>{project.name} · project model restrictions</summary>
              <ModelPolicyForm
                key={
                  state.model_policies.find(
                    (p) => p.scope === `project:${project.id}`,
                  )?.version || 0
                }
                scopeType="project"
                recordId={project.id}
              />
            </details>
          ))}
        </Panel>
      ) : (
        <>
          <Panel
            title={
              tab === "providers" ? "Provider connections" : "Configured models"
            }
            subtitle="Live configurations are distinct from the local fixture provider"
            action={
              <Button onClick={() => setShow(!show)}>
                <Plus size={15} />
                {tab === "providers" ? "Add provider" : "Register model"}
              </Button>
            }
          >
            {tab === "providers" ? (
              <div className="provider-grid">
                {state.providers.map((p) => (
                  <div
                    className="provider-card"
                    key={p.id}
                    id={`provider-config-${p.id}`}
                  >
                    <Server size={24} />
                    <h3>{p.name}</h3>
                    <Badge>{p.kind}</Badge>
                    <p className="mono">{p.base_url}</p>
                    <ProviderControls
                      provider={p}
                      register={(id) => {
                        setProvider(p.id);
                        setIdentifier(id);
                        setTab("models");
                        setShow(true);
                      }}
                    />
                    {p.kind !== "mock" && (
                      <details>
                        <summary>Default model & restrictions</summary>
                        <ModelPolicyForm
                          key={
                            state.model_policies.find(
                              (policy) => policy.scope === `provider:${p.id}`,
                            )?.version || 0
                          }
                          scopeType="provider"
                          recordId={p.id}
                        />
                      </details>
                    )}
                    <Button
                      secondary
                      disabled={busy}
                      onClick={() =>
                        run(() =>
                          api(
                            `/providers/${p.id}`,
                            { enabled: !p.enabled },
                            "PATCH",
                          ),
                        )
                      }
                    >
                      {p.enabled ? "Disable provider" : "Enable provider"}
                    </Button>
                  </div>
                ))}
              </div>
            ) : state.models.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Model identifier</th>
                      <th>Provider</th>
                      <th>Quality</th>
                      <th>Capabilities</th>
                      <th>Input / 1M tokens</th>
                      <th>Output / 1M tokens</th>
                      <th>Data sensitivity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.models.map((m) => (
                      <tr key={m.id}>
                        <td>
                          <strong>{m.identifier}</strong>
                          <small>
                            {m.context_tokens.toLocaleString()} context tokens
                          </small>
                        </td>
                        <td>
                          {
                            state.providers.find((p) => p.id === m.provider_id)
                              ?.name
                          }
                        </td>
                        <td>
                          {m.quality}/100
                          <br />
                          <small>configured, not benchmarked</small>
                        </td>
                        <td>{m.capabilities.join(", ")}</td>
                        <td>{money(m.input_price_micro_per_million)}</td>
                        <td>{money(m.output_price_micro_per_million)}</td>
                        <td>
                          <Badge>{m.sensitivity}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="No models configured"
                text="Connect a provider and register supported model IDs and current source-backed prices."
              />
            )}
          </Panel>
          {show && (
            <Panel
              title={
                tab === "providers"
                  ? "Register provider adapter"
                  : "Register model configuration"
              }
              subtitle="Credentials are saved through the encrypted vault in Provider connections after registration. Model listing never proves free inference entitlement."
            >
              {tab === "providers" ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    run(async () => {
                      await api("/providers", {
                        name,
                        kind: kind === "deepseek" ? "compatible" : kind,
                        base_url: url,
                        credential_env: kind === "ollama" ? "" : credential,
                      });
                      setShow(false);
                    });
                  }}
                >
                  <div className="form-grid">
                    <label>
                      Provider name
                      <input
                        required
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                      />
                    </label>
                    <label>
                      Adapter type
                      <select
                        value={kind}
                        onChange={(e) => {
                          const value = e.target.value;
                          setKind(value);
                          const defaults: Record<string, [string, string]> = {
                            openai: [
                              "https://api.openai.com/v1",
                              "OPENAI_API_KEY",
                            ],
                            anthropic: [
                              "https://api.anthropic.com/v1",
                              "ANTHROPIC_API_KEY",
                            ],
                            gemini: [
                              "https://generativelanguage.googleapis.com/v1beta",
                              "GEMINI_API_KEY",
                            ],
                            xai: ["https://api.x.ai/v1", "XAI_API_KEY"],
                            deepseek: [
                              "https://api.deepseek.com",
                              "DEEPSEEK_API_KEY",
                            ],
                            ollama: ["http://localhost:11434", ""],
                          };
                          if (defaults[value]) {
                            setUrl(defaults[value][0]);
                            setCredential(defaults[value][1]);
                          }
                        }}
                      >
                        {[
                          "openai",
                          "anthropic",
                          "gemini",
                          "xai",
                          "deepseek",
                          "ollama",
                          "compatible",
                        ].map((v) => (
                          <option key={v}>{v}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Official base endpoint
                      <input
                        type="url"
                        required
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                      />
                    </label>
                    {kind === "ollama" ? (
                      <p className="muted">
                        Local Ollama uses no API key. Keep the server on
                        loopback.
                      </p>
                    ) : (
                      <label>
                        Server credential variable name
                        <input
                          required
                          value={credential}
                          onChange={(e) => setCredential(e.target.value)}
                          pattern="[A-Z][A-Z0-9_]*_API_KEY"
                        />
                      </label>
                    )}
                  </div>
                  <Button type="submit" disabled={busy}>
                    Register provider
                  </Button>
                </form>
              ) : (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    run(async () => {
                      const existing = state.models.find(
                        (m) =>
                          m.provider_id === provider &&
                          m.identifier === identifier,
                      );
                      await api(
                        existing ? `/models/${existing.id}` : "/models",
                        {
                          provider_id: provider,
                          identifier,
                          quality: Number(quality),
                          context_tokens: Number(context),
                          capabilities: capabilities
                            .split(",")
                            .map((c) => c.trim()),
                          input_price_micro_per_million: Math.round(
                            Number(input) * 1000000,
                          ),
                          output_price_micro_per_million: Math.round(
                            Number(output) * 1000000,
                          ),
                          price_source: source,
                          sensitivity,
                        },
                        existing ? "PATCH" : "POST",
                      );
                      setShow(false);
                    });
                  }}
                >
                  <div className="form-grid">
                    <label>
                      Provider
                      <select
                        value={provider}
                        onChange={(e) => setProvider(e.target.value)}
                        required
                      >
                        <option value="">Choose live provider</option>
                        {state.providers
                          .filter((p) => p.kind !== "mock")
                          .map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      Official model identifier
                      <input
                        required
                        value={identifier}
                        onChange={(e) => setIdentifier(e.target.value)}
                      />
                    </label>
                    <label>
                      Quality score (0–100)
                      <input
                        required
                        type="number"
                        min="0"
                        max="100"
                        value={quality}
                        onChange={(e) => setQuality(e.target.value)}
                      />
                    </label>
                    <label>
                      Context tokens
                      <input
                        required
                        type="number"
                        min="1024"
                        value={context}
                        onChange={(e) => setContext(e.target.value)}
                      />
                    </label>
                    <label>
                      Input price, USD per million tokens
                      <input
                        required
                        type="number"
                        min="0"
                        step="0.000001"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                      />
                    </label>
                    <label>
                      Output price, USD per million tokens
                      <input
                        required
                        type="number"
                        min="0"
                        step="0.000001"
                        value={output}
                        onChange={(e) => setOutput(e.target.value)}
                      />
                    </label>
                    <label>
                      Capabilities, comma-separated
                      <input
                        required
                        value={capabilities}
                        onChange={(e) => setCapabilities(e.target.value)}
                      />
                    </label>
                    <label>
                      Allowed data sensitivity
                      <select
                        value={sensitivity}
                        onChange={(e) => setSensitivity(e.target.value)}
                      >
                        {["public", "internal", "confidential"].map((v) => (
                          <option key={v}>{v}</option>
                        ))}
                      </select>
                    </label>
                    <label className="full">
                      Verified pricing source
                      <input
                        required
                        type="url"
                        value={source}
                        onChange={(e) => setSource(e.target.value)}
                      />
                    </label>
                  </div>
                  <Button type="submit" disabled={busy}>
                    Register model
                  </Button>
                </form>
              )}
            </Panel>
          )}
        </>
      )}
    </>
  );
}
