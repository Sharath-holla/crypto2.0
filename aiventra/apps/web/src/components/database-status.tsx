"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Badge, Button, Panel, useApp } from "./common";

type StorageFacts = {
  backend: string;
  connected: boolean;
  schema_revision: string | null;
  expected_revision: string;
  schema_current: boolean;
  pgvector_version: string | null;
  vector_index_available: boolean;
  embedding_provider: string;
  embedding_model: string;
};

export function DatabaseStatus() {
  const { state, busy, run } = useApp();
  const [facts, setFacts] = useState<StorageFacts | null>(null);
  return (
    <Panel
      title="Database & semantic memory"
      subtitle="The database used by the running API"
      action={
        <Button
          secondary
          disabled={busy}
          onClick={() =>
            run(async () => {
              setFacts(await api<StorageFacts>("/operations/database"));
            })
          }
        >
          Check database
        </Button>
      }
    >
      <div className="inline">
        <Badge>{state.runtime.database}</Badge>
        {facts && (
          <Badge mode={facts.schema_current ? "ready" : "blocked"}>
            {facts.schema_current ? "Schema current" : "Migration required"}
          </Badge>
        )}
      </div>
      {facts ? (
        <dl className="storage-facts">
          <dt>Schema revision</dt>
          <dd>{facts.schema_revision || "Not recorded"}</dd>
          <dt>pgvector</dt>
          <dd>
            {facts.pgvector_version
              ? `Version ${facts.pgvector_version}`
              : "Unavailable in this database"}
          </dd>
          <dt>Vector index</dt>
          <dd>
            {facts.vector_index_available
              ? "HNSW available"
              : "Unavailable in this database"}
          </dd>
          <dt>Configured embeddings</dt>
          <dd>
            {facts.embedding_provider} · {facts.embedding_model}
          </dd>
        </dl>
      ) : (
        <p>
          Check the connected schema and vector extension. No AI calls are made.
        </p>
      )}
      <p>
        {state.runtime.database === "sqlite"
          ? "Existing records remain in SQLite. PostgreSQL transfer and cutover require a verified backup and an explicitly configured destination."
          : "PostgreSQL is active. A connection check alone does not verify backups or restart recovery."}
      </p>
    </Panel>
  );
}
