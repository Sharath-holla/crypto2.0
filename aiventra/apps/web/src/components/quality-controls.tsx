"use client";

import { useEffect, useRef, useState } from "react";
import { api, date } from "@/lib/api";
import type { Task } from "@/lib/types";
import { Badge, Button, Panel, Pretty, useApp } from "./common";
import { ProjectHistory } from "./project-history";

type Plan = {
  id: string;
  version: number;
  status: string;
  data: {
    plan_hash: string;
    source: { task_id: string; commit: string };
    plan: { independence: string; exceptions: unknown[] };
  };
};
type Report = {
  id: string;
  data: {
    body: {
      plan_id: string;
      stage: number;
      position: number;
      verdict: string;
      verified_at: number;
      classification: string;
      model_independent: boolean;
      tools: { tests: number; cases: { id: string; status: string }[] };
    };
  };
};
type Defect = {
  id: string;
  title: string;
  status: string;
  version: number;
  data: {
    severity: string;
    repair_tasks: string[];
    verification: string;
  };
};
type Evidence = {
  readiness: {
    ready: boolean;
    blockers: string[];
    manifest_hash: string;
    manifest: { traceability: unknown[] };
  };
  plans: Plan[];
  reports: Report[];
  defects: Defect[];
  jobs: {
    id: string;
    plan_id: string;
    workflow_id: string;
    status: string;
    step: number;
    last_error: string;
    executions: { id: string; status: string; exit_code: number | null }[];
  }[];
};

const rounds = [
  "Implementation Verification",
  "Independent Functional QA",
  "Security & Release Verification",
];

