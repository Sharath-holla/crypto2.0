"use client";
import { useState } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ClipboardList,
  FileText,
  Plus,
  Send,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { api, money } from "@/lib/api";
import type { Project, Proposal, Requirement } from "@/lib/types";
import { Badge, Button, Empty, Panel, Pretty, useApp } from "./common";
import { RequirementsReview } from "./requirements-review";

export function Consulting({
  approvals,
  initialId = "",
}: {
  approvals: boolean;
  initialId?: string;
}) {
  const { state, run, busy, navigate } = useApp();
  const [selected, setSelected] = useState(initialId);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [client, setClient] = useState(state.clients[0]?.id || "");
  const [mode, setMode] = useState("live");
  const [budget, setBudget] = useState("5");
  const [deadline, setDeadline] = useState("");
  const [constraints, setConstraints] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [rates, setRates] = useState("[]");
  const [source, setSource] = useState("");
  const requirement = state.requirements.find((r) => r.id === selected);
  const proposals = requirement
    ? state.proposals
        .filter((p) => p.requirement_id === requirement.id)
        .sort((a, b) => b.version - a.version)
    : [];
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await run(async () => {
      const result = await api<Requirement>("/requirements", {
        client_id: client,
        title,
        text,
        mode,
        budget_micro: Math.round(Number(budget) * 1000000),
        deadline: deadline || null,
        constraints: constraints ? { notes: constraints } : {},
      });
      setSelected(result.id);
      setShowForm(false);
      setTitle("");
      setText("");
    }, "Requirement recorded. The worker will run a bounded consultation.");
  };
  const open = (r: Requirement) => {
    setSelected(r.id);
    setAnswers(r.answers);
    setRates(JSON.stringify(r.rates, null, 2));
  };
  if (requirement)
    return (
      <>
        <button className="text-button" onClick={() => setSelected("")}>
          ← All {approvals ? "proposals" : "requirements"}
        </button>
        <div className="record-heading">
          <span className="record-icon">
            <FileText size={22} />
          </span>
          <div>
            <h2>{requirement.title}</h2>
            <p>
              {state.clients.find((c) => c.id === requirement.client_id)?.name}{" "}
              · Revision {requirement.version} · Agent budget{" "}
              {money(requirement.budget_micro)}
            </p>
          </div>
          <Badge>{requirement.status}</Badge>
          <Badge mode={requirement.mode}>
            {requirement.mode === "mock" ? "Local fixture" : "Live provider"}
          </Badge>
        </div>
        <div className="lifecycle">
          {[
            "Recorded",
            "Analyzed",
            "Consulted",
            "Proposal",
            "Approved",
            "Project",
          ].map((step, i) => {
            const progress =
              requirement.status === "approved"
                ? 5
                : proposals.length
                  ? 3
                  : requirement.analysis.questions
                    ? 1
                    : 0;
            return (
              <div key={step} className={i <= progress ? "done" : ""}>
                <span>{i <= progress ? <Check size={13} /> : i + 1}</span>
                {step}
              </div>
            );
          })}
        </div>
        <Panel
          title="Client brief"
          subtitle="Recorded requirement; external actions remain approval controlled"
        >
          <p className="brief-text">{requirement.text}</p>
        </Panel>
        <RequirementsReview
          key={requirement.id}
          requirementId={requirement.id}
        />
        {requirement.mode === "mock" && (
          <div className="alert warning">
            This is a deterministic local fixture. Specialist analysis and
            proposal wording do not represent live AI research. No cloud prices
            have been fabricated.
          </div>
        )}
        <div className="two-columns">
          <Panel
            title="Requirements analysis"
            subtitle="Structured Business Analyst output"
          >
            {requirement.analysis.requirements ? (
              <>
                <h3>Confirmed requirements</h3>
                <ul>
                  {requirement.analysis.requirements.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
                <h3>Assumptions</h3>
                <ul>
                  {requirement.analysis.assumptions?.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
                <h3>Acceptance criteria</h3>
                <ul>
                  {requirement.analysis.acceptance_criteria?.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </>
            ) : (
              <Empty
                title="Analysis queued"
                text="Start the worker to process this requirement. Progress refreshes every five seconds."
              />
            )}
          </Panel>
          <Panel
            title="Clarify & revise"
            subtitle="Changing scope invalidates old approvals and pauses related projects"
          >
            <form
              onSubmit={(e) => {
                e.preventDefault();
                run(
                  () =>
                    api(`/requirements/${requirement.id}/clarify`, {
                      version: requirement.version,
                      answers,
                      rates: JSON.parse(rates),
                    }),
                  "Revision queued. Previous proposals superseded.",
                );
              }}
            >
              {requirement.analysis.questions?.map((question) => (
                <label key={question}>
                  {question}
                  <textarea
                    rows={2}
                    value={answers[question] || ""}
                    onChange={(e) =>
                      setAnswers({ ...answers, [question]: e.target.value })
                    }
                  />
                </label>
              ))}
              <details>
                <summary>Source-backed cost inputs (JSON)</summary>
                <p className="muted">
                  Each line needs alternative, label, unit_price_micro,
                  quantity, unit, region, source_url, retrieved_at and one_time.
                  Dollar amounts are stored as integer millionths. Rates are
                  owner-supplied estimates.
                </p>
                <textarea
                  aria-label="Cost inputs JSON"
                  className="mono"
                  rows={8}
                  value={rates}
                  onChange={(e) => setRates(e.target.value)}
                />
              </details>
              <Button type="submit" disabled={busy}>
                Save revision & rerun <ArrowRight size={14} />
              </Button>
            </form>
            <hr />
            <h3>Research evidence</h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                run(
                  () =>
                    api(`/requirements/${requirement.id}/research`, {
                      url: source,
                    }),
                  "Published source saved. Rerun a revision to include it in analysis.",
                );
              }}
            >
              <label>
                Official published source
                <input
                  type="url"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  placeholder="https://cloud.google.com/…"
                  required
                />
              </label>
              <Button secondary type="submit" disabled={busy}>
                Retrieve source
              </Button>
            </form>
            <label className="upload-button">
              <Upload size={15} />
              Attach requirement document
              <input
                type="file"
                accept=".txt,.md,.json"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    const form = new FormData();
                    form.append("file", file);
                    run(
                      () => api(`/requirements/${requirement.id}/upload`, form),
                      "Document saved. Rerun the requirement to include it.",
                    );
                  }
                }}
              />
            </label>
          </Panel>
        </div>
        {proposals.map((p) => (
          <ProposalReview key={p.id} proposal={p} />
        ))}
        <Panel
          title="Workflow execution"
          subtitle="Actual persisted checkpoints, attempts and errors"
        >
          {state.workflows
            .filter((w) => w.requirement_id === requirement.id)
            .map((w) => (
              <div className="workflow-row" key={w.id}>
                <div>
                  <strong>
                    Consultation revision{" "}
                    {
                      state.requirements.find((r) => r.id === w.requirement_id)
                        ?.version
                    }
                  </strong>
                  <small>{w.id}</small>
                </div>
                <span>{w.step}/7 steps persisted</span>
                <Badge>{w.status}</Badge>
                {w.last_error && <p className="error-text">{w.last_error}</p>}
              </div>
            ))}
        </Panel>
      </>
    );
  const list = approvals
    ? state.requirements.filter((r) =>
        state.proposals.some((p) => p.requirement_id === r.id),
      )
    : state.requirements;
  return (
    <>
      <div className="section-banner">
        <ClipboardList size={28} />
        <div>
          <h2>Consult first. Build with confidence.</h2>
          <p>
            Intake → specialist analysis → alternatives → your approval →
            execution.
          </p>
        </div>
        <Button onClick={() => setShowForm(true)}>
          <Plus size={16} />
          Submit requirement
        </Button>
      </div>
      {showForm && (
        <Panel
          title="What should your company solve?"
          subtitle="Describe the objective, constraints and what success looks like."
          action={
            <button className="text-button" onClick={() => setShowForm(false)}>
              Cancel
            </button>
          }
        >
          <form onSubmit={submit}>
            <div className="form-grid">
              <label>
                Client
                <select
                  value={client}
                  onChange={(e) => setClient(e.target.value)}
                  required
                >
                  {state.clients.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Execution mode
                <select
                  aria-label="Execution mode"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  <option value="mock">Local fixture · no live AI</option>
                  <option value="live">
                    Live configured provider · paid usage
                  </option>
                </select>
              </label>
              <label className="full">
                Requirement title
                <input
                  required
                  minLength={3}
                  maxLength={200}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Assess our cloud migration options"
                />
              </label>
              <label className="full">
                Client requirement
                <textarea
                  required
                  minLength={20}
                  rows={6}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Describe the business problem, current systems and desired outcome…"
                />
              </label>
              <label>
                AI consultation budget (USD)
                <input
                  required
                  type="number"
                  min="0"
                  step="0.01"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                />
              </label>
              <label>
                Target deadline
                <input
                  type="date"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                />
              </label>
              <label className="full">
                Constraints & restrictions
                <textarea
                  rows={2}
                  value={constraints}
                  onChange={(e) => setConstraints(e.target.value)}
                  placeholder="Regions, confidential data, preferred technology, downtime…"
                />
              </label>
            </div>
            <div className="form-footer">
              <span>
                <ShieldCheck size={16} />
                Implementation stays blocked until approval.
              </span>
              <Button type="submit" disabled={busy}>
                <Send size={15} />
                Begin consultation
              </Button>
            </div>
          </form>
        </Panel>
      )}
      <Panel
        title={approvals ? "Proposal review queue" : "Recorded requirements"}
        subtitle={`${list.length} records · updates from the durable worker`}
      >
        {list.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Requirement</th>
                  <th>Client</th>
                  <th>Mode</th>
                  <th>Status</th>
                  <th>Revision</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <strong>{r.title}</strong>
                      <small>{r.text.slice(0, 110)}</small>
                    </td>
                    <td>
                      {state.clients.find((c) => c.id === r.client_id)?.name}
                    </td>
                    <td>
                      <Badge mode={r.mode}>{r.mode}</Badge>
                    </td>
                    <td>
                      <Badge>{r.status}</Badge>
                    </td>
                    <td>v{r.version}</td>
                    <td>
                      <button className="text-button" onClick={() => open(r)}>
                        Review <ArrowRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={
              approvals ? "No proposals yet" : "Your first brief belongs here"
            }
            text="Submit a requirement and the company will compare solutions before starting implementation."
            action={
              <Button onClick={() => setShowForm(true)}>
                Submit a requirement
              </Button>
            }
          />
        )}
      </Panel>
    </>
  );
}

