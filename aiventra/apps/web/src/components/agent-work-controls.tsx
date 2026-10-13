"use client";
import { useRef, useState } from "react";
import { api, money } from "@/lib/api";
import { Badge, Button, Panel, Pretty, useApp } from "./common";

export function AgentWorkControls() {
  const { state, run, busy, navigate } = useApp();
  const [kind, setKind] = useState("message");
  const [project, setProject] = useState("");
  const [sender, setSender] = useState("");
  const [recipient, setRecipient] = useState("");
  const [participants, setParticipants] = useState<string[]>([]);
  const [body, setBody] = useState("");
  const [mode, setMode] = useState("live");
  const [cap, setCap] = useState("0.50");
  const [rounds, setRounds] = useState("1");
  const [followups, setFollowups] = useState(false);
  const [type, setType] = useState("TaskAssigned");
  const [manualModel, setManualModel] = useState("");
  const pending = useRef<{ hash: string; id: string } | null>(null);
  const agents = state.agents.filter(
    (a) => a.enabled && a.tools.includes("read_context"),
  );
  return (
    <>
      <Panel
        title="Direct agent work"
        subtitle="Approved project scope · persistent queues · bounded model calls"
      >
        <div className="tabs">
          <button
            className={kind === "message" ? "active" : ""}
            onClick={() => setKind("message")}
          >
            Assign a message
          </button>
          <button
            className={kind === "meeting" ? "active" : ""}
            onClick={() => setKind("meeting")}
          >
            Convene a meeting
          </button>
          <button
            className={kind === "planning" ? "active" : ""}
            onClick={() => setKind("planning")}
          >
            BA → CTO → PM plan
          </button>
        </div>
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            const hash = JSON.stringify({
              kind,
              project,
              mode,
              cap,
              sender,
              recipient,
              type,
              body,
              participants,
              rounds,
              followups,
              manualModel,
            });
            if (pending.current?.hash !== hash)
              pending.current = { hash, id: crypto.randomUUID() };
            const common = {
              request_id: pending.current.id,
              project_id: project,
              mode,
              budget_micro: Math.round(Number(cap) * 1000000),
              model_override: manualModel || null,
            };
            run(async () => {
              if (kind === "planning") {
                const draft = await api<{
                  version: number;
                  content_hash: string;
                  status: string;
                } | null>(`/projects/${project}/staffing`);
                if (!draft || draft.status !== "draft")
                  throw new Error(
                    "Select a project with an unapproved workforce draft.",
                  );
                await api("/agent-planning", {
                  ...common,
                  plan_version: draft.version,
                  plan_hash: draft.content_hash,
                  objective: body,
                });
                pending.current = null;
                setBody("");
                return;
              }
              await api(
                kind === "message" ? "/agent-messages" : "/agent-meetings",
                kind === "message"
                  ? {
                      ...common,
                      sender_id: sender,
                      recipient_id: recipient,
                      type,
                      body,
                    }
                  : {
                      ...common,
                      participant_ids: participants,
                      agenda: body,
                      rounds: Number(rounds),
                      create_followups: followups,
                    },
              );
              pending.current = null;
              setBody("");
            }, "Agent work queued. Recorded workflow status appears below.");
          }}
        >
          <label>
            Approved project
            <select
              aria-label="Approved project"
              value={project}
              onChange={(e) => setProject(e.target.value)}
              required
            >
              <option value="">Choose an active project</option>
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
            Agent work provider mode
            <select
              aria-label="Agent work provider mode"
              value={mode}
              onChange={(e) => {
                setMode(e.target.value);
                setManualModel("");
              }}
            >
              <option value="live">Live providers</option>
              {state.runtime.mock_enabled && (
                <option value="mock">Explicit local fixture</option>
              )}
            </select>
          </label>
          {kind === "message" ? (
            <>
              <label>
                Sender agent
                <select
                  aria-label="Sender agent"
                  value={sender}
                  onChange={(e) => setSender(e.target.value)}
                  required
                >
                  <option value="">Choose sender</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Recipient agent
                <select
                  aria-label="Recipient agent"
                  value={recipient}
                  onChange={(e) => setRecipient(e.target.value)}
                  required
                >
                  <option value="">Choose recipient</option>
                  {agents
                    .filter(
                      (a) =>
                        a.id !== sender && a.tools.includes("write_artifact"),
                    )
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Message operation
                <select value={type} onChange={(e) => setType(e.target.value)}>
                  {[
                    "TaskAssigned",
                    "QuestionAsked",
                    "ReviewRequested",
                    "EscalationRaised",
                    "ArtifactShared",
                  ].map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </label>
            </>
          ) : kind === "meeting" ? (
            <>
              <label>
                Meeting rounds
                <select
                  value={rounds}
                  onChange={(e) => setRounds(e.target.value)}
                >
                  <option value="1">One independent round + decision</option>
                  <option value="2">
                    Independent round + disagreement review + decision
                  </option>
                </select>
              </label>
              <fieldset className="full">
                <legend>Meeting participants ({participants.length}/8)</legend>
                <div className="model-options">
                  {agents.map((a) => (
                    <label key={a.id}>
                      <input
                        type="checkbox"
                        checked={participants.includes(a.id)}
                        disabled={
                          !participants.includes(a.id) &&
                          participants.length >= 8
                        }
                        onChange={(e) =>
                          setParticipants(
                            e.target.checked
                              ? [...participants, a.id]
                              : participants.filter((id) => id !== a.id),
                          )
                        }
                      />
                      {a.name}
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className="full">
                <input
                  type="checkbox"
                  checked={followups}
                  onChange={(e) => setFollowups(e.target.checked)}
                />
                Create up to four scoped document follow-ups within the same
                spend cap
              </label>
            </>
          ) : (
            <p className="full muted">
              Business Analyst saves requirements, CTO receives that document,
              then Project Manager saves a task plan and a new workforce draft.
              Execution requires separate workforce approval. Without an
              eligible local model, the workflow waits without an inference
              call.
            </p>
          )}
          <label>
            Maximum estimated spend (USD)
            <input
              type="number"
              min="0.001"
              max="50"
              step="0.001"
              required
              value={cap}
              onChange={(e) => setCap(e.target.value)}
            />
          </label>
          <label>
            Explicit model override
            <select
              aria-label="Agent work model override"
              value={manualModel}
              onChange={(e) => setManualModel(e.target.value)}
            >
              <option value="">Automatic eligible routing</option>
              {state.models
                .filter(
                  (m) =>
                    m.enabled &&
                    (state.providers.find((p) => p.id === m.provider_id)
                      ?.kind ===
                      "mock") ===
                      (mode === "mock"),
                )
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.identifier}
                  </option>
                ))}
            </select>
          </label>
          <label className="full">
            {kind === "message"
              ? "Agent message objective"
              : kind === "planning"
                ? "Planning objective"
                : "Meeting agenda"}
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              minLength={10}
              maxLength={kind === "planning" ? 2000 : 12000}
              rows={4}
              required
            />
          </label>
          <p className="muted full">
            First-round meeting contributions receive the same saved evidence
            and no earlier verdicts. ZERO_COST_ONLY permits verified local
            inference; missing eligible models put work into a saved waiting
            state.
          </p>
          <div className="full">
            <Button
              type="submit"
              disabled={
                busy ||
                !project ||
                (kind === "meeting" && participants.length < 2)
              }
            >
              {kind === "message"
                ? "Queue agent message"
                : kind === "planning"
                  ? "Start saved planning workflow"
                  : "Start bounded meeting"}
            </Button>
          </div>
        </form>
      </Panel>
      <Panel
        title="Agent work execution"
        subtitle="Actual workflow records, usage and saved outputs"
      >
        {state.agent_work
          .filter((w) => w.kind !== "probe")
          .map((work) => {
            const workflow = state.workflows.find(
              (w) => w.id === work.workflow_id,
            );
            const runs = state.runs.filter(
              (r) => r.workflow_id === work.workflow_id,
            );
            return (
              <details key={work.id}>
                <summary>
                  {work.kind} ·{" "}
                  {state.projects.find((p) => p.id === work.project_id)?.name}
                  <Badge mode={workflow?.mode}>
                    {workflow?.mode || "unknown"}
                  </Badge>
                  <Badge>{workflow?.status || "unknown"}</Badge>
                </summary>
                <p>
                  {runs.length} recorded calls ·{" "}
                  {money(runs.reduce((n, r) => n + r.cost_micro, 0))} computed
                  estimate ·{" "}
                  {money(
                    runs
                      .filter((r) =>
                        ["started", "uncertain"].includes(r.status),
                      )
                      .reduce((n, r) => n + r.reserved_micro, 0),
                  )}{" "}
                  held
                </p>
                {workflow?.last_error && (
                  <p className="alert warning">{workflow.last_error}</p>
                )}
                {workflow &&
                  !["completed", "cancelled"].includes(workflow.status) && (
                    <Button
                      secondary
                      disabled={busy}
                      onClick={() =>
                        run(
                          () => api(`/agent-work/${work.id}/cancel`, {}),
                          "Agent work cancelled. In-flight provider usage can still be recorded and charged.",
                        )
                      }
                    >
                      Cancel agent work
                    </Button>
                  )}
                <Pretty value={work.result} />
                {work.kind === "planning" && (
                  <>
                    {state.messages
                      .filter((message) => message.correlation_id === work.id)
                      .map((message) => (
                        <p key={message.id}>
                          {
                            state.agents.find(
                              (agent) => agent.id === message.sender,
                            )?.role
                          }{" "}
                          →{" "}
                          {
                            state.agents.find(
                              (agent) => agent.id === message.recipient,
                            )?.role
                          }{" "}
                          <Badge>{message.status}</Badge>
                        </p>
                      ))}
                    <Button secondary onClick={() => navigate("allocation")}>
                      Review workforce draft
                    </Button>
                  </>
                )}
                {typeof work.result.artifact_id === "string" && (
                  <Pretty
                    value={
                      state.artifacts.find(
                        (a) => a.id === work.result.artifact_id,
                      )?.content || "Artifact not in this snapshot"
                    }
                  />
                )}
              </details>
            );
          })}
        {!state.agent_work.some((w) => w.kind !== "probe") && (
          <p className="muted">
            Queue a message or meeting for an approved project to see its
            execution evidence here.
          </p>
        )}
      </Panel>
    </>
  );
}
