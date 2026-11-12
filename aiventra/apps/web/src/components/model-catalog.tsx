"use client";
import { useCallback, useEffect, useState } from "react";
import { api, date } from "@/lib/api";
import { Badge, Button, Panel, useApp } from "./common";
import { LocalAiStatus } from "./local-ai-status";

export type CatalogModel = {
  id: string;
  provider_id: string;
  provider: string;
  kind: string;
  identifier: string;
  enabled: boolean;
  model_enabled: boolean;
  configured: boolean;
  capabilities: string[];
  capability_source: string;
  context_tokens: number;
  effective_context_tokens?: number;
  local_metadata?: { digest?: string; size_bytes?: number };
  registration: string;
  present: boolean;
  stale: boolean;
  pricing_status: string;
  live_inference_at: number | null;
  eligibility: { allowed: boolean; state: string; reason: string };
};
export type Catalog = {
  models: CatalogModel[];
  providers: {
    id: string;
    name: string;
    kind: string;
    connection_state: string;
    configured: boolean;
    enabled: boolean;
    status: string;
    error_code: string;
    credential_error: string;
    registered_count: number;
    last_checked_at: number | null;
    last_success_at: number | null;
    stale: boolean;
    discovery_interrupted: boolean;
  }[];
};

const catalogErrors: Record<string, string> = {
  missing_credentials: "No credential is saved for this provider.",
  vault_unavailable:
    "The credential vault is unavailable. Check the server vault configuration.",
  credential_changed: "The saved connection changed. Refresh its models.",
  catalog_http_401: "The provider rejected authentication (401).",
  catalog_http_403: "The provider denied catalog access (403).",
  catalog_http_404:
    "The model-listing endpoint was not found (404). Owner registration remains available.",
  catalog_http_429: "The provider rate limit was reached (429). Retry later.",
  catalog_timeout:
    "Model discovery timed out. The last successful catalog is retained.",
  catalog_invalid: "The provider returned an invalid model catalog.",
  catalog_network_failure:
    "The provider could not be reached. Retry when the connection recovers.",
  catalog_endpoint_invalid:
    "The endpoint is invalid or outside the server allowlist.",
  catalog_unsupported:
    "This adapter does not support model discovery. Use owner registration.",
  catalog_retention_limit:
    "Catalog retention is full. Existing registrations were preserved.",
};

