"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, date } from "@/lib/api";
import { Badge, Button, Panel, Pretty } from "./common";

type Scope = {
  text: string;
  goals: string[];
  functional_requirements: string[];
  nonfunctional_requirements: string[];
  user_roles: string[];
  user_journeys: string[];
  constraints: string[];
  dependencies: string[];
  acceptance_criteria: string[];
  risks: string[];
  out_of_scope: string[];
  open_questions: string[];
};
type Improvement = {
  id: string;
  current_requirement: string;
  gap: string;
  recommendation: string;
  reason: string;
  complexity: string;
  business_impact: string;
  security_performance_impact: string;
  essential: boolean;
};
type Decision = {
  action: "accept" | "reject" | "edit";
  reason: string;
  edited_text: string;
};
type Snapshot = {
  version: number;
  scope_hash: string;
  scope: Scope;
  basis: string;
  created_at: number;
  approval_id?: string | null;
  decisions: Record<string, Decision>;
  answers: Record<string, string>;
  reviews: {
    role: string;
    run_id: string;
    evidence_category: string;
    critique: { proposed_specification: Scope; assumptions: string[] };
  }[];
};
type Review = {
  draft_id: string;
  draft_version: number;
  current: Snapshot;
  history: Snapshot[];
  improvements: Improvement[];
  questions: { id: string; question: string }[];
  approved: boolean;
  project_started: boolean;
  approval_id: string | null;
  approval_expires_at: number | null;
  blocker: string;
};

const fields: [Exclude<keyof Scope, "text">, string][] = [
  ["goals", "Project goals"],
  ["functional_requirements", "Functional requirements"],
  ["nonfunctional_requirements", "Nonfunctional requirements"],
  ["user_roles", "User roles"],
  ["user_journeys", "User journeys"],
  ["constraints", "Scope constraints"],
  ["dependencies", "Dependencies"],
  ["acceptance_criteria", "Scope acceptance criteria"],
  ["risks", "Known risks"],
  ["out_of_scope", "Out of scope"],
  ["open_questions", "Unresolved scope questions"],
];

