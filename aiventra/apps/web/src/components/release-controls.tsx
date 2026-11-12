"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, date } from "@/lib/api";
import { Button, useApp } from "./common";
import type { DeliveryPackage } from "./package-controls";

type Readiness = {
  ready: boolean;
  blockers: string[];
  approval: { id: string; expires_at: number } | null;
};
export function ReleaseControls({
  item,
  reload,
}: {
  item: DeliveryPackage;
  reload: () => Promise<void>;
}) {
  const { run, busy } = useApp();
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const pending = useRef<{ key: string; id: string } | null>(null);
  const refresh = useCallback(async () => {
    setReadiness(
      await api<Readiness>(`/delivery-packages/${item.id}/release-readiness`),
    );
    setError("");
  }, [item.id]);
  useEffect(() => {
    refresh().catch((cause) => setError(String(cause)));
  }, [refresh, item.status]);
  const action = (
    kind: "approve" | "reject" | "request_changes" | "release" | "withdraw",
  ) => {
    if (reason.length < 10) {
      setError("Enter a reason of at least 10 characters.");
      return;
    }
    if (
      !window.confirm(
        `${kind.replaceAll("_", " ")} exact delivery version ${item.version}? Manifest ${item.manifest_hash}`,
      )
    )
      return;
    const key = `${kind}:${item.id}:${item.manifest_hash}:${reason}`;
    if (pending.current?.key !== key)
      pending.current = { key, id: crypto.randomUUID() };
    const payload = {
      request_id: pending.current.id,
      version: item.version,
      manifest_hash: item.manifest_hash,
    };
    run(
      async () => {
        const endpoint = ["release", "withdraw"].includes(kind)
          ? kind
          : "release-decision";
        await api(`/delivery-packages/${item.id}/${endpoint}`, {
          ...payload,
          ...(kind === "release"
            ? { approval_id: readiness?.approval?.id }
            : kind === "withdraw"
              ? { reason }
              : { decision: kind, reason }),
        });
        pending.current = null;
        await reload();
        await refresh();
      },
      kind === "release"
        ? "Exact package released to its granted recipients. Awaiting client acceptance."
        : "Owner delivery decision saved.",
    );
  };
  return (
    <details>
      <summary>Owner release authority · separate from final review</summary>
      {error && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      {readiness?.blockers.map((row) => (
        <p className="alert warning" key={row}>
          {row}
        </p>
      ))}
      {readiness?.approval && (
        <p>
          Exact approval {readiness.approval.id} · expires{" "}
          {date(readiness.approval.expires_at)}
        </p>
      )}
      <label>
        Owner decision reason
        <textarea
          minLength={10}
          maxLength={2000}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      <div className="button-row">
        <Button secondary disabled={busy} onClick={() => run(refresh)}>
          Check release readiness
        </Button>
        {[
          "package_ready",
          "package_blocked",
          "awaiting_release_approval",
        ].includes(item.status) && (
          <>
            <Button
              disabled={busy || !readiness?.ready}
              onClick={() => action("approve")}
            >
              Approve exact release
            </Button>
            <Button
              secondary
              disabled={busy}
              onClick={() => action("request_changes")}
            >
              Request package changes
            </Button>
            <Button secondary disabled={busy} onClick={() => action("reject")}>
              Reject package release
            </Button>
          </>
        )}
        {item.status === "awaiting_release_approval" && (
          <Button
            disabled={busy || !readiness?.ready || !readiness.approval}
            onClick={() => action("release")}
          >
            Release approved package
          </Button>
        )}
        {[
          "released",
          "superseded",
          "package_ready",
          "awaiting_release_approval",
        ].includes(item.status) && (
          <Button secondary disabled={busy} onClick={() => action("withdraw")}>
            Withdraw package access
          </Button>
        )}
      </div>
    </details>
  );
}
