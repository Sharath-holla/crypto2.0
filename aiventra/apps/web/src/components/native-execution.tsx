"use client";
import { useEffect, useRef, useState } from "react";
import { api, money } from "@/lib/api";
import { Badge, Button, Panel, Pretty, useApp } from "./common";

export function NativeExecution({
  benchmark = false,
}: {
  benchmark?: boolean;
}) {
  const { state, run, busy } = useApp();
  const [recommendations, setRecommendations] = useState<Record<
    string,
    { model_id: string | null; reason: string }
  > | null>(null);
  const [recommendationError, setRecommendationError] = useState("");
  const recommendationRevision = JSON.stringify([
    state.benchmark_profiles,
    state.models,
    state.runtime.providers,
  ]);
  useEffect(() => {
    if (!benchmark) return;
    let active = true;
    api<Record<string, { model_id: string | null; reason: string }>>(
      "/model-recommendations",
    )
      .then((data) => {
        if (active) {
          setRecommendations(data);
          setRecommendationError("");
        }
      })
      .catch(() => {
        if (active)
          setRecommendationError("Model recommendations could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, [benchmark, recommendationRevision]);
  const [project, setProject] = useState("");
  const [agent, setAgent] = useState("");
  const [peers, setPeers] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [objective, setObjective] = useState("");
  const [cap, setCap] = useState("1.00");
  const pending = useRef<{ hash: string; id: string } | null>(null);
  const models = state.models.filter(
    (m) =>
      m.enabled &&
      state.providers.some(
        (p) => p.id === m.provider_id && p.enabled && p.kind !== "mock",
      ),
  );
  const agents = state.agents.filter(
    (a) => a.enabled && a.tools.includes("write_artifact"),
  );
  const jobs = state.agent_work.filter(
    (w) => w.kind === (benchmark ? "benchmark" : "tools"),
  );
  return (
    <Panel
      title={benchmark ? "Model benchmarks" : "Native tool execution"}
      subtitle={
        benchmark
          ? "Versioned microbenchmarks · actual ledger costs and latency"
          : "Authorized project tools · bounded rounds and peer handoff"
      }
    >
      <p className="muted">
        {benchmark
          ? "Eight repeatable cases cover simple, business, architecture, coding, repair, testing, review and tool tasks. Coding answers are parsed without executing code. Scores measure this limited rubric; they do not certify production quality."
          : "The server permits scoped memory/artifact reads, document writes, a calculator and one selected peer document handoff. A handoff shares this job's cap. Maximum three model rounds; generated code never runs here."}{" "}
        Live calls may spend API credits. Missing eligible providers wait
        without spending.
      </p>
      {benchmark && (
        <div className="settings-grid">
          {recommendationError && <p role="alert">{recommendationError}</p>}
          {recommendations &&
            Object.entries(recommendations).map(([policy, value]) => (
              <div className="run-evidence" key={policy}>
                <strong>
                  {policy} ·{" "}
                  {value.model_id
                    ? state.models.find((m) => m.id === value.model_id)
                        ?.identifier
                    : "No automatic selection"}
                </strong>
                <p>{value.reason}</p>
              </div>
            ))}
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const body = benchmark
            ? {
                model_id: model,
                budget_micro: Math.round(Number(cap) * 1000000),
              }
            : {
                project_id: project,
                agent_id: agent,
                peer_ids: peers,
                objective,
                model_override: model || null,
                mode: "live",
                budget_micro: Math.round(Number(cap) * 1000000),
              };
          const hash = JSON.stringify(body);
          if (pending.current?.hash !== hash)
            pending.current = { hash, id: crypto.randomUUID() };
          const id = pending.current.id;
          run(async () => {
            await api(benchmark ? "/model-benchmarks" : "/agent-tool-jobs", {
              ...body,
              request_id: id,
            });
            pending.current = null;
          }, "Durable execution queued");
        }}
      >
        <div className="form-grid">
          {!benchmark && (
            <>
              <label>
                Tool execution project
                <select
                  aria-label="Tool execution project"
                  required
                  value={project}
                  onChange={(e) => setProject(e.target.value)}
                >
                  <option value="">Choose approved active project</option>
                  {state.projects
                    .filter((p) => p.status === "active")
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Tool execution agent
                <select
                  aria-label="Tool execution agent"
                  required
                  value={agent}
                  onChange={(e) => {
                    setAgent(e.target.value);
                    setPeers([]);
                  }}
                >
                  <option value="">Choose document-authorized agent</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          <label>
            {benchmark ? "Benchmark model" : "Tool model override"}
            <select
              aria-label={benchmark ? "Benchmark model" : "Tool model override"}
              value={model}
              required={benchmark}
              onChange={(e) => setModel(e.target.value)}
            >
              <option value="">
                {benchmark
                  ? "Choose registered real model"
                  : "Automatic eligible routing"}
              </option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.identifier}
                </option>
              ))}
            </select>
          </label>
          <label>
            Execution spend cap (USD)
            <input
              aria-label={benchmark ? "Benchmark spend cap" : "Tool spend cap"}
              type="number"
              min="0.001"
              max={benchmark ? "5" : "50"}
              step="0.001"
              required
              value={cap}
              onChange={(e) => setCap(e.target.value)}
            />
          </label>
          {!benchmark && (
            <>
              <label className="full">
                Tool execution objective
                <textarea
                  aria-label="Tool execution objective"
                  required
                  minLength={10}
                  maxLength={12000}
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                />
              </label>
              <fieldset className="full">
                <legend>
                  Optional peer handoff recipients ({peers.length}/8)
                </legend>
                <div className="model-options">
                  {agents
                    .filter((a) => a.id !== agent)
                    .map((a) => (
                      <label key={a.id}>
                        <input
                          type="checkbox"
                          aria-label={`Allow handoff to ${a.name}`}
                          checked={peers.includes(a.id)}
                          disabled={!peers.includes(a.id) && peers.length >= 8}
                          onChange={(e) =>
                            setPeers(
                              e.target.checked
                                ? [...peers, a.id]
                                : peers.filter((id) => id !== a.id),
                            )
                          }
                        />
                        {a.name}
                      </label>
                    ))}
                </div>
              </fieldset>
            </>
          )}
        </div>
        <Button
          type="submit"
          disabled={
            busy ||
            (benchmark && !model) ||
            (!benchmark && (!project || !agent))
          }
        >
          {benchmark ? "Run capped benchmark" : "Queue native tool execution"}
        </Button>
      </form>
      {benchmark &&
        state.benchmark_profiles.map((p) => (
          <details key={p.id}>
            <summary>
              {state.models.find((m) => m.id === p.model_id)?.identifier} ·{" "}
              {p.suite_version} · measured rubric {p.metrics.quality}/100
            </summary>
            <Pretty value={p.metrics} />
            <p className="muted">
              The router uses this profile only while its model/price/credential
              fingerprint remains current.
            </p>
          </details>
        ))}
      {jobs.slice(0, 10).map((job) => {
        const workflow = state.workflows.find((w) => w.id === job.workflow_id);
        const peerTaskIds = new Set(
          state.tasks
            .filter((task) => task.payload.job_id === job.id)
            .map((task) => task.id),
        );
        const runs = state.runs.filter(
          (r) =>
            r.workflow_id === job.workflow_id ||
            (r.task_id !== null && peerTaskIds.has(r.task_id)),
        );
        const invocations = state.tool_invocations.filter(
          (t) => t.workflow_id === job.workflow_id,
        );
        const pendingPeer = invocations.some(
          (call) =>
            typeof call.result.task_id === "string" &&
            state.tasks.some(
              (task) =>
                task.id === call.result.task_id &&
                !["completed", "cancelled", "failed"].includes(task.status),
            ),
        );
        const results = state.benchmark_results.filter(
          (r) => r.work_id === job.id,
        );
        return (
          <details key={job.id}>
            <summary>
              {job.kind} · {job.id.slice(0, 8)}{" "}
              <Badge>{workflow?.status || "record unavailable"}</Badge> ·
              recorded {money(runs.reduce((n, r) => n + r.cost_micro, 0))}
              {benchmark && ` · ${results.length}/8 cases stored`}
            </summary>
            {workflow?.last_error && (
              <p className="error-text">{workflow.last_error}</p>
            )}
            {workflow &&
              workflow.status !== "cancelled" &&
              (workflow.status !== "completed" || pendingPeer) && (
                <Button
                  secondary
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => api(`/agent-work/${job.id}/cancel`, {}),
                      "Execution cancelled; in-flight usage may require reconciliation",
                    )
                  }
                >
                  Cancel execution
                </Button>
              )}
            <Pretty value={job.result} />
            {results.map((r) => (
              <p key={r.id}>
                {r.case_name}: {r.status} · {r.score}/100 ·{" "}
                {money(r.metrics.cost_micro)} · {r.metrics.duration_ms} ms
              </p>
            ))}
            {invocations.map((t) => (
              <div className="run-evidence" key={t.id}>
                <strong>
                  {t.name} · {t.status}
                </strong>
                <Pretty value={t.result} />
                {typeof t.result.task_id === "string" && (
                  <p>
                    Peer task:{" "}
                    {state.tasks.find((task) => task.id === t.result.task_id)
                      ?.status || "record outside current snapshot"}
                  </p>
                )}
              </div>
            ))}
            {runs.map((r) => {
              const trace = state.run_traces.find((t) => t.run_id === r.id);
              return (
                <div className="run-evidence" key={r.id}>
                  <strong>
                    {r.step_name} · {r.status}
                  </strong>
                  <p>{r.routing_reason}</p>
                  {trace && (
                    <>
                      <p>
                        Native execution: {trace.state} · {trace.event_count}{" "}
                        events · {trace.tool_count} calls · usage{" "}
                        {trace.usage_known ? "recorded" : "unresolved"}
                      </p>
                      <Pretty value={trace.preview} />
                    </>
                  )}
                </div>
              );
            })}
          </details>
        );
      })}
    </Panel>
  );
}