export function ModelCatalog({
  configure,
  connect,
}: {
  configure: (provider: string, identifier: string) => void;
  connect: (providerId?: string) => void;
}) {
  const { state, run, busy } = useApp();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState("");
  const [capability, setCapability] = useState("");
  const [mode, setMode] = useState("all");
  const [showUnconfigured, setShowUnconfigured] = useState(false);
  const load = useCallback(async () => {
    try {
      setCatalog(await api<Catalog>("/model-catalog"));
      setError("");
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "Could not load model catalog",
      );
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load, state.models, state.provider_probes, state.providers]);
  const providers =
    catalog?.providers.filter(
      (p) =>
        (!provider || p.id === provider) && (showUnconfigured || p.configured),
    ) || [];
  return (
    <Panel
      title="Models & Providers"
      subtitle="Registered models stay visible. Saving a preference never authorizes paid execution."
    >
      {error && (
        <p role="alert" className="alert error">
          {error}
        </p>
      )}
      <div className="form-grid">
        <label>
          Search models
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          Filter provider
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            <option value="">All configured providers</option>
            {catalog?.providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Filter capability
          <select
            value={capability}
            onChange={(e) => setCapability(e.target.value)}
          >
            <option value="">Any capability</option>
            {["structured", "reasoning", "coding", "tools", "streaming"].map(
              (c) => (
                <option key={c}>{c}</option>
              ),
            )}
          </select>
        </label>
        <label>
          Show models
          <select
            aria-label="Show models"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="all">All registered models</option>
            <option value="ready">Executable models only</option>
            <option value="blocked">Blocked models</option>
          </select>
        </label>
      </div>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={showUnconfigured}
          onChange={(e) => setShowUnconfigured(e.target.checked)}
        />
        Include providers without a saved connection
      </label>
      {!catalog && !error && <p role="status">Loading models…</p>}
      {catalog && !providers.length && (
        <div>
          <p>
            No AI providers are connected yet. Open Provider connections to
            configure an authorized endpoint or inspect existing configurations.
          </p>
          <Button secondary onClick={() => connect()}>
            Configure provider
          </Button>
        </div>
      )}
      {providers.map((p) => {
        const models = catalog!.models.filter(
          (m) =>
            m.provider_id === p.id &&
            m.identifier.toLowerCase().includes(search.toLowerCase()) &&
            (!capability || m.capabilities.includes(capability)) &&
            (mode === "all" || m.eligibility.allowed === (mode === "ready")),
        );
        return (
          <div className="provider-card" key={p.id}>
            <h3>{p.name}</h3>
            <div className="badge-row">
              <Badge>
                {p.configured ? "Provider configured" : "Not configured"}
              </Badge>
              {!p.enabled && <Badge>Disabled</Badge>}
              <Badge>{p.registered_count} registered models</Badge>
              {p.stale && <Badge>Stale catalog</Badge>}
            </div>
            <p>
              {p.kind === "ollama" && p.error_code === "catalog_network_failure"
                ? "No local model server is running at the configured endpoint."
                : catalogErrors[p.credential_error || p.error_code] ||
                  p.credential_error ||
                  p.error_code ||
                  (p.status === "not_discovered"
                    ? "Models have not been discovered yet."
                    : p.status === "catalog_verified"
                      ? catalog!.models.some(
                          (model) =>
                            model.provider_id === p.id &&
                            model.live_inference_at,
                        )
                        ? "Models discovered. Review each model's recorded inference evidence."
                        : "Model identifiers discovered; live inference is unverified."
                      : p.status)}
            </p>
            {p.discovery_interrupted && (
              <p>Discovery was interrupted. Refresh models to retry safely.</p>
            )}
            {p.kind === "ollama" && <LocalAiStatus providerId={p.id} />}
            {p.last_success_at && (
              <small>
                Last successful discovery: {date(p.last_success_at)}
              </small>
            )}
            <Button secondary onClick={() => connect(p.id)}>
              Configure / reconnect
            </Button>
            <Button
              secondary
              disabled={busy || !p.enabled}
              onClick={() =>
                run(async () => {
                  await api(`/providers/${p.id}/discover`, {});
                  await load();
                }, "Discovery finished. Review the saved catalog status.")
              }
            >
              {p.last_success_at ? "Refresh models" : "Discover models"}
            </Button>
            {!p.registered_count && (
              <p>
                {p.configured
                  ? "Your provider is configured, but no models have been discovered yet."
                  : "No registered models. Configuration does not prove account access."}
              </p>
            )}
            {!!p.registered_count && !models.length && (
              <p>No models match these filters.</p>
            )}
            {models.map((m) => (
              <div key={m.id} className="catalog-model">
                <strong>{m.identifier}</strong>
                <div className="badge-row">
                  <Badge>{m.registration}</Badge>
                  <Badge>
                    {m.eligibility.allowed
                      ? "Ready to use"
                      : "Unavailable under free-only mode"}
                  </Badge>
                  {!m.present && <Badge>No longer listed</Badge>}
                  <Badge>
                    {m.live_inference_at
                      ? "Live inference recorded"
                      : "Live inference unverified"}
                  </Badge>
                </div>
                <p>{m.eligibility.reason}</p>
                <small>
                  Capabilities:{" "}
                  {m.capabilities.length
                    ? `${m.capabilities.join(", ")} (owner configured)`
                    : "unknown"}{" "}
                  · Context: {m.context_tokens || "unknown"} · Pricing:{" "}
                  {m.pricing_status}
                </small>
                {m.kind === "ollama" && (
                  <p>
                    Effective local context:{" "}
                    {m.effective_context_tokens ?? "unverified"} tokens.
                    Installed size:{" "}
                    {m.local_metadata?.size_bytes
                      ? `${(m.local_metadata.size_bytes / 1_000_000).toFixed(1)} MB`
                      : "unverified"}
                    . Last accepted live inference:{" "}
                    {m.live_inference_at
                      ? date(m.live_inference_at)
                      : "not verified"}
                    .
                  </p>
                )}
                <div className="button-row">
                  <Button
                    secondary
                    onClick={() => configure(m.provider_id, m.identifier)}
                  >
                    Configure model
                  </Button>
                  <Button
                    secondary
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        api(
                          `/models/${m.id}/enabled`,
                          { enabled: !m.model_enabled },
                          "PATCH",
                        ),
                      )
                    }
                  >
                    {m.model_enabled ? "Disable model" : "Enable model"}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </Panel>
  );
}
