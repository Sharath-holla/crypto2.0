"use client";
import { useState } from "react";
import { Activity, Pause, Play, ShieldCheck, Wallet } from "lucide-react";
import { api, date, money } from "@/lib/api";
import { Badge, Button, Empty, Panel, Pretty, useApp } from "./common";
import { ModelEvaluation } from "./model-evaluation";
import { DatabaseStatus } from "./database-status";
import { AiReadiness } from "./ai-readiness";
export function Governance({ view }: { view: string }) {
  const { state, run, busy, navigate } = useApp();
  const [integrity, setIntegrity] = useState<unknown>(null);
  const [budgetId, setBudgetId] = useState("");
  const [limit, setLimit] = useState("");
  if (view === "finance")
    return (
      <>
        <div className="stats-grid">
          {[
            {
              label: "Computed provider estimate",
              value: money(state.runs.reduce((s, r) => s + r.cost_micro, 0)),
            },
            {
              label: "Recorded input tokens",
              value: state.runs
                .reduce((s, r) => s + r.input_tokens, 0)
                .toLocaleString(),
            },
            {
              label: "Recorded output tokens",
              value: state.runs
                .reduce((s, r) => s + r.output_tokens, 0)
                .toLocaleString(),
            },
            {
              label: "Uncertain provider calls",
              value: state.runs.filter((r) =>
                ["started", "uncertain"].includes(r.status),
              ).length,
            },
          ].map((s) => (
            <div className="stat-card" key={s.label}>
              <div className="stat-label">
                {s.label}
                <Wallet size={16} />
              </div>
              <strong>{s.value}</strong>
              <small>Recorded data · no fabricated invoice charges</small>
            </div>
          ))}
        </div>
        <Panel
          title="Budget controls"
          subtitle="All relevant caps reserve worst-case cost atomically before a paid request"
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Scope</th>
                  <th>Limit</th>
                  <th>Spent estimate</th>
                  <th>Reserved</th>
                  <th>Remaining</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {state.budgets.map((b) => (
                  <tr key={b.id}>
                    <td className="mono">{b.scope}</td>
                    <td>{money(b.limit_micro)}</td>
                    <td>{money(b.spent_micro)}</td>
                    <td>{money(b.reserved_micro)}</td>
                    <td>
                      {money(b.limit_micro - b.spent_micro - b.reserved_micro)}
                    </td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => {
                          setBudgetId(b.id);
                          setLimit(String(b.limit_micro / 1000000));
                        }}
                      >
                        Change limit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {budgetId && (
            <form
              className="inline-form"
              onSubmit={(e) => {
                e.preventDefault();
                const budget = state.budgets.find((b) => b.id === budgetId)!;
                run(
                  () =>
                    api(
                      `/budgets/${budget.id}`,
                      {
                        limit_micro: Math.round(Number(limit) * 1000000),
                        version: budget.version,
                      },
                      "PATCH",
                    ),
                  "Owner budget change recorded.",
                );
              }}
            >
              <label>
                New USD limit
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={limit}
                  onChange={(e) => setLimit(e.target.value)}
                />
              </label>
              <Button type="submit" disabled={busy}>
                Record owner approval
              </Button>
              <Button secondary onClick={() => setBudgetId("")}>
                Cancel
              </Button>
            </form>
          )}
        </Panel>
        <RunTable />
      </>
    );
  if (view === "activity")
    return (
      <>
        <Panel
          title="Durable workflow activity"
          subtitle="No progress is inferred from agent claims"
        >
          {state.workflows.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Workflow</th>
                    <th>Status</th>
                    <th>Persisted step</th>
                    <th>Attempts</th>
                    <th>Issue</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {state.workflows.map((w) => (
                    <tr key={w.id}>
                      <td>
                        <strong>
                          {state.requirements.find(
                            (item) => item.id === w.requirement_id,
                          )?.title ||
                            state.tasks.find((item) => item.id === w.task_id)
                              ?.objective ||
                            w.kind.replaceAll("_", " ")}
                        </strong>
                        <small>
                          {w.mode === "mock"
                            ? "Deterministic fixture · no live AI"
                            : "Live workflow · inference depends on provider eligibility"}
                        </small>
                        <small className="mono">{w.id}</small>
                      </td>
                      <td>
                        <Badge>{w.status.replaceAll("_", " ")}</Badge>
                      </td>
                      <td>{w.step}</td>
                      <td>
                        {w.attempts}/{w.max_attempts}
                      </td>
                      <td>{w.last_error || "—"}</td>
                      <td>
                        {w.status === "needs_attention" && (
                          <Button
                            secondary
                            disabled={busy}
                            onClick={() =>
                              run(() => api(`/workflows/${w.id}/retry`, {}))
                            }
                          >
                            Retry
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="No workflow activity"
              text="Submit a requirement to see real agent execution records."
            />
          )}
        </Panel>
        <RunTable />
      </>
    );
  if (view === "settings")
    return (
      <>
        <AiReadiness />
        <Panel
          title="AI models"
          subtitle="View connected providers, discover models and save project preferences."
        >
          <Button onClick={() => navigate("models")}>Models & Providers</Button>
        </Panel>
        <Panel
          title="Owner emergency controls"
          subtitle="Enforced in backend policy and worker dispatch"
        >
          <div className="settings-grid">
            <div>
              <Pause />
              <h3>Company operations</h3>
              <p>
                Stop new requests and artifact execution across all projects.
              </p>
              <Badge>{state.organization.paused ? "paused" : "active"}</Badge>
              <Button
                disabled={busy}
                onClick={() =>
                  run(() =>
                    api("/controls", {
                      action: state.organization.paused
                        ? "resume_company"
                        : "pause_company",
                    }),
                  )
                }
              >
                {state.organization.paused ? "Resume company" : "Pause company"}
              </Button>
            </div>
            <div>
              <ShieldCheck />
              <h3>Production deployment</h3>
              <p>
                Deployment also requires a connector, verified test evidence and
                environment approval.
              </p>
              <Badge>
                {state.organization.deployments_paused
                  ? "paused"
                  : "approval controlled"}
              </Badge>
              <Button
                secondary
                disabled={busy}
                onClick={() =>
                  run(() => api("/controls", { action: "pause_deployments" }))
                }
              >
                Pause production deployments
              </Button>
            </div>
          </div>
        </Panel>
        <Panel
          title="Runtime configuration"
          subtitle="Facts from the running backend"
        >
          <Pretty value={state.runtime} />
          <div className="alert warning">
            ZERO_COST_ONLY blocks paid cloud inference. Local generation
            requires an installed, verified model. Infrastructure checks and
            model quality are verified separately.
          </div>
          <h3>Remaining platform work</h3>
          <p>
            GitHub publication approval, client delivery, OAuth mail/calendar,
            verified staging deployment/rollback and full-scale concurrency
            tests are tracked in the repository’s implementation status.
          </p>
        </Panel>
        <DatabaseStatus />
      </>
    );
  return (
    <>
      <Panel
        title="Independent monitoring"
        subtitle="Watchdog findings report directly to the owner"
        action={
          <Button
            disabled={busy}
            onClick={() =>
              run(
                () => api("/monitoring/inspect", {}),
                "Watchdog inspection completed.",
              )
            }
          >
            Inspect workflows
          </Button>
        }
      >
        {state.notifications.length ? (
          state.notifications.map((n) => (
            <div className="notification-row" key={n.id}>
              <ShieldCheck size={18} />
              <div>
                <strong>{n.title}</strong>
                <small>
                  {date(n.created_at)} · {n.subject_id}
                </small>
              </div>
              <Badge>{n.severity}</Badge>
              {n.acknowledged ? (
                <Badge>acknowledged</Badge>
              ) : (
                <Button
                  secondary
                  disabled={busy}
                  onClick={() =>
                    run(() => api(`/notifications/${n.id}/ack`, {}))
                  }
                >
                  Acknowledge
                </Button>
              )}
            </div>
          ))
        ) : (
          <Empty
            title="No recorded alerts"
            text="Unauthorized operations, stuck workflows and uncertain spending create owner alerts."
          />
        )}
      </Panel>
      <Panel
        title="Audit integrity"
        subtitle="Append-only hash chain; external anchoring remains a production requirement"
        action={
          <Button
            secondary
            onClick={() =>
              run(
                async () => setIntegrity(await api("/audit/verify")),
                "Audit verification completed.",
              )
            }
          >
            Verify hash chain
          </Button>
        }
      >
        {integrity !== null && <Pretty value={integrity} />}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Authorization</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {state.audit.map((a) => (
                <tr key={a.id}>
                  <td>{date(a.created_at)}</td>
                  <td>
                    {state.agents.find((agent) => agent.id === a.actor)?.name ||
                      a.actor.slice(0, 20)}
                  </td>
                  <td>{a.action}</td>
                  <td>{a.authorization}</td>
                  <td>
                    <details>
                      <summary>Inspect</summary>
                      <Pretty value={a.detail} />
                      <span className="mono">{a.event_hash}</span>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
function RunTable() {
  const { state } = useApp();
  return (
    <Panel
      title="Model execution ledger"
      subtitle="Routing reasons, usage, quality failures and fallback history"
    >
      {state.runs.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Agent / step</th>
                <th>Model</th>
                <th>Status</th>
                <th>Tokens in / out</th>
                <th>Cost basis</th>
                <th>Estimate</th>
                <th>Routing evidence</th>
              </tr>
            </thead>
            <tbody>
              {state.runs.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>
                      {state.agents.find((a) => a.id === r.agent_id)?.name}
                    </strong>
                    <small>{r.step_name}</small>
                  </td>
                  <td>
                    {state.models.find((m) => m.id === r.model_id)?.identifier}
                    <small>
                      {state.providers.find(
                        (provider) =>
                          provider.id ===
                          state.models.find((model) => model.id === r.model_id)
                            ?.provider_id,
                      )?.kind === "mock"
                        ? "Deterministic fixture"
                        : "Recorded provider call"}
                    </small>
                  </td>
                  <td>
                    <Badge>{r.status}</Badge>
                  </td>
                  <td>
                    {r.input_tokens} / {r.output_tokens}
                  </td>
                  <td>{r.cost_basis}</td>
                  <td>{money(r.cost_micro)}</td>
                  <td>
                    <details>
                      <summary>Why this model</summary>
                      <p>{r.routing_reason}</p>
                      {r.error && <p className="error-text">{r.error}</p>}
                      <ModelEvaluation runId={r.id} />
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title="No recorded model calls"
          text="Agent runs persist their provider usage, price basis and selection reason here."
        />
      )}
    </Panel>
  );
}