export function QualityControls({
  projectId,
  tasks,
}: {
  projectId: string;
  tasks: Task[];
}) {
  const { run, busy } = useApp();
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [taskId, setTaskId] = useState("");
  const [source, setSource] = useState<unknown>(null);
  const [planText, setPlanText] = useState("");
  const [selected, setSelected] = useState<Defect | null>(null);
  const [resolution, setResolution] = useState("");
  const requests = useRef<Record<string, string>>({});
  const requestId = (key: string) =>
    (requests.current[key] ??= crypto.randomUUID());
  const refresh = async () => {
    const current = await api<Evidence>(`/projects/${projectId}/quality`);
    setEvidence(current);
    setSelected((value) =>
      value
        ? (current.defects.find((row) => row.id === value.id) ?? null)
        : null,
    );
    setError("");
  };
  useEffect(() => {
    let active = true;
    setEvidence(null);
    setError("");
    setSelected(null);
    setTaskId("");
    setSource(null);
    api<Evidence>(`/projects/${projectId}/quality`)
      .then((value) => active && setEvidence(value))
      .catch((cause: unknown) => active && setError(String(cause)));
    return () => {
      active = false;
    };
  }, [projectId]);
  const action = (operation: () => Promise<unknown>) =>
    run(async () => {
      await operation();
      await refresh();
    });
  const latest = evidence?.plans
    .filter((plan) => !taskId || plan.data.source.task_id === taskId)
    .reduce<Plan | null>(
      (value, plan) => (!value || plan.version > value.version ? plan : value),
      null,
    );
  return (
    <section aria-label="Three-stage quality assurance">
      <Panel
        title="Three-stage quality assurance"
        subtitle="Approved tests → isolated tools → independent assessment → exact release gate"
      >
        <p className="muted">
          Results refer to saved source commits. Deterministic model fixtures
          are labeled. Role independence and model independence are shown
          separately. A passed quality gate still requires package verification
          and owner release approval; deployment remains unverified.
        </p>
        {error && <p className="alert warning">{error}</p>}
        {!evidence && !error && <p role="status">Loading saved QA evidence…</p>}
        <div className="button-row">
          <Button secondary disabled={busy} onClick={() => action(refresh)}>
            Refresh QA evidence
          </Button>
          <Button
            secondary
            disabled={busy}
            onClick={() =>
              action(() => api(`/projects/${projectId}/quality-readiness`, {}))
            }
          >
            Save readiness report
          </Button>
        </div>
        {rounds.map((name, index) => {
          const report = evidence?.reports
            .filter(
              (row) =>
                row.data.body.plan_id === latest?.id &&
                row.data.body.stage === index + 1,
            )
            .sort((a, b) => b.data.body.position - a.data.body.position)[0];
          return (
            <details key={name} open={!report}>
              <summary>
                Round {index + 1} — {name}{" "}
                <Badge>{report?.data.body.verdict ?? "Not verified"}</Badge>
              </summary>
              {report ? (
                <>
                  <p>
                    {report.data.body.tools.tests} tests ·{" "}
                    {
                      report.data.body.tools.cases.filter(
                        (c) => c.status === "PASS",
                      ).length
                    }{" "}
                    passed ·{" "}
                    {
                      report.data.body.tools.cases.filter(
                        (c) => c.status === "FAIL",
                      ).length
                    }{" "}
                    failed · {date(report.data.body.verified_at)}
                  </p>
                  <p>
                    {report.data.body.classification} · Model independence:{" "}
                    {report.data.body.model_independent
                      ? "verified"
                      : "not established"}
                  </p>
                  <Pretty value={report} />
                </>
              ) : (
                <p>No completed evidence for the current test plan.</p>
              )}
            </details>
          );
        })}
        {evidence?.jobs.map((job) => (
          <details key={job.id}>
            <summary>
              QA workflow · {job.status} · {job.step} completed rounds
            </summary>
            <Pretty value={job} />
            <div className="button-row">
              {!["completed", "cancelled"].includes(job.status) && (
                <>
                  <Button
                    secondary
                    disabled={busy}
                    onClick={() =>
                      action(() =>
                        api(`/workflows/${job.workflow_id}/control`, {
                          action: job.status === "paused" ? "resume" : "pause",
                        }),
                      )
                    }
                  >
                    {job.status === "paused"
                      ? "Resume QA workflow"
                      : "Pause QA workflow"}
                  </Button>
                  <Button
                    secondary
                    disabled={busy}
                    onClick={() =>
                      action(() => api(`/agent-work/${job.id}/cancel`, {}))
                    }
                  >
                    Cancel QA workflow
                  </Button>
                </>
              )}
              {job.status === "needs_attention" && (
                <Button
                  secondary
                  disabled={busy}
                  onClick={() =>
                    action(() => api(`/workflows/${job.workflow_id}/retry`, {}))
                  }
                >
                  Retry after reconciliation
                </Button>
              )}
              {job.executions
                .filter((execution) => execution.status === "running")
                .map((execution) => (
                  <Button
                    key={execution.id}
                    secondary
                    disabled={busy}
                    onClick={() =>
                      action(() =>
                        api(`/executions/${execution.id}/reconcile`, {}),
                      )
                    }
                  >
                    Reconcile runner job {execution.id.slice(0, 8)}
                  </Button>
                ))}
            </div>
          </details>
        ))}
        {evidence && (
          <>
            <h3>
              {evidence.readiness.ready
                ? "Quality gate passed"
                : "Release blockers"}
            </h3>
            <ul aria-label="Quality release blockers">
              {evidence.readiness.blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
            <details>
              <summary>
                Requirement traceability and exact evidence versions
              </summary>
              <Pretty value={evidence.readiness} />
            </details>
          </>
        )}
        <h3>Defects and repairs</h3>
        {evidence?.defects.length === 0 && <p>No recorded defects.</p>}
        {evidence?.defects.map((defect) => (
          <div key={defect.id}>
            <p>
              <Badge>{defect.data.severity}</Badge> {defect.title} ·{" "}
              {defect.status}
              {" · "}
              {defect.data.repair_tasks.length} repair attempts
            </p>
            <Button
              secondary
              disabled={busy}
              onClick={() => setSelected(defect)}
            >
              Review defect {defect.id.slice(0, 8)}
            </Button>
          </div>
        ))}
        {selected && (
          <div>
            <Pretty value={selected} />
            {selected.data.repair_tasks.map((id) => (
              <ProjectHistory key={id} projectId={projectId} taskId={id} />
            ))}
            <label>
              Repair objective or verification resolution
              <textarea
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
              />
            </label>
            <div className="button-row">
              <Button
                disabled={busy || resolution.trim().length < 10}
                onClick={() =>
                  action(() =>
                    api(`/quality-defects/${selected.id}/repair`, {
                      request_id: requestId(
                        `repair:${selected.id}:${selected.data.repair_tasks.length}`,
                      ),
                      objective: resolution,
                    }),
                  )
                }
              >
                Request repair scope · owner approval required
              </Button>
              {(["verify_close", "reopen"] as const).map((command) => (
                <Button
                  key={command}
                  secondary
                  disabled={busy || resolution.trim().length < 10}
                  onClick={() =>
                    action(async () => {
                      const updated = await api<Defect>(
                        `/quality-defects/${selected.id}/commands`,

                        {
                          version: selected.version,
                          action: command,
                          resolution,
                        },
                      );
                      setSelected(updated);
                    })
                  }
                >
                  {command === "verify_close"
                    ? "Verify repair and close defect"
                    : "Reopen defect"}
                </Button>
              ))}
            </div>
            <p className="muted">
              Repair task IDs above link the saved engineering history. Approve
              their exact coding scope in Engineering. Closure requires three
              fresh passing rounds.
            </p>
          </div>
        )}
        <details>
          <summary>Prepare independent test plan</summary>
          <p>
            Upload or paste an owner-authored JSON test plan. It must cover
            approved requirements, all applicable checks and justified
            exceptions. Test code runs exclusively inside the restricted Docker
            runner. Python is currently supported.
          </p>
          <label>
            Engineering candidate
            <select
              value={taskId}
              onChange={(e) => {
                setTaskId(e.target.value);
                setSource(null);
              }}
            >
              <option value="">Choose completed coding task</option>
              {tasks
                .filter(
                  (task) =>
                    task.kind === "coding" && task.status === "completed",
                )
                .map((task) => (
                  <option key={task.id} value={task.id}>
                    {task.objective}
                  </option>
                ))}
            </select>
          </label>
          <Button
            secondary
            disabled={busy || !taskId}
            onClick={() =>
              action(async () => {
                setSource(await api(`/tasks/${taskId}/quality-source`));
              })
            }
          >
            Inspect exact candidate and required checks
          </Button>
          {source !== null && <Pretty value={source} />}
          <label>
            QA plan JSON
            <textarea
              value={planText}
              onChange={(e) => setPlanText(e.target.value)}
            />
          </label>
          <Button
            disabled={busy || !taskId || !planText.trim()}
            onClick={() =>
              action(() =>
                api(
                  `/tasks/${taskId}/quality-plans`,

                  JSON.parse(planText) as Record<string, unknown>,
                ),
              )
            }
          >
            Save test plan for approval
          </Button>
        </details>
        {[...(evidence?.plans ?? [])]
          .sort((a, b) => b.version - a.version)
          .map((plan) => (
            <details key={plan.id}>
              <summary>
                Test plan v{plan.version} · {plan.status} ·{" "}
                {plan.data.source.commit.slice(0, 12)}
              </summary>
              <Pretty value={plan} />
              <div className="button-row">
                {plan.status === "awaiting_approval" && (
                  <Button
                    disabled={busy}
                    onClick={() =>
                      action(() =>
                        api(`/quality-plans/${plan.id}/approve`, {
                          version: plan.version,
                          content_hash: plan.data.plan_hash,
                        }),
                      )
                    }
                  >
                    Approve exact test plan
                  </Button>
                )}
                {plan.status === "approved" && (
                  <Button
                    disabled={busy}
                    onClick={() =>
                      action(() =>
                        api(`/quality-plans/${plan.id}/run`, {
                          request_id: requestId(
                            `run:${plan.id}:${evidence?.reports.length ?? 0}`,
                          ),
                          plan_hash: plan.data.plan_hash,
                          mode:
                            tasks.find(
                              (task) => task.id === plan.data.source.task_id,
                            )?.payload.mode ?? "live",
                        }),
                      )
                    }
                  >
                    Request three-stage verification
                  </Button>
                )}
              </div>
            </details>
          ))}
      </Panel>
    </section>
  );
}
