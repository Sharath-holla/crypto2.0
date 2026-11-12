"use client";
import { useEffect, useRef, useState } from "react";
import { api, date } from "@/lib/api";
import { Badge, Button, Panel, Pretty, useApp } from "./common";

type Target = {
  id: string;
  title: string;
  data: { config: { environment: string } };
};
type Plan = {
  id: string;
  title: string;
  version: number;
  status: string;
  data: {
    manifest_hash: string;
    approval_id: string | null;
    manifest: {
      environment: string;
      operation: string;
      risk_summary: string;
      source: { artifact_hash: string };
      required_approvals: string[];
    };
  };
};
type Receipt = {
  id: string;
  status: string;
  integrity_valid: boolean;
  data: {
    body: {
      target_id: string;
      package_id: string;
      revision: string;
      environment: string;
      ended_at: number;
      operation: string;
    };
  };
};
type Evidence = {
  deployments_paused: boolean;
  release_blocker: string;
  targets: Target[];
  plans: Plan[];
  receipts: Receipt[];
  packages: {
    id: string;
    version: number;
    status: string;
    classification: string;
  }[];
  blockers: { plan_id: string; reason: string }[];
  incidents: {
    id: string;
    title: string;
    status: string;
    data: { target_id: string; attempts: number; error: string };
  }[];
  jobs: {
    id: string;
    subject_id: string;
    result: { job_id?: string };
    workflow: { status: string; step: number; last_error: string };
  }[];
};

