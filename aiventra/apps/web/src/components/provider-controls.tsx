"use client";
import { useRef, useState } from "react";
import { api, date, money } from "@/lib/api";
import type { Provider } from "@/lib/types";
import { Badge, Button, useApp } from "./common";

export function ProviderControls({
  provider,
  register,
}: {
  provider: Provider;
  register: (id: string) => void;
}) {
  const { state, run, busy } = useApp();
  const [secret, setSecret] = useState("");
  const [catalogModel, setCatalogModel] = useState("");
  const [probeModel, setProbeModel] = useState("");
  const [cap, setCap] = useState("0.10");
  const pendingProbe = useRef<{ hash: string; id: string } | null>(null);
  const connection = state.runtime.providers.find((p) => p.id === provider.id);
  const probe = state.provider_probes.find(
    (p) => p.provider_id === provider.id,
  );
  const models = state.models.filter(
    (m) => m.provider_id === provider.id && m.enabled !== false,
  );
  const jobs = state.agent_work.filter(
    (w) => w.kind === "probe" && w.subject_id === provider.id,
  );
  if (provider.kind === "mock")
    return (
      <p className="muted">Explicit local fixture · no live provider calls.</p>
    );
  return (
    <div className="provider-controls">
      <div className="badge-row">
        <Badge>{probe?.status || "catalog unverified"}</Badge>
        <Badge>
          {probe?.inference_at ? "inference recorded" : "inference unverified"}
        </Badge>
      </div>
      <p className="muted">
        Credential source: {connection?.credential_source || "none"}.{" "}
        {connection?.credential_error || ""}
      </p>
      {provider.kind !== "ollama" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const key = secret;
            setSecret("");
            run(
              () =>
                api(`/providers/${provider.id}/credentials`, { secret: key }),
              "Credential encrypted on the server. Connection is still unverified.",
            );
          }}
        >
          <label>
            {provider.name} API key
            <input
              type="password"
              autoComplete="off"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              minLength={8}
              maxLength={4096}
              required
              placeholder="Encrypted on save; never shown again"
            />
          </label>
          <div className="button-row">
            <Button
              type="submit"
              disabled={busy || !secret || !connection?.vault_available}
            >
              Save encrypted key
            </Button>
            {connection?.credential_source === "vault" && (
              <Button
                secondary
                disabled={busy}
                onClick={() =>
                  run(
                    () =>
                      api(`/providers/${provider.id}/credentials/revoke`, {}),
                    "Stored key removed. Any environment fallback is shown separately.",
                  )
                }
              >
                Remove stored key
              </Button>
            )}
          </div>
          {!connection?.vault_available && (
            <p className="muted">
              Configure PROVIDER_SECRET_KEY on the server to enable encrypted
              storage. Environment credentials remain available.
            </p>
          )}
        </form>
      )}
      <Button
        secondary
        disabled={busy || !provider.enabled}
        onClick={() =>
          run(
            () => api(`/providers/${provider.id}/discover`, {}),
            "Catalog check recorded. Review its result below.",
          )
        }
      >
        Test connection & discover models
      </Button>
      {probe?.checked_at && (
        <small className="muted">
          Catalog checked {date(probe.checked_at)} ·{" "}
          {probe.error_code || `${probe.models.length} account models`}
        </small>
      )}
      {!!probe?.models.length && (
        <div>
          <label>
            Discovered model
            <select
              value={catalogModel}
              onChange={(e) => setCatalogModel(e.target.value)}
            >
              <option value="">Choose an account model</option>
              {probe.models.map((m) => (
                <option key={m.identifier} value={m.identifier}>
                  {m.identifier}
                </option>
              ))}
            </select>
          </label>
          <Button
            secondary
            disabled={!catalogModel}
            onClick={() => register(catalogModel)}
          >
            Configure this model
          </Button>
          <p className="muted">
            Discovery confirms an identifier. Configure documented capabilities,
            context, quality and current prices before routing.
          </p>
        </div>
      )}
      {!!models.length && (
        <details>
          <summary>Bounded inference test</summary>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const hash = JSON.stringify({ probeModel, cap });
              if (pendingProbe.current?.hash !== hash)
                pendingProbe.current = { hash, id: crypto.randomUUID() };
              const requestId = pendingProbe.current.id;
              run(async () => {
                await api(`/providers/${provider.id}/inference-probe`, {
                  request_id: requestId,
                  model_id: probeModel,
                  budget_micro: Math.round(Number(cap) * 1000000),
                });
                pendingProbe.current = null;
              }, "Inference test queued with its own cap. Check the saved workflow result.");
            }}
          >
            <label>
              Registered model
              <select
                value={probeModel}
                onChange={(e) => setProbeModel(e.target.value)}
                required
              >
                <option value="">Select model</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.identifier}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Maximum estimated spend (USD)
              <input
                type="number"
                min="0.001"
                max="1"
                step="0.001"
                value={cap}
                onChange={(e) => setCap(e.target.value)}
                required
              />
            </label>
            <p className="muted">
              ZERO_COST_ONLY blocks unverified remote billing. This probe can
              run only after free eligibility, capability, permission,
              sensitivity and budget checks pass.
            </p>
            <Button type="submit" disabled={busy || !probeModel}>
              Run bounded inference test
            </Button>
          </form>
        </details>
      )}
      {probe?.inference_at && (
        <p className="muted">
          Last validated inference: {date(probe.inference_at)} ·{" "}
          {
            state.models.find((m) => m.id === probe.inference_model_id)
              ?.identifier
          }
        </p>
      )}
      {jobs.slice(0, 3).map((job) => {
        const workflow = state.workflows.find((w) => w.id === job.workflow_id);
        const runs = state.runs.filter(
          (r) => r.workflow_id === job.workflow_id,
        );
        return (
          <p key={job.id}>
            <Badge>{workflow?.status || "unknown"}</Badge> {runs.length}{" "}
            recorded calls · {money(runs.reduce((n, r) => n + r.cost_micro, 0))}{" "}
            {workflow?.last_error}
          </p>
        );
      })}
    </div>
  );
}

