"use client";
import { useState } from "react";
import {
  ArrowRight,
  BriefcaseBusiness,
  GitBranch,
  Plus,
  ShieldCheck,
} from "lucide-react";
import { api, date, money } from "@/lib/api";
import type { Task } from "@/lib/types";
import { Badge, Button, Empty, Panel, Pretty, useApp } from "./common";
import { PublicationControls } from "./publication-controls";
import { DeliveryControls } from "./delivery-controls";
import { PackageControls } from "./package-controls";
import { DeliveryFollowups } from "./delivery-followups";
import { Staffing } from "./staffing";
import { RepositoryImport } from "./repository-import";
import { ProjectHistory } from "./project-history";
import { ExecutionEvidence } from "./ai-readiness";
import { RequirementsReview } from "./requirements-review";
import { ArchitectureEvidence } from "./consulting";
import { QualityControls } from "./quality-controls";
import { DeploymentControls } from "./deployment-controls";

export function Projects({
  engineering,
  initialId = "",
}: {
  engineering: boolean;
  initialId?: string;
}) {
  const { state, run, busy } = useApp();
  const [selected, setSelected] = useState(initialId);
  const [tab, setTab] = useState(engineering ? "engineering" : "board");
  const [path, setPath] = useState("");
  const [repoName, setRepoName] = useState("");
  const [repository, setRepository] = useState("");
  const [objective, setObjective] = useState("");
  const [acceptance, setAcceptance] = useState("");
  const [suite, setSuite] = useState("python-unittest");
  const [mode, setMode] = useState("live");
  const [reviewPolicy, setReviewPolicy] = useState("prefer_provider");
  const [reviewCount, setReviewCount] = useState("1");
  const [details, setDetails] = useState<Task | null>(null);
  const [assigning, setAssigning] = useState(false);
  const project = state.projects.find((p) => p.id === selected);
  const tasks = state.tasks.filter((t) => t.project_id === selected);
  const repos = state.repositories.filter((r) => r.project_id === selected);
  const executions = state.executions.filter((e) =>
    tasks.some((t) => t.id === e.task_id),
  );
  const artifacts = state.artifacts.filter((a) => a.project_id === selected);
  const dependencies = state.dependencies.filter((edge) =>
    tasks.some((task) => task.id === edge.task_id),
  );
  const proposal = state.proposals.find(
    (item) => item.id === project?.proposal_id,
  );
  const requirement = state.requirements.find(
    (item) => item.id === proposal?.requirement_id,
  );
  if (!project)
    return (
      <>
        <Panel
          title={
            engineering ? "Managed repositories & QA" : "Your project portfolio"
          }
          subtitle="Projects are created from versioned approved proposals"
        >
          {state.projects.length ? (
            <div className="portfolio-grid">
              {state.projects.map((p) => {
                const all = state.tasks.filter((t) => t.project_id === p.id);
                const completed = all.filter(
                  (t) => t.status === "completed",
                ).length;
                return (
                  <button
                    className="portfolio-card"
                    key={p.id}
                    onClick={() => {
                      setSelected(p.id);
                      setTab(engineering ? "engineering" : "board");
                    }}
                  >
                    <div>
                      <span className="project-icon">
                        <BriefcaseBusiness size={21} />
                      </span>
                      <Badge>{p.status}</Badge>
                    </div>
                    <h3>{p.name}</h3>
                    <p>{p.selected_alternative}</p>
                    <div className="progress">
                      <span
                        style={{
                          width: `${all.length ? (completed / all.length) * 100 : 0}%`,
                        }}
                      />
                    </div>
                    <div className="portfolio-footer">
                      <span>
                        {completed}/{all.length} tasks verified
                      </span>
                      <ArrowRight size={16} />
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <Empty
              title="No projects have been approved"
              text="Approve a consulting proposal to create a project. No implementation starts before that decision."
            />
          )}
        </Panel>
        {engineering && (
          <Panel title="Execution boundary" subtitle="Runner readiness">
            <div className="control-note">
              <ShieldCheck size={18} />
              <p>
                Code execution is{" "}
                {state.runtime.execution_enabled
                  ? "enabled by configuration"
                  : "disabled"}
                . A separate restricted Docker runner, independent review and QA
                evidence are required. Live Docker verification is pending until
                that runtime is available.
              </p>
            </div>
          </Panel>
        )}
      </>
    );
  return (
    <>
      <button className="text-button" onClick={() => setSelected("")}>
        ← Project portfolio
      </button>
      <div className="record-heading">
        <span className="record-icon">
          <BriefcaseBusiness />
        </span>
        <div>
          <h2>{project.name}</h2>
          <p>
            {project.selected_alternative} · Agent budget{" "}
            {money(project.budget_micro)}
          </p>
        </div>
        <Badge>{project.status}</Badge>
        <Button
          disabled={busy || project.status !== "active"}
          onClick={() => setAssigning(!assigning)}
        >
          <Plus size={15} /> Assign specialist
        </Button>
        <Button
          secondary
          disabled={busy}
          onClick={() =>
            run(() =>
              api(
                `/projects/${project.id}`,
                { enabled: project.status !== "active" },
                "PATCH",
              ),
            )
          }
        >
          {project.status === "active" ? "Pause project" : "Resume project"}
        </Button>
      </div>
      {assigning && <SpecialistAssignment projectId={project.id} />}
      <ExecutionEvidence key={project.id} projectId={project.id} />
      <section className="project-stages" aria-label="Project stages">
        {[
          ["requirements", "Requirements", "Scope approved"],
          ["planning", "Planning", "Review workforce plan and approvals"],
          [
            "engineering",
            "Engineering",
            `${tasks.filter((task) => task.status === "completed").length}/${tasks.length} tasks completed`,
          ],
          [
            "qa",
            "QA & review",
            `${executions.filter((execution) => execution.status === "completed" && execution.exit_code === 0).length} successful executions`,
          ],
          ["delivery", "Delivery", "Review release and client acceptance"],
        ].map(([target, label, status]) => (
          <button
            key={target}
            aria-label={`Open ${label} stage`}
            onClick={() => setTab(target)}
            aria-current={tab === target ? "step" : undefined}
          >
            <strong>{label}</strong>
            <small>{status}</small>
          </button>
        ))}
      </section>
      {tab === "requirements" && (
        <Panel
          title="Approved requirements"
          subtitle="Versioned scope remains the authority for this project"
        >
          <h3>{requirement?.title}</h3>
          <p className="wizard-brief">{requirement?.text}</p>
          <p>Selected architecture: {project.selected_alternative}</p>
          {proposal && <ArchitectureEvidence proposal={proposal} />}
          {requirement && (
            <RequirementsReview
              key={requirement.id}
              requirementId={requirement.id}
            />
          )}
          <p>
            Acceptance criteria:{" "}
            {proposal?.content.acceptance_criteria.join(" · ")}
          </p>
        </Panel>
      )}
      {tab === "planning" && (
        <Staffing key={project.id} initialId={project.id} />
      )}
      {tab === "qa" && (
        <QualityControls
          key={`quality:${project.id}`}
          projectId={project.id}
          tasks={tasks}
        />
      )}
      {tab === "qa" && (
        <Panel
          title="Independent QA & review"
          subtitle="Recorded task outcomes and sandbox execution evidence; successful commands alone do not prove acceptance."
        >
          {!tasks.some((task) => task.kind === "coding") && (
            <p>No engineering task has produced independent QA evidence yet.</p>
          )}
          {tasks
            .filter((task) => task.kind === "coding")
            .map((task) => (
              <details key={task.id}>
                <summary>
                  {task.objective} · {task.status.replaceAll("_", " ")}
                </summary>
                <p>Acceptance criteria: {task.acceptance.join(" · ")}</p>
                <Pretty value={task.evidence} />
                <ProjectHistory
                  key={task.id}
                  projectId={project.id}
                  taskId={task.id}
                />
                {executions
                  .filter((execution) => execution.task_id === task.id)
                  .map((execution) => (
                    <div key={execution.id}>
                      <Badge>{execution.status}</Badge>
                      <p>
                        Exit code: {execution.exit_code ?? "Not available"} ·{" "}
                        {execution.command.join(" ")}
                      </p>
                      <Pretty value={execution.logs} />
                    </div>
                  ))}
              </details>
            ))}
          <div className="heading-actions">
            <Button secondary onClick={() => setTab("engineering")}>
              Inspect engineering and review controls
            </Button>
            <Button secondary onClick={() => setTab("delivery")}>
              Open final review and delivery gates
            </Button>
          </div>
        </Panel>
      )}
      <div className="tabs">
        {[
          "board",
          "timeline",
          "dependencies",
          "engineering",
          "delivery",
          "artifacts",
        ].map((t) => (
          <button
            key={t}
            className={tab === t ? "active" : ""}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      {tab === "delivery" && (
        <>
          <DeliveryControls key={project.id} projectId={project.id} />
          <DeploymentControls
            key={`deployment:${project.id}`}
            projectId={project.id}
          />
          <PackageControls
            key={`packages:${project.id}`}
            projectId={project.id}
          />
          <DeliveryFollowups
            key={`followups:${project.id}`}
            projectId={project.id}
          />
        </>
      )}
      {tab === "board" && (
        <div className="kanban">
          {[
            {
              name: "Queued",
              states: [
                "ready",
                "blocked",
                "awaiting_approval",
                "waiting_for_provider",
                "waiting_for_free_provider",
              ],
            },
            {
              name: "In progress",
              states: ["in_progress", "review", "testing"],
            },
            { name: "Completed", states: ["completed"] },
            { name: "Needs attention", states: ["failed", "cancelled"] },
          ].map((column) => (
            <section className="kanban-column" key={column.name}>
              <h3>
                {column.name}
                <span>
                  {tasks.filter((t) => column.states.includes(t.status)).length}
                </span>
              </h3>
              {tasks
                .filter((t) => column.states.includes(t.status))
                .map((t) => (
                  <button
                    className="task-card"
                    key={t.id}
                    onClick={() => setDetails(t)}
                  >
                    <div>
                      <Badge>{t.kind}</Badge>
                      <Badge>{t.status}</Badge>
                    </div>
                    <h4>{t.objective}</h4>
                    <small>
                      {
                        state.agents.find((a) => a.id === t.assigned_agent_id)
                          ?.name
                      }
                    </small>
                    <span>{t.acceptance.length} acceptance criteria</span>
                  </button>
                ))}
            </section>
          ))}
        </div>
      )}
      {tab === "timeline" && (
        <>
          <ProjectHistory key={selected} projectId={selected} />
          <Panel
            title="Delivery milestones"
            subtitle="Ordered milestones; no invented delivery dates"
          >
            <div className="timeline">
              {state.milestones
                .filter((m) => m.project_id === selected)
                .sort((a, b) => a.position - b.position)
                .map((m, i) => (
                  <div key={m.id}>
                    <span>{i + 1}</span>
                    <h3>{m.name}</h3>
                    <p>
                      Dates require an approved schedule and workload estimate.
                    </p>
                  </div>
                ))}
            </div>
          </Panel>
        </>
      )}
      {tab === "dependencies" && (
        <Panel
          title="Task dependencies"
          subtitle="Stored prerequisites determine which tasks can start"
        >
          <div className="dependency-list">
            {dependencies.map((edge) => {
              const before = tasks.find((task) => task.id === edge.depends_on);
              const after = tasks.find((task) => task.id === edge.task_id);
              return (
                <div key={`${edge.depends_on}:${edge.task_id}`}>
                  <strong>{before?.objective}</strong>
                  <Badge>{before?.status}</Badge>
                  <ArrowRight size={18} aria-label="Required before" />
                  <strong>{after?.objective}</strong>
                  <Badge>{after?.status}</Badge>
                </div>
              );
            })}
            {!dependencies.length && (
              <Empty
                title="No task prerequisites"
                text="These visible tasks have no stored dependencies."
              />
            )}
          </div>
        </Panel>
      )}
      {tab === "engineering" && (
        <>
          <RepositoryImport key={project.id} projectId={project.id} />
          <div className="two-columns">
            <Panel
              title="Register existing repository"
              subtitle="Read-only discovery under the configured repository root"
            >
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  run(
                    () =>
                      api("/repositories", {
                        project_id: project.id,
                        name: repoName,
                        relative_path: path,
                      }),
                    "Repository discovered without modifying source files.",
                  );
                }}
              >
                <label>
                  Repository name
                  <input
                    value={repoName}
                    onChange={(e) => setRepoName(e.target.value)}
                    required
                  />
                </label>
                <label>
                  Relative path under REPOSITORY_ROOT
                  <input
                    value={path}
                    onChange={(e) => setPath(e.target.value)}
                    placeholder="my-crypto-project"
                    required
                  />
                </label>
                <p className="muted">
                  Copy or place your repository inside the configured root.
                  Discovery does not run its code or expose secret files.
                </p>
                <Button type="submit" disabled={busy}>
                  <GitBranch size={15} />
                  Analyze repository
                </Button>
              </form>
            </Panel>
            <Panel
              title="Plan an isolated coding task"
              subtitle="Repository modification requires approval of this exact scope"
            >
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  run(
                    () =>
                      api(`/projects/${project.id}/coding`, {
                        repository_id: repository,
                        objective,
                        acceptance: acceptance.split("\n").filter(Boolean),
                        test_suite: suite,
                        mode,
                        review_policy: reviewPolicy,
                        review_count: Number(reviewCount),
                      }),
                    "Coding task created, awaiting repository-change approval.",
                  );
                }}
              >
                <label>
                  Repository
                  <select
                    value={repository}
                    onChange={(e) => setRepository(e.target.value)}
                    required
                  >
                    <option value="">Choose repository</option>
                    {repos
                      .filter((r) => !r.report.remote_metadata_only)
                      .map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Objective
                  <textarea
                    value={objective}
                    onChange={(e) => setObjective(e.target.value)}
                    required
                    minLength={10}
                  />
                </label>
                <label>
                  Acceptance criteria (one per line)
                  <textarea
                    value={acceptance}
                    onChange={(e) => setAcceptance(e.target.value)}
                    required
                  />
                </label>
                <div className="form-grid">
                  <label>
                    Approved test suite
                    <select
                      value={suite}
                      onChange={(e) => setSuite(e.target.value)}
                    >
                      <option value="python-unittest">Python unittest</option>
                      <option value="node-test">Node test runner</option>
                    </select>
                  </label>
                  <label>
                    Provider mode
                    <select
                      value={mode}
                      onChange={(e) => setMode(e.target.value)}
                    >
                      <option value="live">Live coding model</option>
                      <option value="mock">
                        Fixture patch · review required
                      </option>
                    </select>
                  </label>
                </div>
                <div className="form-grid">
                  <label>
                    Reviewer diversity
                    <select
                      aria-label="Reviewer diversity"
                      value={reviewPolicy}
                      onChange={(event) => setReviewPolicy(event.target.value)}
                    >
                      <option value="prefer_provider">
                        Prefer another provider; report reduced diversity
                      </option>
                      <option value="require_provider">
                        Require another provider
                      </option>
                      <option value="require_model">
                        Require another model
                      </option>
                    </select>
                  </label>
                  <label>
                    Independent reviews
                    <select
                      aria-label="Independent reviews"
                      value={reviewCount}
                      onChange={(event) => setReviewCount(event.target.value)}
                    >
                      <option value="1">1 review</option>
                      <option value="2">2 reviews</option>
                    </select>
                  </label>
                </div>
                <Button type="submit" disabled={!repos.length || busy}>
                  Create coding task
                </Button>
              </form>
            </Panel>
          </div>
          {repos.map((r) => (
            <Panel
              key={r.id}
              title={r.name}
              subtitle={`Baseline ${r.baseline_commit || "No Git commit — coding unavailable"}`}
            >
              <Pretty value={r.report} />
            </Panel>
          ))}
          <Panel
            title="Build and test evidence"
            subtitle="Actual restricted-runner results; never inferred from an agent claim"
          >
            {executions.length ? (
              executions.map((e) => (
                <details key={e.id}>
                  <summary>
                    <Badge>{e.status}</Badge> {e.command.join(" ")} · exit{" "}
                    {e.exit_code ?? "pending"}
                  </summary>
                  <p>
                    {e.environment} · Commit {e.commit_hash} ·{" "}
                    {date(e.started_at)}
                  </p>
                  {e.status === "running" && (
                    <Button
                      secondary
                      disabled={busy}
                      onClick={() =>
                        run(
                          () => api(`/executions/${e.id}/reconcile`, {}),
                          "Saved runner result reconciled.",
                        )
                      }
                    >
                      Reconcile saved runner result
                    </Button>
                  )}
                  <Pretty value={e.logs} />
                </details>
              ))
            ) : (
              <Empty
                title="No tests executed"
                text="Tests appear only after an approved coding task runs on the separate Docker runner."
              />
            )}
          </Panel>
          <PublicationControls projectId={project.id} tasks={tasks} />
        </>
      )}
      {tab === "artifacts" && (
        <Panel
          title="Project artifacts"
          subtitle="Saved content with SHA-256 integrity hashes"
        >
          {artifacts.length ? (
            artifacts.map((a) => (
              <details key={a.id}>
                <summary>
                  {a.name} <Badge>{a.kind}</Badge>
                </summary>
                <p className="mono muted">SHA-256: {a.sha256}</p>
                <Pretty value={a.content} />
              </details>
            ))
          ) : (
            <Empty
              title="Artifacts arrive as tasks run"
              text="The durable worker saves authorized results here."
            />
          )}
        </Panel>
      )}
      {details && (
        <div className="modal-overlay" onClick={() => setDetails(null)}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="modal-close"
              onClick={() => setDetails(null)}
              aria-label="Close task"
            >
              ×
            </button>
            <Badge>{details.status}</Badge>
            <h2>{details.objective}</h2>
            <p>
              Assigned to{" "}
              {
                state.agents.find((a) => a.id === details.assigned_agent_id)
                  ?.name
              }
            </p>
            <h3>Acceptance criteria</h3>
            <ul>
              {details.acceptance.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
            <h3>Scope</h3>
            <Pretty value={details.payload} />
            <h3>Execution evidence</h3>
            <Pretty value={details.evidence} />
            <ProjectHistory
              key={details.id}
              projectId={project.id}
              taskId={details.id}
            />
            {details.kind === "coding" &&
              details.status === "awaiting_approval" && (
                <CodingApproval task={details} />
              )}
            <Button
              secondary
              disabled={busy || details.status === "completed"}
              onClick={() => run(() => api(`/tasks/${details.id}/cancel`, {}))}
            >
              Cancel task
            </Button>
          </section>
        </div>
      )}
    </>
  );
}
function SpecialistAssignment({ projectId }: { projectId: string }) {
  const { state, run, busy } = useApp();
  const [agentId, setAgentId] = useState("");
  const [objective, setObjective] = useState("");
  const [acceptance, setAcceptance] = useState("");
  const [mode, setMode] = useState("live");
  const [budget, setBudget] = useState("0.50");
  return (
    <Panel
      title="Assign specialist artifact"
      subtitle="Create scoped document work under this project's approval"
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          run(async () => {
            await api(`/projects/${projectId}/tasks`, {
              agent_id: agentId,
              objective,
              acceptance: acceptance
                .split("\n")
                .map((line) => line.trim())
                .filter(Boolean),
              mode,
              budget_micro: Math.round(Number(budget) * 1000000),
            });
            setObjective("");
            setAcceptance("");
          }, "Specialist task queued. Completion requires a saved, validated artifact.");
        }}
      >
        <div className="form-grid">
          <div>
            <label htmlFor="specialist-agent">Specialist</label>
            <select
              id="specialist-agent"
              required
              value={agentId}
              onChange={(event) => setAgentId(event.target.value)}
            >
              <option value="">Choose a permitted employee</option>
              {state.agents
                .filter(
                  (agent) =>
                    agent.enabled && agent.tools.includes("write_artifact"),
                )
                .map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
            </select>
          </div>
          <div>
            <label htmlFor="specialist-mode">Provider mode</label>
            <select
              id="specialist-mode"
              value={mode}
              onChange={(event) => setMode(event.target.value)}
            >
              <option value="live">Live configured model</option>
              <option value="mock">Explicit local fixture</option>
            </select>
          </div>
        </div>
        <label>
          Task objective
          <textarea
            required
            minLength={10}
            maxLength={10000}
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
          />
        </label>
        <label>
          Acceptance criteria (one per line)
          <textarea
            required
            value={acceptance}
            onChange={(event) => setAcceptance(event.target.value)}
          />
        </label>
        <label>
          Task model budget (USD)
          <input
            type="number"
            required
            min="0"
            max="10000"
            step="0.01"
            value={budget}
            onChange={(event) => setBudget(event.target.value)}
          />
        </label>
        <p className="muted">
          This task produces a document artifact. Engineering changes use the
          separate repository approval and independent QA workflow.
        </p>
        <Button type="submit" disabled={busy}>
          Queue specialist task
        </Button>
      </form>
    </Panel>
  );
}
function CodingApproval({ task }: { task: Task }) {
  const { run, busy } = useApp();
  return (
    <Button
      disabled={busy}
      onClick={() =>
        run(async () => {
          const bytes = new TextEncoder().encode(canonical(task.payload));
          const hash = await crypto.subtle.digest("SHA-256", bytes);
          const hex = Array.from(new Uint8Array(hash))
            .map((v) => v.toString(16).padStart(2, "0"))
            .join("");
          await api(`/tasks/${task.id}/approve`, { content_hash: hex });
        }, "Exact repository-change scope approved.")
      }
    >
      Approve repository modification
    </Button>
  );
}
function canonical(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${canonical(object[k])}`)
    .join(",")}}`;
}