export function DeploymentControls({ projectId }: { projectId: string }) {
  const { run, busy } = useApp();
  const [saved, setSaved] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("Staging simulation");
  const [environment, setEnvironment] = useState("staging");
  const [targetId, setTargetId] = useState("");
  const [packageId, setPackageId] = useState("");
  const [risk, setRisk] = useState(
    "Isolated nonproduction simulation. No real infrastructure is changed.",
  );
  const [scenario, setScenario] = useState("healthy");
  const [incidentId, setIncidentId] = useState("");
  const [receiptId, setReceiptId] = useState("");
  const ids = useRef<Record<string, string>>({});
  const refresh = async () => {
    setSaved(await api<Evidence>(`/projects/${projectId}/deployments`));
    setError("");
  };
  useEffect(() => {
    let active = true;
    api<Evidence>(`/projects/${projectId}/deployments`)
      .then((value) => {
        if (active) setSaved(value);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [projectId]);
  const mutate = (path: string, body: unknown, key?: string) =>
    void run(async () => {
      await api(path, body);
      if (key) delete ids.current[key];
      await refresh();
    });
  const requestId = (key: string) => (ids.current[key] ??= crypto.randomUUID());
  return (
    <div
      className="deployment-controls"
      role="region"
      aria-label="Deployment orchestration"
    >
      <Panel
        title="Deployment"
        subtitle="Review exact plans, approve simulations, inspect health evidence and recover failures."
      >
        <Badge>SIMULATED_NONPRODUCTION</Badge>
        <p>
          No live deployment adapter is configured. No files are uploaded,
          targets contacted or resources provisioned.
        </p>
        {error && <p role="alert">{error}</p>}
        <Button secondary disabled={busy} onClick={() => void run(refresh)}>
          Refresh deployment evidence
        </Button>
        {!saved ? (
          <p role="status">
            {error
              ? "Deployment evidence unavailable. Retry refresh."
              : "Loading deployment evidence…"}
          </p>
        ) : (
          <>
            <p className="notice">{saved.release_blocker}</p>
            {saved.deployments_paused && (
              <div className="notice">
                <p>
                  Company deployment controls are paused. Prepare plans now;
                  execution waits for you to resume.
                </p>
                <Button
                  disabled={busy}
                  onClick={() =>
                    mutate("/controls", { action: "resume_deployments" })
                  }
                >
                  Resume company deployments
                </Button>
              </div>
            )}
            <details>
              <summary>Create a simulation target</summary>
              <div className="form-grid">
                <label>
                  Target name
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label>
                  Target environment
                  <select
                    aria-label="Target environment"
                    value={environment}
                    onChange={(e) => setEnvironment(e.target.value)}
                  >
                    <option value="staging">Staging</option>
                    <option value="production">
                      Production approval contract (simulation)
                    </option>
                  </select>
                </label>
                <Button
                  disabled={busy || name.length < 3}
                  onClick={() => {
                    const key = `target:${name}:${environment}`;
                    mutate(
                      `/projects/${projectId}/deployment-targets`,
                      {
                        request_id: requestId(key),
                        name,
                        environment,
                        adapter: "simulation",
                      },
                      key,
                    );
                  }}
                >
                  Save simulation target
                </Button>
              </div>
            </details>
            <h3>Prepare an exact deployment plan</h3>
            <div className="form-grid">
              <label>
                Frozen release package
                <select
                  aria-label="Frozen release package"
                  value={packageId}
                  onChange={(e) => setPackageId(e.target.value)}
                >
                  <option value="">Select a frozen package</option>
                  {saved.packages
                    .filter((p) =>
                      ["package_ready", "awaiting_release_approval"].includes(
                        p.status,
                      ),
                    )
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        Version {p.version} · {p.classification} ·{" "}
                        {p.id.slice(0, 8)}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Deployment target
                <select
                  aria-label="Deployment target"
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                >
                  <option value="">Select a target</option>
                  {saved.targets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.title} · {t.data.config.environment}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Risk assessment
                <textarea
                  value={risk}
                  onChange={(e) => setRisk(e.target.value)}
                />
              </label>
              <label>
                Explicit simulation outcome
                <select
                  aria-label="Explicit simulation outcome"
                  value={scenario}
                  onChange={(e) => setScenario(e.target.value)}
                >
                  {[
                    "healthy",
                    "health_failure",
                    "health_timeout",
                    "partial_failure",
                    "wrong_revision",
                  ].map((s) => (
                    <option key={s} value={s}>
                      {s.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Recovery incident (optional)
                <select
                  aria-label="Recovery incident (optional)"
                  value={incidentId}
                  onChange={(e) => {
                    setIncidentId(e.target.value);
                    setReceiptId("");
                  }}
                >
                  <option value="">New deployment</option>
                  {saved.incidents
                    .filter(
                      (i) =>
                        i.status === "open" && i.data.target_id === targetId,
                    )
                    .map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.title} · {i.data.attempts}/3 attempts
                      </option>
                    ))}
                </select>
              </label>
              {incidentId && (
                <label>
                  Known healthy rollback receipt
                  <select
                    aria-label="Known healthy rollback receipt"
                    value={receiptId}
                    onChange={(e) => setReceiptId(e.target.value)}
                  >
                    <option value="">Select prior verified artifact</option>
                    {saved.receipts
                      .filter(
                        (r) =>
                          r.integrity_valid &&
                          r.status === "deployment_completed" &&
                          r.data.body.target_id === targetId &&
                          r.data.body.package_id === packageId,
                      )
                      .map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.id.slice(0, 8)} ·{" "}
                          {r.data.body.revision.slice(0, 12)}
                        </option>
                      ))}
                  </select>
                </label>
              )}
            </div>
            <Button
              disabled={
                busy ||
                !targetId ||
                !packageId ||
                risk.length < 10 ||
                (!!incidentId && !receiptId)
              }
              onClick={() => {
                const body = {
                  package_id: packageId,
                  target_id: targetId,
                  risk_summary: risk,
                  scenario,
                  ...(incidentId
                    ? {
                        incident_id: incidentId,
                        rollback_receipt_id: receiptId,
                      }
                    : {}),
                };
                const key = `plan:${JSON.stringify(body)}`;
                mutate(
                  `/projects/${projectId}/deployment-plans`,
                  { ...body, request_id: requestId(key) },
                  key,
                );
              }}
            >
              {incidentId ? "Prepare rollback plan" : "Prepare deployment plan"}
            </Button>
            {!saved.packages.some((p) =>
              ["package_ready", "awaiting_release_approval"].includes(p.status),
            ) && (
              <p>
                Freeze a complete delivery package before preparing a
                deployment.
              </p>
            )}
            {saved.plans.map((plan) => {
              const job = saved.jobs.find((j) => j.subject_id === plan.id);
              const blocker = saved.blockers.find((b) => b.plan_id === plan.id);
              const terminal =
                job && ["completed", "cancelled"].includes(job.workflow.status);
              return (
                <article
                  className="timeline-item"
                  key={plan.id}
                  aria-label={plan.title}
                >
                  <h3>{plan.title}</h3>
                  <Badge>{plan.status}</Badge>
                  <p>{plan.data.manifest.risk_summary}</p>
                  <p>
                    Artifact:{" "}
                    <code>{plan.data.manifest.source.artifact_hash}</code>
                  </p>
                  <p>
                    Approval:{" "}
                    {plan.data.approval_id || "Waiting for your exact approval"}
                  </p>
                  {blocker && <p className="notice">{blocker.reason}</p>}
                  <details>
                    <summary>Exact manifest and approval binding</summary>
                    <Pretty value={plan.data} />
                  </details>
                  {plan.status === "awaiting_approval" && (
                    <Button
                      disabled={busy}
                      onClick={() =>
                        mutate(`/deployment-plans/${plan.id}/approve`, {
                          version: plan.version,
                          manifest_hash: plan.data.manifest_hash,
                        })
                      }
                    >
                      Approve exact {plan.data.manifest.environment}{" "}
                      {plan.data.manifest.operation} simulation
                    </Button>
                  )}
                  {plan.status === "approved" && !job && (
                    <Button
                      disabled={busy || !!blocker}
                      onClick={() => {
                        const key = `run:${plan.id}`;
                        mutate(
                          `/deployment-plans/${plan.id}/run`,
                          {
                            request_id: requestId(key),
                            manifest_hash: plan.data.manifest_hash,
                          },
                          key,
                        );
                      }}
                    >
                      Run approved simulation
                    </Button>
                  )}
                  {![
                    "revoked",
                    "cancelled",
                    "deployment_completed",
                    "deployment_failed",
                  ].includes(plan.status) && (
                    <Button
                      secondary
                      disabled={busy}
                      onClick={() =>
                        mutate(`/deployment-plans/${plan.id}/revoke`, {})
                      }
                    >
                      Revoke deployment approval
                    </Button>
                  )}
                  {job && (
                    <>
                      <p>
                        Workflow: {job.workflow.status} · saved checkpoint{" "}
                        {job.workflow.step} · job{" "}
                        {job.result.job_id || "awaiting dispatch"}
                      </p>
                      {job.workflow.last_error && (
                        <p role="alert">{job.workflow.last_error}</p>
                      )}
                      {!terminal && (
                        <div className="actions">
                          {["queued", "running"].includes(
                            job.workflow.status,
                          ) && (
                            <Button
                              secondary
                              disabled={busy}
                              onClick={() =>
                                mutate(`/deployments/${job.id}/commands`, {
                                  action: "pause",
                                })
                              }
                            >
                              Pause deployment
                            </Button>
                          )}
                          {["paused", "needs_attention", "failed"].includes(
                            job.workflow.status,
                          ) && (
                            <Button
                              disabled={busy || !!blocker}
                              onClick={() =>
                                mutate(`/deployments/${job.id}/commands`, {
                                  action: "reconcile",
                                })
                              }
                            >
                              Reconcile saved deployment
                            </Button>
                          )}
                          <Button
                            secondary
                            disabled={busy}
                            onClick={() =>
                              mutate(`/deployments/${job.id}/commands`, {
                                action: "cancel",
                              })
                            }
                          >
                            Cancel deployment
                          </Button>
                        </div>
                      )}
                    </>
                  )}
                </article>
              );
            })}
            <h3>Health receipts and incidents</h3>
            {saved.receipts.length === 0 && (
              <p>No deployment outcomes have been recorded.</p>
            )}
            {saved.receipts.map((receipt) => (
              <details key={receipt.id}>
                <summary>
                  {receipt.data.body.environment} {receipt.data.body.operation}{" "}
                  · {receipt.status} ·{" "}
                  {receipt.integrity_valid
                    ? "Integrity verified"
                    : "Evidence invalid"}{" "}
                  · {date(receipt.data.body.ended_at)}
                </summary>
                <Pretty value={receipt} />
              </details>
            ))}
            {saved.incidents.map((incident) => (
              <details key={incident.id}>
                <summary>
                  {incident.title} · {incident.status} ·{" "}
                  {incident.data.attempts}/3 recovery attempts
                </summary>
                <p>{incident.data.error}</p>
                <Pretty value={incident} />
              </details>
            ))}
          </>
        )}
      </Panel>
    </div>
  );
}