function ProposalReview({ proposal: p }: { proposal: Proposal }) {
  const { run, busy, navigate, state } = useApp();
  const [selection, setSelection] = useState(p.content.recommendation);
  const [reason, setReason] = useState("");
  const latest =
    state.requirements.find((r) => r.id === p.requirement_id)?.version ===
    p.version;
  return (
    <Panel
      title={`Solution proposal · v${p.version}`}
      subtitle={`Exact content hash: ${p.content_hash}`}
      action={<Badge>{p.status}</Badge>}
    >
      <div className="proposal-summary">
        <span className="eyebrow">EXECUTIVE RECOMMENDATION</span>
        <h3>{p.content.recommendation}</h3>
        <p>{p.content.executive_summary}</p>
      </div>
      <div className="alternative-grid">
        {p.content.alternatives.map((a) => {
          const cost = p.content.cost_comparison.find(
            (c) => c.alternative === a.name,
          );
          return (
            <button
              className={`alternative-card ${selection === a.name ? "chosen" : ""}`}
              key={a.name}
              onClick={() => setSelection(a.name)}
            >
              <div>
                <span className="radio-dot">
                  {selection === a.name && <i />}
                </span>
                <Badge
                  mode={
                    a.name === p.content.recommendation ? "active" : "neutral"
                  }
                >
                  {a.name === p.content.recommendation
                    ? "Recommended"
                    : "Alternative"}
                </Badge>
              </div>
              <h3>{a.name}</h3>
              <p>{a.architecture}</p>
              <strong className="alternative-cost">
                {money(cost?.recurring_micro)}
                <small> / month</small>
              </strong>
              <span className="cost-label">{cost?.basis}</span>
              <ul>
                {a.advantages.map((v, i) => (
                  <li key={i}>
                    <CheckCircle2 size={13} />
                    {v}
                  </li>
                ))}
              </ul>
              <p className="tradeoff">
                Trade-off: {a.disadvantages.join("; ")}
              </p>
            </button>
          );
        })}
      </div>
      <ArchitectureEvidence proposal={p} />
      <div className="alert warning">
        Cost inputs are partial estimates. Missing compute, storage, data
        transfer, licensing, labor and downtime costs prevent a verified
        cheapest-provider claim.
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Solution</th>
              <th>Recurring / month</th>
              <th>One-time estimate</th>
              <th>12-month estimate</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {p.content.cost_comparison.map((c) => (
              <tr key={c.alternative}>
                <td>{c.alternative}</td>
                <td>{money(c.recurring_micro)}</td>
                <td>{money(c.one_time_micro)}</td>
                <td>{money(c.twelve_month_micro)}</td>
                <td>{c.lines.length} rate inputs · incomplete</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="two-columns proposal-details">
        <div>
          <h3>Deliverables & milestones</h3>
          <ol>
            {p.content.milestones.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ol>
          <h3>Proposed team</h3>
          <div className="badge-row">
            {p.content.proposed_team.map((t) => (
              <Badge key={t}>{t}</Badge>
            ))}
          </div>
        </div>
        <div>
          <h3>Risks & mitigations</h3>
          <ul>
            {p.content.risks_and_mitigations.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
          <h3>Open questions</h3>
          <ul>
            {p.content.open_questions.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      </div>
      {p.status === "awaiting_approval" && latest ? (
        <div className="approval-bar">
          <div>
            <ShieldCheck size={22} />
            <div>
              <strong>
                You authorize this exact version and selected architecture.
              </strong>
              <small>
                Project planning begins after approval. Repository changes and
                external actions have separate controls.
              </small>
            </div>
          </div>
          <Button
            disabled={busy}
            onClick={() =>
              run(async () => {
                const project = await api<Project>(
                  `/proposals/${p.id}/approve`,
                  {
                    version: p.version,
                    content_hash: p.content_hash,
                    selection,
                  },
                );
                navigate(`projects:${project.id}`);
              }, "Proposal approved. Project created with assigned, dependent tasks.")
            }
          >
            Approve selected solution <Check size={16} />
          </Button>
        </div>
      ) : null}
      {p.status === "awaiting_approval" && latest && (
        <details className="decision-details">
          <summary>Request changes or reject</summary>
          <label>
            Reason
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
            />
          </label>
          <div className="button-row">
            <Button
              secondary
              disabled={!reason || busy}
              onClick={() =>
                run(() =>
                  api(`/proposals/${p.id}/decision`, {
                    version: p.version,
                    action: "request_changes",
                    reason,
                  }),
                )
              }
            >
              Request changes
            </Button>
            <Button
              secondary
              disabled={!reason || busy}
              onClick={() =>
                run(() =>
                  api(`/proposals/${p.id}/decision`, {
                    version: p.version,
                    action: "reject",
                    reason,
                  }),
                )
              }
            >
              Reject proposal
            </Button>
          </div>
        </details>
      )}
      <details>
        <summary>Inspect full proposal record</summary>
        <Pretty value={p} />
      </details>
    </Panel>
  );
}

export function ArchitectureEvidence({ proposal: p }: { proposal: Proposal }) {
  return (
    <>
      {p.content.architecture_manifest && (
        <section aria-label="Saved architecture evidence">
          <h3>
            Architecture design · requirements v
            {p.content.architecture_manifest.requirement_version}
          </h3>
          <Badge>{p.content.architecture_manifest.basis}</Badge>
          <p>
            Approval binds the selected option and these saved design documents
            to this exact requirements version. Implementation, benchmarks and
            cloud prices remain unverified.
          </p>
          {p.content.architecture_manifest.design.limitations?.map((text) => (
            <p key={text}>{text}</p>
          ))}
          {p.content.architecture_manifest.design.single_option_reason && (
            <p>{p.content.architecture_manifest.design.single_option_reason}</p>
          )}
          {p.content.architecture_manifest.design.options?.map((option) => (
            <details key={option.name}>
              <summary>{option.name} · design and trade-offs</summary>
              {Object.entries(option)
                .filter(([key]) => key !== "name")
                .map(([key, value]) => (
                  <div key={key}>
                    <h4>{key.replaceAll("_", " ")}</h4>
                    {Array.isArray(value) ? (
                      <ul>
                        {value.map((text, index) => (
                          <li key={index}>{text}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="preserve-lines">{value}</p>
                    )}
                  </div>
                ))}
            </details>
          ))}
          <details>
            <summary>Saved document identities and hashes</summary>
            <Pretty value={p.content.architecture_manifest.documents} />
          </details>
        </section>
      )}
    </>
  );
}