export function RequirementsReview({
  draftId,
  requirementId,
  onChanged,
}: {
  draftId?: string;
  requirementId?: string;
  onChanged?: () => Promise<unknown>;
}) {
  const [row, setRow] = useState<Review | null>(null);
  const [scope, setScope] = useState<Scope | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [acknowledged, setAcknowledged] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [revising, setRevising] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const dirtyRef = useRef(false);
  const baseVersion = useRef(0);
  const pending = useRef<{ path: string; body: unknown } | null>(null);
  const path = draftId
    ? `/project-drafts/${draftId}/requirements-review`
    : `/requirements/${requirementId}/requirements-review`;
  const load = useCallback(
    async (reset = false) => {
      const result = await api<Review | null>(path);
      setRow(result);
      if (result && (reset || !dirtyRef.current)) {
        setScope(result.current.scope);
        setDecisions({});
        setAnswers({});
        baseVersion.current = result.draft_version;
        dirtyRef.current = false;
        setDirty(false);
        setAcknowledged(false);
        setRevising(false);
      }
    },
    [path],
  );
  useEffect(() => {
    let disposed = false;
    let inFlight = false;
    const refresh = async () => {
      if (disposed || inFlight || dirtyRef.current) return;
      inFlight = true;
      try {
        await load();
      } catch (failure) {
        if (!disposed) setError((failure as Error).message);
      } finally {
        inFlight = false;
      }
    };
    void refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [load]);
  function edit() {
    dirtyRef.current = true;
    setDirty(true);
    setAcknowledged(false);
    setMessage("");
  }
  async function send(command?: { path: string; body: unknown }) {
    if (busy) return;
    const request = pending.current || command;
    if (!request) return;
    pending.current = request;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(request.path, request.body);
      pending.current = null;
      await load(true);
      await onChanged?.();
      setMessage("Your exact requirements decision is saved.");
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!row || !scope)
    return error ? (
      <div role="alert" className="alert warning">
        {error}
      </div>
    ) : null;
  const root = `/project-drafts/${row.draft_id}`;
  const blocked = busy || Boolean(pending.current);
  const readOnly = row.project_started || (row.approved && !revising);
  function revision(reconsider: boolean) {
    if (!row || !scope) return;
    const next = structuredClone(scope);
    if (!reconsider) {
      for (const improvement of row.improvements) {
        const decision = decisions[improvement.id];
        if (decision && decision.action !== "reject") {
          const text =
            decision.action === "edit"
              ? decision.edited_text
              : improvement.recommendation;
          if (
            !next.functional_requirements.includes(text) &&
            !next.nonfunctional_requirements.includes(text)
          )
            next.functional_requirements.push(text);
        }
      }
      const answered = row.questions
        .filter((item) => answers[item.id]?.trim())
        .map((item) => item.question);
      next.open_questions = next.open_questions.filter(
        (question) => !answered.includes(question),
      );
    }
    void send({
      path: `${root}/requirements-revision`,
      body: {
        request_id: crypto.randomUUID(),
        version: baseVersion.current,
        scope: next,
        decisions: reconsider ? {} : decisions,
        answers: reconsider ? {} : answers,
        reconsider,
      },
    });
  }
  return (
    <Panel
      title="Review and refine requirements"
      subtitle="Suggestions stay separate from approved scope. Every saved revision retains its history."
    >
      <div className="control-note">
        <Badge>
          {row.approved ? "requirements approved" : "owner decision required"}
        </Badge>
        <span>
          Requirements version {row.current.version} ·{" "}
          {row.current.basis.replaceAll("_", " ")}
        </span>
      </div>
      {row.blocker && <p>{row.blocker}</p>}
      {row.approved && !row.project_started && !revising && (
        <Button
          secondary
          disabled={blocked}
          onClick={() => {
            setRevising(true);
            edit();
          }}
        >
          Revise approved requirements
        </Button>
      )}
      {error && (
        <div role="alert" className="alert warning">
          {error}
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {row.current.reviews.length === 0 && (
        <p>
          No model critique exists for this scope version. You can wait for an
          eligible model or write and explicitly approve your own scope. Model
          review is never implied.
        </p>
      )}
      {row.current.reviews.map((review) => (
        <details key={review.run_id}>
          <summary>
            {review.role === "lead_intake" ? "Lead AI" : review.role} critique ·{" "}
            {review.evidence_category}
          </summary>
          <p>Execution reference: {review.run_id}</p>
          <Pretty value={review.critique} />
          <Button
            secondary
            disabled={blocked || readOnly}
            onClick={() => {
              setScope(structuredClone(review.critique.proposed_specification));
              edit();
            }}
          >
            Use {review.role === "lead_intake" ? "Lead AI" : review.role}{" "}
            proposed specification as editable draft
          </Button>
        </details>
      ))}
      {row.improvements.length > 0 && (
        <p>
          Review each recommendation: accept, reject or edit it. Accepted
          changes appear in the next saved specification for your sign-off.
        </p>
      )}
      {row.improvements.map((item, index) => (
        <div className="control-note" key={item.id}>
          <div style={{ minWidth: 0, width: "100%" }}>
            <h3>
              {index + 1}. {item.recommendation}
            </h3>
            <p>Current: {item.current_requirement}</p>
            <p>Gap: {item.gap}</p>
            <p>
              {item.reason} · Complexity: {item.complexity} ·{" "}
              {item.essential
                ? "Essential recommendation"
                : "Optional recommendation"}
            </p>
            <p>Business impact: {item.business_impact}</p>
            <p>Security / performance: {item.security_performance_impact}</p>
            <label>
              Decision for recommendation {index + 1}
              <select
                aria-label={`Decision for recommendation ${index + 1}`}
                disabled={blocked || readOnly}
                value={decisions[item.id]?.action || ""}
                onChange={(event) => {
                  setDecisions({
                    ...decisions,
                    [item.id]: {
                      reason: decisions[item.id]?.reason || "",
                      edited_text: decisions[item.id]?.edited_text || "",
                      action: event.target.value as Decision["action"],
                    },
                  });
                  edit();
                }}
              >
                <option value="" disabled>
                  Choose a decision
                </option>
                <option value="accept">Accept</option>
                <option value="reject">Reject</option>
                <option value="edit">Edit</option>
              </select>
            </label>
            <label>
              Reason for recommendation {index + 1}
              <input
                maxLength={2000}
                disabled={blocked || readOnly || !decisions[item.id]}
                value={decisions[item.id]?.reason || ""}
                onChange={(event) => {
                  setDecisions({
                    ...decisions,
                    [item.id]: {
                      ...decisions[item.id],
                      reason: event.target.value,
                    },
                  });
                  edit();
                }}
              />
            </label>
            {decisions[item.id]?.action === "edit" && (
              <label>
                Edited recommendation {index + 1}
                <textarea
                  maxLength={2000}
                  disabled={blocked || readOnly}
                  value={decisions[item.id].edited_text}
                  onChange={(event) => {
                    setDecisions({
                      ...decisions,
                      [item.id]: {
                        ...decisions[item.id],
                        edited_text: event.target.value,
                      },
                    });
                    edit();
                  }}
                />
              </label>
            )}
          </div>
        </div>
      ))}
      {row.questions.map((item, index) => (
        <label key={item.id}>
          Clarification {index + 1}: {item.question}
          <textarea
            maxLength={2000}
            disabled={blocked || readOnly}
            value={answers[item.id] || ""}
            onChange={(event) => {
              setAnswers({ ...answers, [item.id]: event.target.value });
              edit();
            }}
          />
        </label>
      ))}
      <label>
        Reviewed requirements
        <textarea
          rows={5}
          maxLength={30000}
          disabled={blocked || readOnly}
          value={scope.text}
          onChange={(event) => {
            setScope({ ...scope, text: event.target.value });
            edit();
          }}
        />
      </label>
      <label>
        Scope acceptance criteria
        <textarea
          rows={3}
          disabled={blocked || readOnly}
          value={scope.acceptance_criteria.join("\n")}
          onChange={(event) => {
            setScope({
              ...scope,
              acceptance_criteria: event.target.value
                .split("\n")
                .filter(Boolean),
            });
            edit();
          }}
        />
      </label>
      <details>
        <summary>
          Structured specification · goals, roles, risks and constraints
        </summary>
        {fields
          .filter(([key]) => key !== "acceptance_criteria")
          .map(([key, title]) => (
            <label key={key}>
              {title}
              <textarea
                rows={2}
                disabled={blocked || readOnly}
                value={scope[key].join("\n")}
                onChange={(event) => {
                  setScope({
                    ...scope,
                    [key]: event.target.value.split("\n").filter(Boolean),
                  });
                  edit();
                }}
              />
            </label>
          ))}
      </details>
      {(!row.approved || revising) && !row.project_started && (
        <>
          <div className="wizard-toolbar">
            <Button disabled={blocked} onClick={() => revision(false)}>
              Save reviewed scope version
            </Button>
            <Button secondary disabled={blocked} onClick={() => revision(true)}>
              Ask AI to reconsider
            </Button>
          </div>
          <label>
            <input
              type="checkbox"
              checked={acknowledged}
              disabled={
                blocked || dirty || row.current.basis !== "owner_authored"
              }
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            I reviewed this exact saved scope. This is my approval; model
            critique is advisory and may be unavailable.
          </label>
          <Button
            disabled={blocked || dirty || !acknowledged}
            onClick={() =>
              void send({
                path: `${root}/requirements-approve`,
                body: {
                  request_id: crypto.randomUUID(),
                  version: row.draft_version,
                  scope_hash: row.current.scope_hash,
                  owner_authored: true,
                },
              })
            }
          >
            Approve exact requirements version {row.current.version}
          </Button>
        </>
      )}
      {row.approval_id && (
        <p>
          Approval {row.approval_id} · expires{" "}
          {row.approval_expires_at ? date(row.approval_expires_at) : "unknown"}.
          Architecture, execution, publication and release need their separate
          approvals.
        </p>
      )}
      <div className="wizard-toolbar">
        {pending.current && (
          <Button secondary disabled={busy} onClick={() => void send()}>
            Retry the same requirements decision
          </Button>
        )}
        <Button
          secondary
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await load(true);
              pending.current = null;
            } catch (failure) {
              setError((failure as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Reload saved requirements
        </Button>
      </div>
      <details>
        <summary>
          Requirement version history · {row.history.length + 1} saved versions
        </summary>
        {[...row.history, row.current].map((entry) => (
          <details key={entry.version}>
            <summary>
              Version {entry.version} · {entry.basis.replaceAll("_", " ")} ·{" "}
              {date(entry.created_at)}
            </summary>
            <p>
              Scope hash:{" "}
              <code style={{ overflowWrap: "anywhere" }}>
                {entry.scope_hash}
              </code>
            </p>
            <Pretty value={entry} />
          </details>
        ))}
      </details>
    </Panel>
  );
}
