"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge, Button, Panel, Pretty, useApp } from "./common";

type Readiness = {
  state: string;
  message: string;
  setup_message: string;
  registered_models: number;
  eligible_models: number;
  live_verified_models: number;
  execution_enabled: boolean;
};
type Evidence = {
  preferred_lead: string;
  selected_lead_id: string | null;
  worker_mode: string;
  lead_status: { allowed: boolean; state: string; reason: string };
  selection_history: unknown[];
  workflows: {
    id: string;
    kind: string;
    status: string;
    step: number;
    message: string;
    waiting: Record<string, unknown>;
    runs: {
      run_id: string;
      step: string;
      status: string;
      verification: string;
      agent_id: string;
      requested_model_id?: string | null;
      actual_model_id: string;
      successful_model_id?: string | null;
      transport?: {
        reported_model?: string;
        identity_verified?: boolean;
        tokens_per_second?: number;
        load_duration_ns?: number;
      };
      identifier?: string;
      provider?: string;
      error?: string;
    }[];
  }[];
};

export function AiReadiness() {
  const { navigate } = useApp();
  const [result, setResult] = useState<Readiness | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function refresh() {
    setLoading(true);
    setError("");
    try {
      setResult(await api<Readiness>("/ai-readiness"));
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);
  return (
    <Panel
      title="AI readiness"
      subtitle="Saved configuration, eligibility and observed results are separate facts."
    >
      {error && <p role="alert">Readiness check failed: {error}</p>}
      {result && (
        <>
          <Badge>{result.state}</Badge>
          <p>{result.message}</p>
          <p>{result.setup_message}</p>
          <p>
            {result.registered_models} registered · {result.eligible_models}{" "}
            eligible · {result.live_verified_models} live verified
          </p>
          <p>
            Restricted code execution:{" "}
            {result.execution_enabled
              ? "enabled; exact task approval still required"
              : "disabled in this workspace"}
            .
          </p>
        </>
      )}
      <div className="heading-actions">
        <Button secondary disabled={loading} onClick={() => void refresh()}>
          {loading ? "Checking readiness…" : "Refresh readiness"}
        </Button>
        <Button onClick={() => navigate("models")}>Connect AI Provider</Button>
      </div>
      <small className="muted">
        Readiness refresh makes no AI call, installs nothing and authorizes no
        work.
      </small>
    </Panel>
  );
}

export function ExecutionEvidence({
  projectId,
  draftId,
}: {
  projectId?: string;
  draftId?: string;
}) {
  const { state, navigate } = useApp();
  const [result, setResult] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const endpoint = projectId
    ? `/projects/${projectId}/execution-evidence`
    : `/project-drafts/${draftId}/execution-evidence`;
  const workflowRevision = state.workflows
    .map((row) => `${row.id}:${row.status}:${row.step}`)
    .join("|");
  useEffect(() => {
    let disposed = false;
    setError("");
    api<Evidence>(endpoint)
      .then((value) => {
        if (!disposed) setResult(value);
      })
      .catch((exc: Error) => {
        if (!disposed) setError(exc.message);
      });
    return () => {
      disposed = true;
    };
  }, [endpoint, revision, workflowRevision, state.runs.length]);
  const modelName = (id?: string | null) =>
    id
      ? state.models.find((model) => model.id === id)?.identifier || id
      : "Automatic routing";
  return (
    <Panel
      title="Model assignments & execution evidence"
      subtitle="A saved choice is not a completed AI invocation."
    >
      {error && <p role="alert">Could not load execution evidence: {error}</p>}
      {result && (
        <>
          <p>
            Lead AI:{" "}
            {result.selected_lead_id
              ? modelName(result.selected_lead_id)
              : `${result.preferred_lead} · preferred, unavailable`}
          </p>
          <p>{result.lead_status.reason}</p>
          <p>
            Worker selection: {result.worker_mode}.{" "}
            {result.selection_history.length} saved selection revisions.
          </p>
          {!result.workflows.length && (
            <p>
              No agent execution has started. Requirements and model preferences
              remain saved.
            </p>
          )}
          {result.workflows.map((workflow) => (
            <details key={workflow.id}>
              <summary>
                {workflow.kind.replaceAll("_", " ")} ·{" "}
                {workflow.status.replaceAll("_", " ")} · {workflow.step} saved
                checkpoints
              </summary>
              {workflow.message && <p>{workflow.message}</p>}
              {!workflow.runs.length && (
                <p>No model result has been recorded for this workflow.</p>
              )}
              {workflow.runs.map((run) => (
                <div className="control-note" key={run.run_id}>
                  <div>
                    <strong>
                      {state.agents.find((agent) => agent.id === run.agent_id)
                        ?.role || "Agent"}{" "}
                      · {run.step}
                    </strong>
                    <p>
                      Requested: {modelName(run.requested_model_id)}. Attempted
                      model: {run.identifier || modelName(run.actual_model_id)}
                      {run.provider ? ` (${run.provider})` : ""}.
                    </p>
                    {run.successful_model_id && (
                      <p>
                        Accepted execution model:{" "}
                        {modelName(run.successful_model_id)}.
                      </p>
                    )}
                    {run.transport?.reported_model && (
                      <p>
                        Ollama reported: {run.transport.reported_model}.
                        Identity{" "}
                        {run.transport.identity_verified
                          ? "matched"
                          : "unverified"}
                        {typeof run.transport.tokens_per_second === "number"
                          ? ` · ${run.transport.tokens_per_second} tokens/s`
                          : ""}
                        .
                      </p>
                    )}
                    <Badge>{run.verification}</Badge>{" "}
                    <Badge>{run.status}</Badge>
                    {run.error && <p>{run.error}</p>}
                  </div>
                </div>
              ))}
              <details>
                <summary>Advanced details</summary>
                <Pretty value={workflow} />
              </details>
            </details>
          ))}
        </>
      )}
      <div className="heading-actions">
        <Button secondary onClick={() => setRevision((value) => value + 1)}>
          Refresh execution evidence
        </Button>
        <Button secondary onClick={() => navigate("models")}>
          Configure approved models
        </Button>
      </div>
    </Panel>
  );
}