export function ModelPolicyForm({
  scopeType,
  recordId,
}: {
  scopeType: "agent" | "provider" | "project";
  recordId: string;
}) {
  const { state, run, busy } = useApp();
  const policy = state.model_policies.find(
    (p) => p.scope === `${scopeType}:${recordId}`,
  );
  const [preferred, setPreferred] = useState(policy?.preferred_model_id || "");
  const [allowed, setAllowed] = useState<string[]>(
    policy?.allowed_model_ids || [],
  );
  const models = state.models.filter(
    (m) => scopeType !== "provider" || m.provider_id === recordId,
  );
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        run(
          () =>
            api(`/model-policies/${scopeType}/${recordId}`, {
              version: policy?.version || 0,
              preferred_model_id: preferred || null,
              allowed_model_ids: allowed,
            }),
          "Model policy saved; mandatory routing filters still apply.",
        );
      }}
    >
      <label>
        Preferred model
        <select
          aria-label="Preferred model"
          value={preferred}
          onChange={(e) => setPreferred(e.target.value)}
        >
          <option value="">Automatic eligible routing</option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.identifier} ·{" "}
              {state.providers.find((p) => p.id === m.provider_id)?.name}
            </option>
          ))}
        </select>
      </label>
      <details>
        <summary>
          Restrict allowed models ({allowed.length || "all eligible"})
        </summary>
        <div className="model-options">
          {models.map((m) => (
            <label key={m.id}>
              <input
                type="checkbox"
                checked={allowed.includes(m.id)}
                onChange={(e) =>
                  setAllowed(
                    e.target.checked
                      ? [...allowed, m.id]
                      : allowed.filter((id) => id !== m.id),
                  )
                }
              />
              {m.identifier}
            </label>
          ))}
        </div>
        <p className="muted">
          An empty selection allows all eligible models. Project, employee and
          provider restrictions intersect; preferences cannot bypass them.
          Registered models can be saved while blocked; execution still waits
          for verified free eligibility and required capabilities.
        </p>
      </details>
      <Button type="submit" disabled={busy}>
        Save model policy
      </Button>
    </form>
  );
}
