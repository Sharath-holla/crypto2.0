"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Json } from "@/lib/types";
import { Badge, Button, Empty, Panel, Pretty, useApp } from "./common";

type Readiness = {
  ready: boolean;
  blockers: string[];
  source_hash: string;
  manifest: { tasks: Json[]; acceptance: string[]; mode: string };
};

export function DeliveryControls({ projectId }: { projectId: string }) {
  const { state, run, busy } = useApp();
  const [mode, setMode] = useState("live");
  const [evidence, setEvidence] = useState<Readiness | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const pending = useRef<{ source: string; id: string } | null>(null);
  useEffect(() => {
    let active = true;
    setEvidence(null);
    setError("");
    setLoading(true);
    api<Readiness>(`/projects/${projectId}/delivery-readiness?mode=${mode}`)
      .then((value) => {
        if (active) setEvidence(value);
      })
      .catch((cause: unknown) => {
        if (active) setError(String(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, mode]);
  const reviews = state.records.filter(
    (record) =>
      record.project_id === projectId && record.kind === "delivery_review",
  );
  return (
    <Panel
      title="Final review readiness"
      subtitle="CTO → QA → Security → Project Manager → Finance · saved evidence at every checkpoint"
    >
      <p className="muted">
        Review checks the current approved workforce, completed task evidence
        and project budget. This step does not release a package, deploy
        software or record client acceptance. Deterministic fixtures cannot
        certify live work.
      </p>
      <label>
        Final review execution mode
        <select
          value={mode}
          disabled={busy || loading}
          onChange={(event) => setMode(event.target.value)}
        >
          <option value="live">Live configured zero-cost model</option>
          <option value="mock">
            Explicit deterministic fixture · no delivery
          </option>
        </select>
      </label>
      {error && <p className="alert warning">{error}</p>}
      {loading && <p className="muted">Checking saved project evidence…</p>}
      {evidence && (
        <>
          <p>
            <Badge>
              {evidence.ready ? "Ready for review" : "Review blocked"}
            </Badge>{" "}
            {evidence.manifest.tasks.length} saved tasks ·{" "}
            {evidence.manifest.acceptance.length} approved acceptance criteria
          </p>
          <p className="mono muted" style={{ overflowWrap: "anywhere" }}>
            Source SHA-256: {evidence.source_hash}
          </p>
          <ul aria-label="Final review blockers">
            {evidence.blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </>
      )}
      <div className="button-row">
        <Button
          secondary
          disabled={busy || loading}
          onClick={() =>
            run(async () => {
              setEvidence(
                await api<Readiness>(
                  `/projects/${projectId}/delivery-readiness?mode=${mode}`,
                ),
              );
              setError("");
            })
          }
        >
          Refresh review readiness
        </Button>
        <Button
          disabled={
            busy ||
            loading ||
            !evidence?.ready ||
            reviews.some((row) => row.status === "reviewing")
          }
          onClick={() =>
            run(async () => {
              if (!evidence) return;
              const source = `${projectId}:${mode}:${evidence.source_hash}`;
              if (pending.current?.source !== source) {
                pending.current = { source, id: crypto.randomUUID() };
              }
              await api(`/projects/${projectId}/final-review`, {
                request_id: pending.current.id,
                source_hash: evidence.source_hash,
                mode,
              });
              pending.current = null;
            }, "Final review queued against this exact saved evidence. No delivery was released.")
          }
        >
          Queue five-role final review
        </Button>
      </div>
      {reviews.length ? (
        reviews.map((record) => {
          const work = state.agent_work.find(
            (row) => row.subject_id === record.id,
          );
          const workflow = state.workflows.find(
            (row) => row.id === work?.workflow_id,
          );
          const rows = Array.isArray(record.data.reviews)
            ? record.data.reviews
            : [];
          return (
            <details key={record.id}>
              <summary>
                <Badge>{record.status}</Badge> {record.title} · {rows.length}/5
                saved reviews
              </summary>
              <p>
                Mode: {String(record.data.mode)} · Workflow:{" "}
                {workflow?.status || "unavailable"}
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
                      run(() =>
                        api(`/workflows/${workflow.id}/control`, {
                          action:
                            workflow.status === "paused" ? "resume" : "pause",
                        }),
                      )
                    }
                  >
                    {workflow.status === "paused"
                      ? "Resume final review"
                      : "Pause final review"}
                  </Button>
                )}
              {rows.map((value, index) => {
                if (!value || typeof value !== "object" || Array.isArray(value))
                  return null;
                const findings = Array.isArray(value.findings)
                  ? value.findings
                  : [];
                return (
                  <section
                    className="control-note"
                    key={String(value.artifact_id || index)}
                  >
                    <div style={{ minWidth: 0 }}>
                      <h3>
                        {String(value.role)}{" "}
                        <Badge>
                          {value.approved && !findings.length
                            ? "Clear"
                            : "Findings"}
                        </Badge>
                      </h3>
                      <p>{String(value.summary)}</p>
                      {findings.length > 0 && (
                        <ul>
                          {findings.map((finding, number) => (
                            <li key={number}>{String(finding)}</li>
                          ))}
                        </ul>
                      )}
                      <details>
                        <summary>Saved review evidence</summary>
                        <Pretty value={value} />
                      </details>
                    </div>
                  </section>
                );
              })}
              {work &&
                workflow &&
                !["completed", "cancelled"].includes(workflow.status) && (
                  <Button
                    secondary
                    disabled={busy}
                    onClick={() =>
                      run(
                        () => api(`/agent-work/${work.id}/cancel`, {}),
                        "Review cancelled. Its saved evidence is preserved; a fresh review requires current readiness.",
                      )
                    }
                  >
                    Cancel final review
                  </Button>
                )}
            </details>
          );
        })
      ) : (
        <Empty
          title="No saved final reviews"
          text="Complete the blockers above, then explicitly queue a review. Saved reviews and failures appear here."
        />
      )}
    </Panel>
  );
}
