"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, date, money } from "@/lib/api";
import { Badge, Button, Panel, Pretty, useApp } from "./common";

type Case = {
  id: string;
  status: string;
  version: number;
  case_hash: string;
  title: string;
  data: {
    kind: string;
    reason: string;
    analysis_task_id?: string;
    assigned_role: string;
    scope?: {
      impact: {
        summary: string;
        components: string[];
        acceptance: string[];
        budget_micro: number;
      };
    };
    repair_tasks?: { task_id: string }[];
    public_resolution?: string;
    attachments?: { name: string; sha256: string; bytes: number }[];
  };
};

function CaseControls({
  item,
  projectId,
  reload,
}: {
  item: Case;
  projectId: string;
  reload: () => Promise<void>;
}) {
  const { state, run, busy } = useApp();
  const [mode, setMode] = useState("live");
  const [summary, setSummary] = useState("");
  const [components, setComponents] = useState("");
  const [acceptance, setAcceptance] = useState("");
  const [budget, setBudget] = useState("0");
  const [resolution, setResolution] = useState("");
  const [kind, setKind] = useState(
    item.data.kind === "report_defect" ? "coding" : "document",
  );
  const [repository, setRepository] = useState("");
  const [component, setComponent] = useState("");
  const pending = useRef<{ key: string; id: string } | null>(null);
  const analysis = state.artifacts.find(
    (row) =>
      row.task_id === item.data.analysis_task_id && row.kind === "document",
  );
  const invoke = (action: string, value: object) => {
    if (
      !window.confirm(
        `Confirm ${action.replaceAll("-", " ")} for this exact case revision?`,
      )
    )
      return;
    const payload = {
      ...value,
      version: item.version,
      case_hash: item.case_hash,
    };
    const key = JSON.stringify({ action, payload });
    if (pending.current?.key !== key)
      pending.current = { key, id: crypto.randomUUID() };
    const requestId = pending.current.id;
    run(async () => {
      await api(`/delivery-cases/${item.id}/${action}`, {
        ...payload,
        request_id: requestId,
      });
      pending.current = null;
      await reload();
    }, "Case workflow checkpoint saved.");
  };
  return (
    <section className="delivery-package" aria-label={item.title}>
      <div className="panel-heading">
        <h3>{item.title}</h3>
        <Badge>{item.status}</Badge>
      </div>
      <p>{item.data.reason}</p>
      {item.data.attachments?.map((file) => (
        <p key={file.sha256}>
          <a
            href={`/api/delivery-cases/${item.id}/attachments/${file.sha256}`}
            download
          >
            {file.name}
          </a>{" "}
          · {file.bytes} bytes
        </p>
      ))}
      <p>
        Assigned: {item.data.assigned_role} · case revision {item.version}
      </p>
      {item.data.analysis_task_id && (
        <p>
          Saved analysis task: {item.data.analysis_task_id} ·{" "}
          {state.tasks.find((task) => task.id === item.data.analysis_task_id)
            ?.status || "Loading state"}
        </p>
      )}
      {analysis && (
        <details>
          <summary>Inspect analysis document and source hash</summary>
          <p className="mono delivery-hash">{analysis.sha256}</p>
          <Pretty value={analysis.content} />
        </details>
      )}
      {item.status === "submitted" && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            invoke("analyze", {
              mode,
              budget_micro: Math.round(Number(budget) * 1000000),
            });
          }}
        >
          <label>
            Analysis execution
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value)}
            >
              <option value="live">
                Local verified zero-cost model · waits when unavailable
              </option>
              <option value="mock">
                Explicit deterministic test adapter · cannot certify release
              </option>
            </select>
          </label>
          <label>
            Analysis budget cap · USD
            <input
              required
              type="number"
              min="0"
              max="10000"
              step="0.01"
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
            />
          </label>
          <Button type="submit" disabled={busy}>
            Assign saved impact analysis
          </Button>
        </form>
      )}
      {item.status === "analysis_pending" && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!analysis) return;
            invoke("approve-scope", {
              analysis_sha256: analysis.sha256,
              impact: {
                summary,
                components: components.split("\n").filter(Boolean),
                acceptance: acceptance.split("\n").filter(Boolean),
                budget_micro: Math.round(Number(budget) * 1000000),
              },
            });
          }}
        >
          <label>
            Reviewed impact summary
            <textarea
              required
              minLength={20}
              maxLength={2000}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
            />
          </label>
          <label>
            Affected components · one per line
            <textarea
              required
              value={components}
              onChange={(event) => setComponents(event.target.value)}
            />
          </label>
          <label>
            Follow-up acceptance criteria · one per line
            <textarea
              required
              value={acceptance}
              onChange={(event) => setAcceptance(event.target.value)}
            />
          </label>
          <label>
            Approved follow-up budget cap · USD
            <input
              required
              type="number"
              min="0"
              max="10000"
              step="0.01"
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
            />
          </label>
          <Button type="submit" disabled={busy || !analysis}>
            Approve exact analyzed scope
          </Button>
        </form>
      )}
      {item.status === "scope_approved" && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            invoke("create-work", {
              tasks: [
                {
                  kind,
                  component,
                  budget_micro: Math.round(Number(budget) * 1000000),
                  repository_id: kind === "coding" ? repository : null,
                },
              ],
            });
          }}
        >
          <p>
            Approved cap: {money(item.data.scope?.impact.budget_micro)}. Coding
            tasks still require separate exact repository approval.
          </p>
          <label>
            Follow-up component
            <select
              required
              value={component}
              onChange={(event) => setComponent(event.target.value)}
            >
              <option value="">Choose approved component</option>
              {item.data.scope?.impact.components.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            Work type
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              {item.data.kind !== "report_defect" && (
                <option value="document">Specialist document</option>
              )}
              <option value="coding">
                Restricted engineering with independent review and QA
              </option>
            </select>
          </label>
          {kind === "coding" && (
            <label>
              Registered project repository
              <select
                required
                value={repository}
                onChange={(event) => setRepository(event.target.value)}
              >
                <option value="">Select repository</option>
                {state.repositories
                  .filter((row) => row.project_id === projectId)
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
              </select>
            </label>
          )}
          <label>
            Task budget cap · USD
            <input
              required
              type="number"
              min="0"
              max="10000"
              step="0.01"
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
            />
          </label>
          <Button type="submit" disabled={busy}>
            Create approved follow-up tasks
          </Button>
        </form>
      )}
      {item.data.repair_tasks?.map((row) => (
        <p key={row.task_id}>
          Follow-up task {row.task_id} ·{" "}
          <Badge>
            {state.tasks.find((task) => task.id === row.task_id)?.status ||
              "Loading state"}
          </Badge>
        </p>
      ))}
      {["engineering_pending", "fixture_verified"].includes(item.status) && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            invoke("resolve", { public_resolution: resolution });
          }}
        >
          <label>
            Client-facing resolution summary
            <textarea
              required
              minLength={20}
              maxLength={4000}
              value={resolution}
              onChange={(event) => setResolution(event.target.value)}
            />
          </label>
          <Button type="submit" disabled={busy}>
            Verify completed work and resolve case
          </Button>
        </form>
      )}
      {item.data.public_resolution && <p>{item.data.public_resolution}</p>}
      {item.status === "fixture_verified" && (
        <p className="alert warning">
          Deterministic evidence only. This case remains a blocker for live
          release and closure.
        </p>
      )}
      <details>
        <summary>Inspect case evidence and approval history</summary>
        <Pretty value={item} />
      </details>
      {[
        "scope_approved",
        "engineering_pending",
        "fixture_verified",
        "resolved",
      ].includes(item.status) && (
        <Button
          secondary
          disabled={busy}
          onClick={() => {
            const reason = window.prompt(
              "Reason for a new impact analysis and scope revision (at least 20 characters)",
            );
            if (reason && reason.length >= 20) invoke("revise", { reason });
          }}
        >
          Revise case scope and retain history
        </Button>
      )}
    </section>
  );
}

