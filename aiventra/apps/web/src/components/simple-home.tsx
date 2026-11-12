"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BusinessRecord } from "@/lib/types";
import { ArrowUp, FolderOpen, Plus, ShieldCheck } from "lucide-react";
import { Badge, Button, Panel, useApp } from "./common";
import { AiReadiness } from "./ai-readiness";

export function SimpleHome() {
  const { state, navigate } = useApp();
  const [brief, setBrief] = useState("");
  const [drafts, setDrafts] = useState<BusinessRecord[]>([]);
  const [draftError, setDraftError] = useState("");
  useEffect(() => {
    let disposed = false;
    api<BusinessRecord[]>("/project-drafts")
      .then((rows) => {
        if (!disposed) setDrafts(rows.slice(0, 5));
      })
      .catch((exc: Error) => {
        if (!disposed) setDraftError(exc.message);
      });
    return () => {
      disposed = true;
    };
  }, [state.records.length]);
  const waiting = state.workflows.filter((row) =>
    ["waiting_for_free_provider", "failed", "blocked"].includes(row.status),
  );
  const pending = state.proposals.filter(
    (row) => row.status === "awaiting_approval",
  );
  return (
    <div className="simple-home">
      <section className="home-intro">
        <span className="eyebrow">YOUR IDEAS. A CLEAR PATH TO DELIVERY.</span>
        <h1>What would you like to build?</h1>
        <p>
          Describe your project. Choose your Lead AI. Review the plan before
          work begins.
        </p>
        <form
          className="home-composer"
          onSubmit={(event) => {
            event.preventDefault();
            sessionStorage.setItem("aiventra-project-brief", brief);
            navigate("new-project");
          }}
        >
          <textarea
            aria-label="Describe your project"
            placeholder="I want to build a customer portal for my business…"
            value={brief}
            onChange={(event) => setBrief(event.target.value)}
            maxLength={30000}
          />
          <div>
            <span>Saved drafts · Zero-cost model policy · Owner approvals</span>
            <button className="button" type="submit" aria-label="Start project">
              <ArrowUp size={18} />
            </button>
          </div>
        </form>
        <div className="home-shortcuts">
          <Button secondary onClick={() => navigate("new-project")}>
            <Plus size={16} /> Upload requirements
          </Button>
          <Button secondary onClick={() => navigate("chat")}>
            Talk to your AI CEO
          </Button>
        </div>
      </section>
      <AiReadiness />
      <div className="home-grid">
        <Panel
          title="Pick up where you left off"
          subtitle="Your saved requirements and approved projects"
        >
          {draftError && (
            <p role="alert">Could not load drafts: {draftError}</p>
          )}
          {!drafts.length && !state.projects.length && (
            <p className="muted">
              Your first project starts with a description above.
            </p>
          )}
          {drafts.map((row) => (
            <button
              className="home-record"
              key={row.id}
              onClick={() => navigate(`new-project:${row.id}`)}
            >
              <FolderOpen size={18} />
              <span>
                <strong>{row.title}</strong>
                <small>Requirements draft · version {row.version}</small>
              </span>
              <Badge>{row.status}</Badge>
            </button>
          ))}
          {state.projects
            .slice(-3)
            .reverse()
            .map((project) => (
              <button
                className="home-record"
                key={project.id}
                onClick={() => navigate(`projects:${project.id}`)}
              >
                <FolderOpen size={18} />
                <span>
                  <strong>{project.name}</strong>
                  <small>Approved project</small>
                </span>
                <Badge>{project.status}</Badge>
              </button>
            ))}
        </Panel>
        <Panel
          title="Needs your attention"
          subtitle="Decisions and real workflow status"
        >
          <button className="home-record" onClick={() => navigate("proposals")}>
            <ShieldCheck size={18} />
            <span>
              <strong>{pending.length} proposal approvals</strong>
              <small>Review the exact scope before authorizing work</small>
            </span>
          </button>
          <p>{waiting.length} workflows waiting or needing attention.</p>
          <Button secondary onClick={() => navigate("activity")}>
            View activity
          </Button>
          <p className="muted">
            Live AI runs require an installed, verified local model. No models
            are installed by this interface.
          </p>
        </Panel>
      </div>
    </div>
  );
}
