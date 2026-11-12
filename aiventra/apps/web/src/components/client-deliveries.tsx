"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, date } from "@/lib/api";
import { Badge, Button, Empty, Panel } from "./common";
import type { User } from "@/lib/types";

type Statement = {
  id: string;
  package_id: string;
  package_version: number;
  manifest_hash: string;
  kind: string;
  reason: string;
  created_at: number;
};
type Delivery = {
  repositories: {
    repository_id: string;
    source_commit: string;
    tree: string;
    pull_requests: {
      status: string;
      number: number | null;
      url: string | null;
      remote_commit: string | null;
    }[];
  }[];
  id: string;
  project_id: string;
  project_name: string;
  version: number;
  status: string;
  manifest_hash: string;
  summary: string;
  release_notes: string;
  test_summary: string;
  limitations: string[];
  known_issues: string[];
  deployment: { status: string; url: string | null };
  acceptance_deadline: number | null;
  released_at: number;
  acceptance_criteria: string[];
  responses: Statement[];
  files: { id: string; name: string; sha256: string; bytes: number }[];
};
type Case = {
  id: string;
  kind: string;
  status: string;
  package_version: number;
  reason: string;
  assigned_role: string;
  resolution: string | null;
  severity: string;
  priority: string;
  reproduction: string;
  attachments: { name: string; sha256: string; bytes: number }[];
};
type Project = { id: string; name: string; can_respond: boolean };

export function RedeemInvitation({ onUser }: { onUser: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <details>
      <summary>Redeem an owner invitation</summary>
      <p>
        Use the private token supplied by your project owner. Existing clients
        use their current password.
      </p>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            const value = await api<{ user: User }>("/auth/redeem-invitation", {
              email,
              token,
              password,
            });
            setToken("");
            setPassword("");
            onUser(value.user);
          } catch (cause) {
            setError(String(cause));
          } finally {
            setBusy(false);
          }
        }}
      >
        {error && (
          <p className="alert error" role="alert">
            {error}
          </p>
        )}
        <label>
          Invited email
          <input
            required
            type="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label>
          Private invitation token
          <input
            required
            type="password"
            autoComplete="off"
            minLength={43}
            maxLength={100}
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
        </label>
        <label>
          Client password
          <input
            required
            type="password"
            autoComplete="current-password"
            minLength={12}
            maxLength={1024}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <Button disabled={busy} type="submit">
          Redeem invitation and sign in
        </Button>
      </form>
    </details>
  );
}

