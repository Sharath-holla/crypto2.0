"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, date } from "@/lib/api";
import { Badge, Button, useApp } from "./common";

export type ClientAccess = {
  invitations: {
    id: string;
    email: string;
    expires_at: number;
    redeemed_at: number | null;
    revoked_at: number | null;
    can_respond: boolean;
  }[];
  grants: {
    id: string;
    user_id: string;
    email: string;
    enabled: boolean;
    can_respond: boolean;
    revoked_at: number | null;
  }[];
};

export function ClientAccessControls({
  projectId,
  onAccess,
}: {
  projectId: string;
  onAccess: (value: ClientAccess) => void;
}) {
  const { run, busy } = useApp();
  const [access, setAccess] = useState<ClientAccess>({
    invitations: [],
    grants: [],
  });
  const [email, setEmail] = useState("");
  const [respond, setRespond] = useState(true);
  const [secret, setSecret] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const pending = useRef<{ key: string; id: string } | null>(null);
  const reload = useCallback(async () => {
    const value = await api<ClientAccess>(
      `/projects/${projectId}/client-access`,
    );
    setAccess(value);
    onAccess(value);
    setError("");
  }, [projectId, onAccess]);
  useEffect(() => {
    reload().catch((cause) => setError(String(cause)));
  }, [reload]);
  return (
    <details className="delivery-package">
      <summary>Client invitations and project access</summary>
      <p className="muted">
        Invite a specific client email. The private token appears once; share it
        directly. No email is sent.
      </p>
      {error && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const key = JSON.stringify({ email, respond });
          if (pending.current?.key !== key)
            pending.current = { key, id: crypto.randomUUID() };
          const requestId = pending.current.id;
          run(async () => {
            const value = await api<{ token: string | null; message: string }>(
              `/projects/${projectId}/client-invitations`,
              { request_id: requestId, email, can_respond: respond },
            );
            setSecret(value.token || "");
            setMessage(value.message);
            pending.current = null;
            await reload();
          }, "Invitation saved. Share the token privately with its intended recipient.");
        }}
      >
        <label>
          Client email
          <input
            required
            type="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setSecret("");
            }}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={respond}
            onChange={(event) => setRespond(event.target.checked)}
          />
          Can formally accept or request changes
        </label>
        <Button type="submit" disabled={busy}>
          Create client invitation
        </Button>
      </form>
      {message && <p role="status">{message}</p>}
      {secret && (
        <label>
          Private invitation token · shown once
          <input
            type="password"
            readOnly
            value={secret}
            autoComplete="off"
            onFocus={(event) => event.target.select()}
          />
          <Button secondary onClick={() => setSecret("")}>
            Hide invitation token
          </Button>
        </label>
      )}
      <Button secondary disabled={busy} onClick={() => run(reload)}>
        Refresh client access
      </Button>
      {access.invitations.map((item) => (
        <div className="delivery-document" key={item.id}>
          <p>
            {item.email} ·{" "}
            <Badge>
              {item.revoked_at
                ? "revoked"
                : item.redeemed_at
                  ? "redeemed"
                  : "pending"}
            </Badge>{" "}
            · expires {date(item.expires_at)} ·{" "}
            {item.can_respond ? "Response permission" : "Read only"}
          </p>
          {!item.revoked_at && (
            <Button
              secondary
              disabled={busy}
              onClick={() => {
                const reason = window.prompt(
                  `Reason to revoke ${item.email}'s invitation and its current grant (at least 10 characters)`,
                );
                if (!reason || reason.length < 10) return;
                const key = `revoke:${item.id}:${reason}`;
                if (pending.current?.key !== key)
                  pending.current = { key, id: crypto.randomUUID() };
                const requestId = pending.current.id;
                run(async () => {
                  await api(`/client-invitations/${item.id}/revoke`, {
                    request_id: requestId,
                    reason,
                  });
                  pending.current = null;
                  setSecret("");
                  await reload();
                }, "Client access revoked.");
              }}
            >
              Revoke invitation and access
            </Button>
          )}
        </div>
      ))}
    </details>
  );
}
