"use client";
import { useState } from "react";
import { CopyPlus, Network, Search, ShieldCheck, Users } from "lucide-react";
import { api, date, money } from "@/lib/api";
import { ModelPolicyForm } from "./provider-controls";
import { Badge, Button, Empty, Panel, useApp } from "./common";

export function Workforce({ hierarchy }: { hierarchy: boolean }) {
  const { state, run, busy } = useApp();
  const [department, setDepartment] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const agents = state.agents.filter(
    (a) =>
      (!department || a.department_id === department) &&
      a.name.toLowerCase().includes(search.toLowerCase()),
  );
  const agent = state.agents.find((a) => a.id === selected);
  const runs = agent ? state.runs.filter((r) => r.agent_id === agent.id) : [];
  const runtime = agent
    ? state.agent_runtime.find((r) => r.agent_id === agent.id)
    : null;
  return (
    <>
      <div className="runtime-strip">
        <span>
          <strong>
            {
              state.agent_runtime.filter(
                (r) => r.state === "RUNNING" && r.mode === "live",
              ).length
            }
          </strong>{" "}
          live invocations running
        </span>
        <span>
          <strong>
            {
              state.agent_runtime.filter((r) =>
                ["WAITING_FOR_PROVIDER", "WAITING_FOR_FREE_PROVIDER"].includes(
                  r.state,
                ),
              ).length
            }
          </strong>{" "}
          waiting for providers
        </span>
        <span>
          <strong>
            {state.agent_runtime.filter((r) => r.state === "BLOCKED").length}
          </strong>{" "}
          blocked
        </span>
        <small>
          Registered roles execute on demand. Fixture runs are explicitly
          labeled.
        </small>
      </div>
      <div className="tabs">
        <button
          className={!hierarchy ? "active" : ""}
          onClick={() => window.location.assign("/?view=workforce")}
        >
          Employee directory
        </button>
        <button
          className={hierarchy ? "active" : ""}
          onClick={() => window.location.assign("/?view=organization")}
        >
          Reporting structure
        </button>
        <span>
          {state.agents.length} employees across {state.departments.length}{" "}
          departments
        </span>
      </div>
      {hierarchy ? (
        <>
          <div className="org-owner">
            <ShieldCheck />
            <div>
              <strong>Human owner</strong>
              <small>Approval authority · independent oversight</small>
            </div>
          </div>
          <div className="department-grid">
            {state.departments.map((d) => (
              <Panel
                key={d.id}
                title={d.name}
                subtitle={
                  d.independent
                    ? "Reports directly to owner"
                    : "Reports through department leadership"
                }
              >
                <div className="role-list">
                  {state.agents
                    .filter((a) => a.department_id === d.id)
                    .map((a) => (
                      <button key={a.id} onClick={() => setSelected(a.id)}>
                        <span className="avatar-mini">
                          {a.name.slice(0, 2).toUpperCase()}
                        </span>
                        <div>
                          <strong>{a.name}</strong>
                          <small>Reports to {a.reports_to}</small>
                        </div>
                        <Badge>
                          {state.agent_runtime.find((r) => r.agent_id === a.id)
                            ?.state || "REGISTERED"}
                        </Badge>
                      </button>
                    ))}
                </div>
              </Panel>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="toolbar">
            <div className="filter-input">
              <Search size={16} />
              <input
                aria-label="Find employee"
                placeholder="Find an employee…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select
              aria-label="Filter department"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            >
              <option value="">All departments</option>
              {state.departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
            <Button
              secondary
              onClick={() =>
                run(
                  () => api("/crypto/activate", {}),
                  "Optional crypto specialist roles activated.",
                )
              }
            >
              Activate crypto specialists
            </Button>
          </div>
          <div className="agent-grid">
            {agents.map((a) => {
              const department = state.departments.find(
                (d) => d.id === a.department_id,
              );
              const count = state.runs.filter(
                (r) => r.agent_id === a.id,
              ).length;
              return (
                <button
                  className="agent-card"
                  key={a.id}
                  onClick={() => setSelected(a.id)}
                >
                  <div className="agent-card-top">
                    <span className="agent-avatar">
                      {a.name
                        .split(" ")
                        .map((w) => w[0])
                        .slice(0, 2)
                        .join("")}
                    </span>
                    <Badge>
                      {state.agent_runtime.find((r) => r.agent_id === a.id)
                        ?.state || "REGISTERED"}
                    </Badge>
                  </div>
                  <h3>{a.name}</h3>
                  <p>{department?.name}</p>
                  <div className="agent-card-bottom">
                    <span>
                      <Network size={13} />
                      {a.routing_policy}
                    </span>
                    <span>{count} model runs</span>
                  </div>
                </button>
              );
            })}
          </div>
          {!agents.length && (
            <Empty
              title="No matching employees"
              text="Try another department or search."
            />
          )}
        </>
      )}
      {agent && (
        <div className="modal-overlay" onClick={() => setSelected("")}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="modal-close"
              aria-label="Close employee"
              onClick={() => setSelected("")}
            >
              ×
            </button>
            <span className="agent-avatar">{agent.name.slice(0, 2)}</span>
            <h2>{agent.name}</h2>
            <div className="badge-row">
              <Badge>{runtime?.state || "REGISTERED"}</Badge>
              {runtime?.mode && (
                <Badge mode={runtime.mode}>{runtime.mode}</Badge>
              )}
            </div>
            {runtime?.workflow_id && (
              <p className="muted">
                {runtime.step_name} · updated {date(runtime.updated_at)}
                {runtime.stale_lease
                  ? " · expired lease; recovery required"
                  : ""}
              </p>
            )}
            <p>
              {
                state.departments.find((d) => d.id === agent.department_id)
                  ?.name
              }{" "}
              · Reports to {agent.reports_to}
            </p>
            <div className="detail-stats">
              <div>
                <strong>{runs.length}</strong>
                <small>model runs</small>
              </div>
              <div>
                <strong>
                  {runs.filter((r) => r.status === "succeeded").length}
                </strong>
                <small>validated results</small>
              </div>
              <div>
                <strong>
                  {money(runs.reduce((sum, r) => sum + r.cost_micro, 0))}
                </strong>
                <small>recorded estimates</small>
              </div>
            </div>
            <h3>Responsibilities</h3>
            <ModelPolicyForm
              key={`${agent.id}:${state.model_policies.find((p) => p.scope === `agent:${agent.id}`)?.version || 0}`}
              scopeType="agent"
              recordId={agent.id}
            />
            <ul>
              {agent.responsibilities.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <h3>Tool permissions</h3>
            <div className="badge-row">
              {agent.tools.map((t) => (
                <Badge key={t}>{t}</Badge>
              ))}
            </div>
            <h3>Policy & objectives</h3>
            <ul>
              {[...agent.policies, ...agent.objectives].map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
            <label>
              Routing policy
              <select
                value={agent.routing_policy}
                onChange={(e) =>
                  run(() =>
                    api(
                      `/agents/${agent.id}`,
                      { routing_policy: e.target.value },
                      "PATCH",
                    ),
                  )
                }
              >
                <option value="economy">Economy</option>
                <option value="balanced">Balanced</option>
                <option value="quality">Quality first</option>
                <option value="manual">Manual exact model override</option>
                <option value="fastest">Fastest</option>
              </select>
            </label>
            <p className="muted">
              Per-agent limit: {money(agent.max_cost_micro)} ·{" "}
              {agent.max_iterations} maximum iterations
            </p>
            <details>
              <summary>Recorded execution transitions</summary>
              {state.agent_executions
                .filter((e) => e.agent_id === agent.id)
                .map((execution) => (
                  <div key={execution.id}>
                    <p>
                      {execution.step_name} · <Badge>{execution.state}</Badge>
                    </p>
                    {state.agent_state_events
                      .filter((event) => event.execution_id === execution.id)
                      .slice()
                      .sort((a, b) => a.sequence - b.sequence)
                      .map((event) => (
                        <p className="muted" key={event.id}>
                          {date(event.created_at)} ·{" "}
                          {event.previous_state || "new"} → {event.state}
                        </p>
                      ))}
                  </div>
                ))}
            </details>
            <div className="button-row">
              <Button
                disabled={busy}
                onClick={() =>
                  run(() =>
                    api(
                      `/agents/${agent.id}`,
                      { enabled: !agent.enabled },
                      "PATCH",
                    ),
                  )
                }
              >
                {agent.enabled ? "Pause employee" : "Enable employee"}
              </Button>
              <Button
                secondary
                disabled={busy}
                onClick={() => run(() => api(`/agents/${agent.id}/clone`, {}))}
              >
                <CopyPlus size={15} />
                Add instance
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