function Respond({
  item,
  reload,
}: {
  item: Delivery;
  reload: () => Promise<void>;
}) {
  const [kind, setKind] = useState("accept");
  const [reason, setReason] = useState("");
  const [consent, setConsent] = useState(false);
  const [severity, setSeverity] = useState("medium");
  const [priority, setPriority] = useState("normal");
  const [attachments, setAttachments] = useState<
    { name: string; content: string }[]
  >([]);
  const [reproduction, setReproduction] = useState("");
  const [feature, setFeature] = useState("");
  const [criteria, setCriteria] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const pending = useRef<{ key: string; id: string } | null>(null);
  const decided = item.responses.some((row) =>
    ["accept", "reject", "request_changes"].includes(row.kind),
  );
  useEffect(() => {
    if (decided || item.status !== "released") setKind("report_defect");
  }, [decided, item.status]);
  return (
    <details>
      <summary>Respond to version {item.version}</summary>
      <p className="mono delivery-hash">
        Your statement binds SHA-256 {item.manifest_hash}.
      </p>
      {error && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (!consent) return;
          if (
            !window.confirm(
              `Submit ${kind.replaceAll("_", " ")} for exact version ${item.version}? Formal decisions cannot be rewritten.`,
            )
          )
            return;
          const value = {
            kind,
            reason,
            severity,
            priority,
            attachments,
            reproduction,
            feature,
            affected_criteria: criteria,
            version: item.version,
            manifest_hash: item.manifest_hash,
          };
          const key = JSON.stringify(value);
          if (pending.current?.key !== key)
            pending.current = { key, id: crypto.randomUUID() };
          setBusy(true);
          setError("");
          setNotice("");
          try {
            await api(`/client/deliveries/${item.id}/responses`, {
              ...value,
              request_id: pending.current.id,
            });
            pending.current = null;
            setConsent(false);
            setNotice("Statement saved with its exact version and timestamp.");
            await reload();
          } catch (cause) {
            setError(String(cause));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Response
          <select
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setConsent(false);
            }}
          >
            {!decided && item.status === "released" && (
              <>
                <option value="accept">Accept this delivery</option>
                <option value="request_changes">Request changes</option>
                <option value="reject">Reject delivery</option>
              </>
            )}
            <option value="report_defect">Report a defect</option>
            <option value="request_support">Request support</option>
          </select>
        </label>
        {decided && (
          <p>
            A formal decision is already saved. You can open a defect or support
            case.
          </p>
        )}
        <label>
          Reason or feedback
          <textarea
            required
            minLength={20}
            maxLength={4000}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        {kind !== "accept" && (
          <>
            <label>
              Affected feature
              <input
                maxLength={1000}
                value={feature}
                onChange={(event) => setFeature(event.target.value)}
              />
            </label>
            <label>
              Reproduction steps or supporting details
              <textarea
                maxLength={4000}
                value={reproduction}
                onChange={(event) => setReproduction(event.target.value)}
              />
            </label>
            <label>
              Severity
              <select
                value={severity}
                onChange={(event) => setSeverity(event.target.value)}
              >
                {["low", "medium", "high", "critical"].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Priority
              <select
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
              >
                {["low", "normal", "high"].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Supporting text files · up to 3 files, 20KB each
              <input
                type="file"
                accept=".txt,.md,.json"
                multiple
                onChange={async (event) => {
                  const files = Array.from(event.target.files || []);
                  if (
                    files.length > 3 ||
                    files.some((file) => file.size > 20000)
                  ) {
                    setError(
                      "Choose up to three text files of at most 20KB each.",
                    );
                    event.target.value = "";
                    setAttachments([]);
                    return;
                  }
                  try {
                    setAttachments(
                      await Promise.all(
                        files.map(async (file) => ({
                          name: file.name,
                          content: await file.text(),
                        })),
                      ),
                    );
                    setError("");
                  } catch {
                    setError("The selected text files could not be read.");
                    setAttachments([]);
                  }
                }}
              />
            </label>
            <fieldset>
              <legend>Affected acceptance criteria</legend>
              {item.acceptance_criteria.map((criterion, index) => (
                <label className="check" key={index}>
                  <input
                    type="checkbox"
                    checked={criteria.includes(index)}
                    onChange={(event) =>
                      setCriteria(
                        event.target.checked
                          ? [...criteria, index]
                          : criteria.filter((value) => value !== index),
                      )
                    }
                  />
                  {criterion}
                </label>
              ))}
            </fieldset>
          </>
        )}
        <label className="check">
          <input
            required
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
          />
          I confirm this response applies to version {item.version} and the
          manifest shown above.
        </label>
        <Button
          type="submit"
          disabled={
            busy ||
            !consent ||
            (decided && ["accept", "reject", "request_changes"].includes(kind))
          }
        >
          Submit client response
        </Button>
      </form>
    </details>
  );
}

export function ClientDeliveries() {
  const [items, setItems] = useState<Delivery[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [history, setHistory] = useState<Statement[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    const [deliveries, granted, statements, requests] = await Promise.all([
      api<Delivery[]>("/client/deliveries"),
      api<Project[]>("/client/projects"),
      api<Statement[]>("/client/history"),
      api<Case[]>("/client/cases"),
    ]);
    setItems(deliveries);
    setProjects(granted);
    setHistory(statements);
    setCases(requests);
    setError("");
    setLoading(false);
  }, []);
  useEffect(() => {
    reload().catch((cause) => {
      setError(String(cause));
      setLoading(false);
    });
  }, [reload]);
  return (
    <Panel
      title="Released deliveries"
      subtitle="Your granted projects, approved files and versioned decisions."
    >
      {error && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      {loading && <p role="status">Loading released deliveries…</p>}
      <div className="button-row">
        <label>
          Project
          <select
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            <option value="">All granted projects</option>
            {projects.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <Button
          secondary
          onClick={() => {
            setLoading(true);
            reload().catch((cause) => {
              setError(String(cause));
              setLoading(false);
            });
          }}
        >
          Refresh deliveries
        </Button>
      </div>
      {!loading && !items.length && (
        <Empty
          title="No released packages"
          text="Your owner must approve and release an exact package to your account before files appear."
        />
      )}
      {items
        .filter((item) => !selected || item.project_id === selected)
        .map((item) => (
          <section
            className="delivery-package"
            key={item.id}
            aria-label={`Released delivery version ${item.version}`}
          >
            <div className="panel-heading">
              <h3>
                {item.project_name} · Version {item.version}
              </h3>
              <Badge>{item.status}</Badge>
            </div>
            <p>{item.summary}</p>
            <p className="mono delivery-hash">
              Manifest SHA-256: {item.manifest_hash}
            </p>
            <p>
              Released {date(item.released_at)}
              {item.acceptance_deadline &&
                ` · Respond before ${date(item.acceptance_deadline)}`}
            </p>
            <h4>Release notes</h4>
            <p className="preserve-lines">{item.release_notes}</p>
            <h4>Test evidence summary</h4>
            <p>{item.test_summary}</p>
            <h4>Limitations and known issues</h4>
            <ul>
              {[...item.limitations, ...item.known_issues].map((row, index) => (
                <li key={index}>{row}</li>
              ))}
            </ul>
            <p>
              Deployment: <Badge>{item.deployment.status}</Badge>
            </p>
            <h4>Approved acceptance criteria</h4>
            <ol>
              {item.acceptance_criteria.map((row, index) => (
                <li key={index}>{row}</li>
              ))}
            </ol>
            <h4>Released files</h4>
            {item.repositories.map((repository) => (
              <details key={repository.repository_id}>
                <summary>Verified repository source</summary>
                <p className="mono delivery-hash">
                  Commit: {repository.source_commit}
                </p>
                <p className="mono delivery-hash">Tree: {repository.tree}</p>
                {repository.pull_requests.map((pull, index) => (
                  <p key={index}>
                    <Badge>{pull.status}</Badge>
                    {pull.url?.startsWith("https://") && (
                      <a href={pull.url} target="_blank" rel="noreferrer">
                        Pull request #{pull.number}
                      </a>
                    )}
                  </p>
                ))}
              </details>
            ))}
            {item.files.map((file) => (
              <p key={file.id}>
                <a
                  href={`/api/client/deliveries/${item.id}/files/${file.id}`}
                  download
                >
                  {file.name}
                </a>{" "}
                · {file.bytes} bytes
                <span className="mono delivery-hash">{file.sha256}</span>
              </p>
            ))}
            {projects.find((project) => project.id === item.project_id)
              ?.can_respond && <Respond item={item} reload={reload} />}
          </section>
        ))}
      <details>
        <summary>Client decisions and acceptance history</summary>
        {history.map((row) => (
          <article className="delivery-document" key={row.id}>
            <Badge>{row.kind}</Badge> · version {row.package_version} ·{" "}
            {date(row.created_at)}
            <p>{row.reason}</p>
            <p className="mono delivery-hash">{row.manifest_hash}</p>
          </article>
        ))}
      </details>
      <details>
        <summary>Changes, defects and support</summary>
        {cases.map((row) => (
          <article className="delivery-document" key={row.id}>
            <Badge>{row.status}</Badge> · {row.kind.replaceAll("_", " ")} ·
            version {row.package_version}
            <p>{row.reason}</p>
            <p>Assigned: {row.assigned_role}</p>
            <p>
              Severity: {row.severity} · Priority: {row.priority}
            </p>
            {row.reproduction && (
              <p className="preserve-lines">{row.reproduction}</p>
            )}
            {row.attachments?.map((file) => (
              <p key={file.sha256}>
                <a
                  href={`/api/client/cases/${row.id}/attachments/${file.sha256}`}
                  download
                >
                  {file.name}
                </a>{" "}
                · {file.bytes} bytes
              </p>
            ))}
            {row.resolution && <p>{row.resolution}</p>}
          </article>
        ))}
      </details>
    </Panel>
  );
}