export function DeliveryFollowups({ projectId }: { projectId: string }) {
  const { state, run, busy } = useApp();
  const [cases, setCases] = useState<Case[]>([]);
  const [error, setError] = useState("");
  const [stage, setStage] = useState<{
    stage: string;
    timeline: { id: string; created_at: number; new: string; actor: string }[];
  } | null>(null);
  const [closure, setClosure] = useState<{
    ready: boolean;
    blockers: string[];
    version: number;
    closure_hash?: string;
    manifest?: unknown;
  } | null>(null);
  const pending = useRef<{ key: string; id: string } | null>(null);
  const project = state.projects.find((row) => row.id === projectId);
  const reload = useCallback(async () => {
    const [requests, status, gate] = await Promise.all([
      api<Case[]>(`/projects/${projectId}/delivery-cases`),
      api<NonNullable<typeof stage>>(`/projects/${projectId}/delivery-state`),
      api<NonNullable<typeof closure>>(
        `/projects/${projectId}/closure-readiness`,
      ),
    ]);
    setCases(requests);
    setStage(status);
    setClosure(gate);
    setError("");
  }, [projectId]);
  useEffect(() => {
    reload().catch((cause) => setError(String(cause)));
  }, [reload, state.organization.version]);
  const approval = state.approvals.find(
    (row) =>
      row.category === "delivery_closure" &&
      row.subject_id === projectId &&
      row.version === project?.version &&
      row.expires_at * 1000 > Date.now(),
  );
  const invoke = (action: string, reason?: string) => {
    if (
      !project ||
      !window.confirm(`Confirm ${action} for this exact project revision?`)
    )
      return;
    const payload =
      action === "reopen"
        ? { version: project.version, reason }
        : {
            version: closure?.version,
            closure_hash: closure?.closure_hash,
            ...(action === "close" ? { approval_id: approval?.id } : {}),
          };
    const key = JSON.stringify({ action, payload });
    if (pending.current?.key !== key)
      pending.current = { key, id: crypto.randomUUID() };
    const requestId = pending.current.id;
    run(async () => {
      await api(`/projects/${projectId}/${action}`, {
        ...payload,
        request_id: requestId,
      });
      pending.current = null;
      await reload();
    }, "Project closure decision saved.");
  };
  return (
    <Panel
      title="Client follow-ups and project closure"
      subtitle="Formal acceptance, approved revisions and retained evidence."
    >
      {error && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      <p>
        Delivery stage: <Badge>{stage?.stage || "Loading saved state"}</Badge>
      </p>
      <Button secondary disabled={busy} onClick={() => run(reload)}>
        Refresh cases and closure
      </Button>
      {cases.map((item) => (
        <CaseControls
          key={item.id}
          item={item}
          projectId={projectId}
          reload={reload}
        />
      ))}
      <details>
        <summary>Recorded delivery timeline</summary>
        {stage?.timeline.map((item) => (
          <p key={item.id}>
            {date(item.created_at)} · {item.new} · actor {item.actor}
          </p>
        ))}
      </details>
      <details>
        <summary>Owner project closure gate</summary>
        {closure?.blockers.map((row) => (
          <p className="alert warning" key={row}>
            {row}
          </p>
        ))}
        {closure?.manifest !== undefined && <Pretty value={closure.manifest} />}
        <p className="mono delivery-hash">
          Closure SHA-256: {closure?.closure_hash || "Not ready"}
        </p>
        <div className="button-row">
          <Button
            disabled={busy || !closure?.ready}
            onClick={() => invoke("approve-closure")}
          >
            Approve exact project closure
          </Button>
          <Button
            disabled={busy || !closure?.ready || !approval}
            onClick={() => invoke("close")}
          >
            Close accepted project
          </Button>
          {project?.status === "closed" && (
            <Button
              secondary
              disabled={busy}
              onClick={() => {
                const reason = window.prompt(
                  "Reason to reopen (at least 20 characters)",
                );
                if (reason && reason.length >= 20) invoke("reopen", reason);
              }}
            >
              Reopen project with retained acceptance
            </Button>
          )}
        </div>
      </details>
    </Panel>
  );
}
