"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, date } from "@/lib/api";
import { Badge, Button, Empty, Panel, Pretty, useApp } from "./common";
import {
  ClientAccessControls,
  type ClientAccess,
} from "./client-access-controls";
import { ReleaseControls } from "./release-controls";

type DeliveryFile = {
  id: string;
  name: string;
  purpose: string;
  sha256: string;
  bytes: number;
  client_visible: boolean;
};
export type DeliveryPackage = {
  id: string;
  project_id: string;
  version: number;
  status: string;
  classification: string;
  manifest_hash: string;
  finalized_at: number | null;
  supersedes_id: string | null;
  workflow: { id: string; status: string; step: number; last_error: string };
  integrity_valid: boolean;
  integrity_error: string;
  manifest: {
    files?: DeliveryFile[];
    blockers?: string[];
    summary?: string;
    release_notes?: string;
    test_summary?: string;
    limitations?: string[];
    known_issues?: string[];
    source_hash?: string;
  };
};
const purposes = [
  "architecture_decisions",
  "high_level_design",
  "low_level_design",
  "database",
  "api",
  "deployment_instructions",
];

export function PackageControls({ projectId }: { projectId: string }) {
  const { state, run, busy } = useApp();
  const [items, setItems] = useState<DeliveryPackage[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reviewId, setReviewId] = useState("");
  const [summary, setSummary] = useState("");
  const [notes, setNotes] = useState("");
  const [tests, setTests] = useState("");
  const [limitations, setLimitations] = useState("");
  const [documents, setDocuments] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [access, setAccess] = useState<ClientAccess>({
    invitations: [],
    grants: [],
  });
  const [recipients, setRecipients] = useState<string[]>([]);
  const [patches, setPatches] = useState(false);
  const [deadline, setDeadline] = useState("");
  const request = useRef<{ hash: string; id: string } | null>(null);
  const reviews = state.records.filter(
    (row) =>
      row.project_id === projectId &&
      row.kind === "delivery_review" &&
      ["fixture_reviewed", "awaiting_delivery_approval"].includes(row.status),
  );
  const review = reviews.find((row) => row.id === reviewId);
  const artifacts = state.artifacts.filter(
    (row) => row.project_id === projectId && row.kind === "document",
  );
  const reload = useCallback(async () => {
    const value = await api<DeliveryPackage[]>(
      `/projects/${projectId}/delivery-packages`,
    );
    setItems(value);
    setError("");
    setLoading(false);
  }, [projectId]);
  useEffect(() => {
    let active = true;
    api<DeliveryPackage[]>(`/projects/${projectId}/delivery-packages`)
      .then((value) => {
        if (active) {
          setItems(value);
          setError("");
        }
      })
      .catch((cause) => {
        if (active) setError(String(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, state.organization.version]);
  return (
    <Panel
      title="Immutable delivery packages"
      subtitle="Prepare a frozen version. Inspect the evidence before release."
    >
      {loading && <p role="status">Loading saved delivery packages…</p>}
      {error && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      <p className="muted">
        Required documents must come from the reviewed source. Missing documents
        block the package. Fixture packages remain nonproduction and cannot be
        released.
      </p>
      <ClientAccessControls projectId={projectId} onAccess={setAccess} />
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!review) return;
          const payload = {
            review_id: review.id,
            source_hash: String(review.data.source_hash),
            summary,
            release_notes: notes,
            test_summary: tests,
            limitations: limitations.split("\n").filter(Boolean),
            recipient_ids: recipients,
            include_source_patches: patches,
            acceptance_deadline: deadline
              ? Math.floor(new Date(deadline).getTime() / 1000)
              : null,
            documents: purposes
              .filter((purpose) => documents[purpose])
              .map((purpose) => ({
                purpose,
                artifact_id: documents[purpose],
                client_visible: !!visible[purpose],
              })),
          };
          const hash = JSON.stringify(payload);
          if (request.current?.hash !== hash)
            request.current = { hash, id: crypto.randomUUID() };
          const requestId = request.current.id;
          run(async () => {
            await api(`/projects/${projectId}/delivery-packages`, {
              ...payload,
              request_id: requestId,
            });
            request.current = null;
            await reload();
          }, "Package preparation saved. Follow its worker checkpoints below.");
        }}
      >
        <label>
          Completed final review
          <select
            required
            value={reviewId}
            onChange={(event) => setReviewId(event.target.value)}
          >
            <option value="">Choose reviewed evidence</option>
            {reviews.map((row) => (
              <option key={row.id} value={row.id}>
                {row.status} · {row.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          Client delivery summary
          <textarea
            required
            minLength={20}
            maxLength={2000}
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
          />
        </label>
        <label>
          Release notes
          <textarea
            required
            minLength={20}
            maxLength={4000}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>
        <label>
          Owner-provided test summary
          <textarea
            required
            minLength={20}
            maxLength={2000}
            value={tests}
            onChange={(event) => setTests(event.target.value)}
          />
        </label>
        <label>
          Known limitations · one per line
          <textarea
            maxLength={4000}
            value={limitations}
            onChange={(event) => setLimitations(event.target.value)}
          />
        </label>
        <details>
          <summary>Map reviewed documents and client visibility</summary>
          {purposes.map((purpose) => (
            <div key={purpose} className="delivery-document">
              <label>
                {purpose.replaceAll("_", " ")}
                <select
                  aria-label={`Document for ${purpose}`}
                  value={documents[purpose] || ""}
                  onChange={(event) =>
                    setDocuments({
                      ...documents,
                      [purpose]: event.target.value,
                    })
                  }
                >
                  <option value="">Missing · package will be blocked</option>
                  {artifacts.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name} · {row.sha256.slice(0, 12)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={!!visible[purpose]}
                  onChange={(event) =>
                    setVisible({ ...visible, [purpose]: event.target.checked })
                  }
                />
                Approved for client disclosure
              </label>
            </div>
          ))}
        </details>
        <fieldset>
          <legend>Exact intended recipients</legend>
          {!access.grants.some(
            (grant) => grant.enabled && !grant.revoked_at,
          ) && (
            <p className="muted">
              Invite a client and have them redeem their token before selecting
              recipients.
            </p>
          )}
          {access.grants
            .filter((grant) => grant.enabled && !grant.revoked_at)
            .map((grant) => (
              <label className="check" key={grant.id}>
                <input
                  type="checkbox"
                  checked={recipients.includes(grant.user_id)}
                  onChange={(event) =>
                    setRecipients(
                      event.target.checked
                        ? [...recipients, grant.user_id]
                        : recipients.filter((id) => id !== grant.user_id),
                    )
                  }
                />
                {grant.email} ·{" "}
                {grant.can_respond ? "Can respond" : "Read only"}
              </label>
            ))}
          <label>
            Acceptance deadline (optional, local time)
            <input
              type="datetime-local"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
            />
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={patches}
              onChange={(event) => setPatches(event.target.checked)}
            />
            Approve verified source patches for client disclosure
          </label>
        </fieldset>
        <div className="button-row">
          <Button type="submit" disabled={busy || !review}>
            Prepare immutable package
          </Button>
          <Button secondary disabled={busy} onClick={() => run(reload)}>
            Refresh packages
          </Button>
        </div>
      </form>
      {!loading && !items.length && (
        <Empty
          title="No frozen packages"
          text="Complete final review, then prepare a delivery version."
        />
      )}
      {items.map((item) => (
        <section
          className="delivery-package"
          key={item.id}
          aria-label={`Delivery package version ${item.version}`}
        >
          <div className="panel-heading">
            <h3>Version {item.version}</h3>
            <Badge>{item.status}</Badge>
          </div>
          <p>
            <Badge>{item.classification}</Badge> ·{" "}
            {item.finalized_at
              ? date(item.finalized_at)
              : `Worker ${item.workflow.status} · ${item.workflow.step} saved checkpoints`}
          </p>
          <p className="mono delivery-hash">
            Manifest SHA-256: {item.manifest_hash || "Not frozen yet"}
          </p>
          <p role="status">
            {item.integrity_valid
              ? "All frozen files verified"
              : item.integrity_error}
          </p>
          {item.workflow.last_error && (
            <p className="alert warning">{item.workflow.last_error}</p>
          )}
          <ul aria-label="Package blockers">
            {item.manifest.blockers?.map((row) => (
              <li key={row}>{row}</li>
            ))}
          </ul>
          {item.status === "preparing" && (
            <div className="button-row">
              <Button
                secondary
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    await api(`/workflows/${item.workflow.id}/control`, {
                      action:
                        item.workflow.status === "paused" ? "resume" : "pause",
                    });
                    await reload();
                  })
                }
              >
                {item.workflow.status === "paused"
                  ? "Resume preparation"
                  : "Pause preparation"}
              </Button>
              <Button
                secondary
                disabled={busy}
                onClick={() => {
                  if (
                    window.confirm(
                      `Cancel preparation of version ${item.version}? Saved evidence is retained.`,
                    )
                  )
                    run(async () => {
                      await api(`/delivery-packages/${item.id}/cancel`, {});
                      await reload();
                    });
                }}
              >
                Cancel preparation
              </Button>
            </div>
          )}
          <details>
            <summary>Inspect frozen manifest and files</summary>
            <Pretty value={item.manifest} />
            {item.manifest.files?.map((file) => (
              <p key={file.id}>
                <a
                  href={`/api/delivery-packages/${item.id}/files/${file.id}`}
                  download
                >
                  {file.name}
                </a>{" "}
                · {file.bytes} bytes ·{" "}
                {file.client_visible ? "Client-facing" : "Internal"}
                <span className="mono delivery-hash">{file.sha256}</span>
              </p>
            ))}
          </details>
          {item.finalized_at && <ReleaseControls item={item} reload={reload} />}
        </section>
      ))}
    </Panel>
  );
}
