"use client";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BriefcaseBusiness,
  CircleCheck,
  Clock3,
  Cpu,
  Files,
  ShieldCheck,
  Users,
  Wallet,
} from "lucide-react";
import { api, date, money } from "@/lib/api";
import { Badge, Button, Empty, Panel, useApp, ViewLink } from "./common";

export function Overview() {
  const { state, navigate, run, busy } = useApp();
  const active = state.projects.filter((p) => p.status === "active");
  const pending = state.proposals.filter(
    (p) => p.status === "awaiting_approval",
  );
  const running = state.workflows.filter(
    (w) => w.status === "running" || w.status === "queued",
  );
  const totalCost = state.runs.reduce((sum, row) => sum + row.cost_micro, 0);
  const recent = state.audit.slice(0, 6);
  const days = Array.from({ length: 7 }, (_, i) => {
    const day = new Date();
    day.setDate(day.getDate() - (6 - i));
    const runs = state.runs.filter(
      (r) =>
        new Date(r.created_at * 1000).toDateString() === day.toDateString(),
    );
    return {
      label: day.toLocaleDateString("en", { weekday: "short" }),
      cost: runs.reduce((sum, r) => sum + r.cost_micro, 0),
    };
  });
  const maxCost = Math.max(...days.map((d) => d.cost), 1);
  return (
    <>
      <div className="hero">
        <div>
          <div className="hero-label">
            <span className="dot" />
            YOUR COMPANY, AT A GLANCE
          </div>
          <h2>Big ideas. Coordinated execution.</h2>
          <p>
            Define the work. Bring a requirement, review the options,
            <br className="desktop" /> and give the company a clear direction.
          </p>
          <Button onClick={() => navigate("chat")}>
            Talk to your CEO <ArrowRight size={16} />
          </Button>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit orbit-three" />
          <div className="hub">
            <CommandLogo />
          </div>
          <div className="orbit-node n1">
            <Cpu size={20} />
          </div>
          <div className="orbit-node n2">
            <ShieldCheck size={20} />
          </div>
          <div className="orbit-node n3">
            <Users size={20} />
          </div>
          <div className="orbit-node n4">
            <BriefcaseBusiness size={20} />
          </div>
          <span className="visual-caption">
            16 departments. One shared mission.
          </span>
        </div>
      </div>
      <div className="stats-grid">
        {[
          {
            label: "Registered AI employees",
            value: state.agents.length,
            note: `${state.departments.length} departments`,
            icon: Users,
            view: "workforce",
          },
          {
            label: "Active projects",
            value: active.length,
            note: `${state.tasks.filter((t) => t.status === "completed").length} tasks completed`,
            icon: BriefcaseBusiness,
            view: "projects",
          },
          {
            label: "Awaiting your decision",
            value: pending.length,
            note: pending.length
              ? "Proposal approval required"
              : "Your approval queue is clear",
            icon: Clock3,
            view: "proposals",
          },
          {
            label: "Recorded AI cost",
            value: money(totalCost),
            note: "Computed estimate · mock = $0",
            icon: Wallet,
            view: "finance",
          },
        ].map((stat) => (
          <button
            key={stat.label}
            className="stat-card"
            onClick={() => navigate(stat.view)}
          >
            <div className="stat-label">
              {stat.label}
              <stat.icon size={17} />
            </div>
            <strong>{stat.value}</strong>
            <div className="stat-note">
              {stat.note}
              <ArrowUpRight size={14} />
            </div>
          </button>
        ))}
      </div>
      <div className="dashboard-columns">
        <Panel
          title="Project portfolio"
          subtitle="Progress from verified underlying task records"
          action={<ViewLink view="projects">View portfolio</ViewLink>}
        >
          {state.projects.length ? (
            <div className="project-list">
              {state.projects.slice(0, 4).map((p) => {
                const tasks = state.tasks.filter((t) => t.project_id === p.id);
                const complete = tasks.filter(
                  (t) => t.status === "completed",
                ).length;
                return (
                  <button
                    className="project-row"
                    key={p.id}
                    onClick={() => navigate("projects")}
                  >
                    <span className="project-icon">
                      <BriefcaseBusiness size={19} />
                    </span>
                    <div>
                      <strong>{p.name}</strong>
                      <small>{p.selected_alternative}</small>
                      <div className="progress">
                        <span
                          style={{
                            width: `${tasks.length ? (complete / tasks.length) * 100 : 0}%`,
                          }}
                        />
                      </div>
                    </div>
                    <span className="project-meta">
                      <Badge>{p.status}</Badge>
                      <small>
                        {complete}/{tasks.length} tasks
                      </small>
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <Empty
              title="Your next project starts here"
              text="Submit a requirement. Approve a proposal to create a project with assigned specialists."
              action={
                <Button secondary onClick={() => navigate("requirements")}>
                  Create a requirement <ArrowRight size={14} />
                </Button>
              }
            />
          )}
        </Panel>
        <Panel
          title="Needs your attention"
          subtitle="Decisions that keep work moving"
          action={
            <Badge>
              {pending.length +
                state.notifications.filter((n) => !n.acknowledged).length}
            </Badge>
          }
        >
          {pending.slice(0, 3).map((p) => (
            <button
              className="attention-row"
              key={p.id}
              onClick={() => navigate("proposals")}
            >
              <span className="attention-icon">
                <Files size={17} />
              </span>
              <div>
                <strong>
                  {
                    state.requirements.find((r) => r.id === p.requirement_id)
                      ?.title
                  }
                </strong>
                <small>
                  Proposal v{p.version} ·{" "}
                  {p.content.mode === "mock"
                    ? "Fixture analysis"
                    : "Live analysis"}
                </small>
              </div>
              <ArrowRight size={15} />
            </button>
          ))}
          {state.notifications
            .filter((n) => !n.acknowledged)
            .slice(0, 2)
            .map((n) => (
              <button
                key={n.id}
                className="attention-row"
                onClick={() => navigate("security")}
              >
                <ShieldCheck size={17} />
                <div>
                  <strong>{n.title}</strong>
                  <small>{n.severity}</small>
                </div>
                <ArrowRight size={15} />
              </button>
            ))}
          {!pending.length &&
            !state.notifications.some((n) => !n.acknowledged) && (
              <Empty
                title="No pending decisions"
                text="Approval requests and monitoring alerts appear here."
              />
            )}
          <div className="control-note">
            <ShieldCheck size={17} />
            <span>
              Production deployments are{" "}
              {state.organization.deployments_paused
                ? "paused"
                : "approval controlled"}
              .
            </span>
          </div>
        </Panel>
      </div>
      <div className="dashboard-columns">
        <Panel
          title="Company activity"
          subtitle="An auditable history of real operations"
          action={<ViewLink view="activity">All activity</ViewLink>}
        >
          <div className="activity-list">
            {recent.map((event) => (
              <div className="activity-row" key={event.id}>
                <span className="activity-symbol">
                  <Activity size={15} />
                </span>
                <div>
                  <strong>
                    {event.action.replaceAll(".", " · ").replaceAll("_", " ")}
                  </strong>
                  <small>
                    {state.agents.find((a) => a.id === event.actor)?.name ||
                      (event.actor.length === 36
                        ? "Company owner"
                        : event.actor)}{" "}
                    · {date(event.created_at)}
                  </small>
                </div>
                <CircleCheck size={15} className="green" />
              </div>
            ))}
          </div>
        </Panel>
        <Panel
          title="AI spending"
          subtitle="Last seven days · computed provider usage estimates"
          action={<ViewLink view="finance">Finance</ViewLink>}
        >
          <div className="cost-total">
            <strong>{money(totalCost)}</strong>
            <span>recorded total</span>
          </div>
          <div className="bar-chart">
            {days.map((d, i) => (
              <div key={i} className="bar-column">
                <span className="bar-value">{money(d.cost)}</span>
                <div className="bar-track">
                  <div style={{ height: `${(d.cost / maxCost) * 100}%` }} />
                </div>
                <small>{d.label}</small>
              </div>
            ))}
          </div>
          <div className="chart-note">
            Mock runs incur no provider charge. Invoice reconciliation is
            separate.
          </div>
        </Panel>
      </div>
      <div className="system-strip">
        <span>
          <span className="dot" />
          {running.length} queued or running workflows
        </span>
        <span>
          <Users size={15} />
          {state.agents.filter((a) => a.enabled).length} enabled employees
        </span>
        <span>
          <ShieldCheck size={15} />
          Owner approval enforced
        </span>
        <Button
          secondary
          disabled={busy}
          onClick={() =>
            run(() =>
              api("/controls", {
                action: state.organization.paused
                  ? "resume_company"
                  : "pause_company",
              }),
            )
          }
        >
          {state.organization.paused ? "Resume company" : "Pause company"}
        </Button>
      </div>
    </>
  );
}
function CommandLogo() {
  return (
    <div className="command-logo">
      <i />
      <i />
      <i />
      <i />
    </div>
  );
}
