"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  Bell,
  BookOpen,
  BriefcaseBusiness,
  CircleHelp,
  Command,
  Cpu,
  Files,
  GitBranch,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Moon,
  Sun,
  Network,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Square,
  Users,
  Wallet,
} from "lucide-react";
import { api } from "@/lib/api";
import type { State, User } from "@/lib/types";
import { AppContext, Badge, Button, Loading } from "@/components/common";
import { Overview } from "@/components/overview";
import { Workforce } from "@/components/workforce";
import { Consulting } from "@/components/consulting";
import { Projects } from "@/components/projects";
import { Governance } from "@/components/governance";
import { Registry } from "@/components/registry";
import { Business } from "@/components/business";
import { MemoryBrowser } from "@/components/memory-browser";
import { Staffing } from "@/components/staffing";
import { Communications } from "@/components/communications";
import { CEOChat, ConversationHistory } from "@/components/conversations";
import { SimpleHome } from "@/components/simple-home";
import { ProjectWizard } from "@/components/project-wizard";
import { CryptoProject, CryptoProjectLink } from "@/components/crypto-project";
import {
  ClientDeliveries,
  RedeemInvitation,
} from "@/components/client-deliveries";

const groups = [
  {
    label: "WORKSPACE",
    items: [
      ["overview", "Company overview", LayoutDashboard],
      ["chat", "Executive chat", MessageSquare],
      ["conversations", "Conversations", MessageSquare],
      ["requirements", "Client requirements", Files],
      ["proposals", "Proposals & approvals", ShieldCheck],
      ["projects", "Project portfolio", BriefcaseBusiness],
    ],
  },
  {
    label: "YOUR AI COMPANY",
    items: [
      ["workforce", "AI workforce", Users],
      ["allocation", "Workforce allocation", Network],
      ["organization", "Organization", Network],
      ["meetings", "Meetings & messages", MessageSquare],
      ["activity", "Live activity", Activity],
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      ["engineering", "Engineering & QA", GitBranch],
      ["finance", "Finance & budgets", Wallet],
      ["models", "Models & providers", Cpu],
      ["crm", "Sales & clients", BriefcaseBusiness],
      ["knowledge", "Knowledge & support", BookOpen],
      ["memory", "Semantic memory", BookOpen],
      ["security", "Security & audit", ShieldCheck],
      ["settings", "System settings", Settings2],
      ["commands", "Company commands", Command],
    ],
  },
] as const;
const titles: Record<string, [string, string]> = {
  crypto: [
    "Crypto 2.0",
    "Protected scientific research, supervised by Aiventra OS.",
  ],
  home: ["Home", "Your next idea starts here."],
  "new-project": [
    "New project",
    "Describe it. Choose your AI. Review the plan.",
  ],
  allocation: [
    "Workforce allocation",
    "Shape the team. Approve the work. Follow the evidence.",
  ],
  memory: [
    "Company memory",
    "Retrieve the evidence behind your company's decisions.",
  ],
  conversations: [
    "Conversations",
    "Return to the context behind every decision.",
  ],
  commands: ["Company commands", "Direct, authenticated company operations."],
  overview: ["Company overview", "The big picture, down to every decision."],
  chat: [
    "Executive chat",
    "Give direction. Inspect the actions behind the answer.",
  ],
  requirements: [
    "Client requirements",
    "Good solutions begin with the right questions.",
  ],
  proposals: [
    "Proposals & approvals",
    "Compare the options. Authorize the exact scope.",
  ],
  projects: [
    "Project portfolio",
    "Every deliverable, dependency and decision in one place.",
  ],
  workforce: [
    "AI workforce",
    "A whole company of specialists. One accountable owner.",
  ],
  organization: [
    "Organization",
    "Clear responsibilities and independent oversight.",
  ],
  meetings: ["Meetings & messages", "Bounded discussions. Recorded decisions."],
  activity: [
    "Live activity",
    "See which agent and model handled every request.",
  ],
  engineering: [
    "Engineering & QA",
    "Isolated changes, independent review, real execution evidence.",
  ],
  finance: [
    "Finance & budgets",
    "Recorded usage, deterministic estimates, enforced limits.",
  ],
  models: [
    "Models & providers",
    "Choose capability and quality with cost in view.",
  ],
  crm: [
    "Sales & clients",
    "A persistent pipeline for opportunities and relationships.",
  ],
  knowledge: [
    "Knowledge & support",
    "Keep project facts and support requests connected.",
  ],
  security: [
    "Security & audit",
    "Server controls and a verifiable activity history.",
  ],
  settings: ["System settings", "Configure the boundaries of autonomous work."],
};

function Logo() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <Square size={15} fill="currentColor" />
        <Square size={15} fill="currentColor" />
        <Square size={15} fill="currentColor" />
        <Square size={15} fill="currentColor" />
      </span>
      <span>
        Aiventra<span className="brand-os">OS</span>
      </span>
    </div>
  );
}
export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [state, setState] = useState<State | null>(null);
  const [view, setView] = useState("home");
  const [setupId, setSetupId] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [conversationId, setConversationId] = useState("");
  const [draft, setDraft] = useState(0);
  const [projectId, setProjectId] = useState("");
  const [requirementId, setRequirementId] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [light, setLight] = useState(false);
  const searchInput = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [email, setEmail] = useState("owner@local.test");
  const [password, setPassword] = useState("");
  const refresh = useCallback(async () => {
    const result = await api<State>("/state");
    setState(result);
  }, []);
  const navigate = useCallback((target: string) => {
    const [nextView, recordId] = target.split(":");
    if (!titles[nextView]) return;
    setView(nextView);
    if (nextView === "chat") {
      setConversationId(recordId || "");
      if (!recordId) setDraft((current) => current + 1);
    }
    if (nextView === "projects") setProjectId(recordId || "");
    if (nextView === "new-project") setSetupId(recordId || "");
    if (
      ![
        "home",
        "new-project",
        "projects",
        "activity",
        "proposals",
        "settings",
      ].includes(nextView)
    )
      setAdvanced(true);
    if (["proposals", "requirements"].includes(nextView))
      setRequirementId(recordId || "");
    setMobileMenu(false);
    setSearch("");
    const query = new URLSearchParams({ view: nextView });
    if (recordId)
      query.set(
        nextView === "new-project"
          ? "draft"
          : nextView === "chat"
            ? "conversation"
            : nextView === "projects"
              ? "project"
              : "requirement",
        recordId,
      );
    window.history.pushState({}, "", `/?${query}`);
  }, []);
  const run = useCallback(
    async (
      operation: () => Promise<unknown>,
      message = "Saved to your company records.",
    ) => {
      setBusy(true);
      setError("");
      try {
        await operation();
        await refresh();
        setNotice(message);
        setTimeout(() => setNotice(""), 4500);
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Operation failed");
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );
  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("view");
    if (initial && titles[initial]) setView(initial);
    setSetupId(new URLSearchParams(window.location.search).get("draft") || "");
    setAdvanced(
      localStorage.getItem("aiventra-advanced") === "open" ||
        (!!initial &&
          ![
            "home",
            "new-project",
            "projects",
            "activity",
            "proposals",
            "settings",
          ].includes(initial)),
    );
    setConversationId(
      new URLSearchParams(window.location.search).get("conversation") || "",
    );
    setProjectId(
      new URLSearchParams(window.location.search).get("project") || "",
    );
    setRequirementId(
      new URLSearchParams(window.location.search).get("requirement") || "",
    );
    const savedTheme = localStorage.getItem("aiventra-theme") === "light";
    setLight(savedTheme);
    document.documentElement.dataset.theme = savedTheme ? "light" : "dark";
    setSidebarCollapsed(
      localStorage.getItem("aiventra-sidebar") === "collapsed",
    );
    api<User>("/auth/me")
      .then((result) => {
        setUser(result);
        return result.role === "owner" ? refresh() : undefined;
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [refresh]);
  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "k") {
        event.preventDefault();
        searchInput.current?.focus();
      }
      if (event.key === "Escape") setMobileMenu(false);
    };
    const history = () => {
      const query = new URLSearchParams(window.location.search);
      const target = query.get("view") || "home";
      if (titles[target]) setView(target);
      setConversationId(query.get("conversation") || "");
      setProjectId(query.get("project") || "");
      setRequirementId(query.get("requirement") || "");
      setSetupId(query.get("draft") || "");
      if (
        ![
          "home",
          "new-project",
          "projects",
          "activity",
          "proposals",
          "settings",
        ].includes(target)
      )
        setAdvanced(true);
    };
    window.addEventListener("keydown", keys);
    window.addEventListener("popstate", history);
    return () => {
      window.removeEventListener("keydown", keys);
      window.removeEventListener("popstate", history);
    };
  }, []);
  useEffect(() => {
    if (!user || user.role !== "owner") return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        await refresh();
      } catch (exc) {
        if (!disposed)
          setError(exc instanceof Error ? exc.message : "Refresh failed");
      } finally {
        if (!disposed) timer = setTimeout(poll, 5000);
      }
    };
    timer = setTimeout(poll, 5000);
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [user, refresh]);
  const login = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ user: User }>("/auth/login", {
        email,
        password,
      });
      setUser(result.user);
      setPassword("");
      if (result.user.role === "owner") await refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };
  const logout = async () => {
    setBusy(true);
    setError("");
    try {
      await api("/auth/logout", {});
      setUser(null);
      setState(null);
      setNotice("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Sign-out failed");
    } finally {
      setBusy(false);
    }
  };
  if (loading) return <Loading />;
  if (!user)
    return (
      <main className="login-page">
        <div className="login-art">
          <Logo />
          <div>
            <div className="eyebrow">
              THE OPERATING SYSTEM FOR YOUR AI COMPANY
            </div>
            <h1>
              Big ambitions.
              <br />
              An entire company
              <br />
              behind you.
            </h1>
            <p>
              Give your specialists direction. Keep every decision, deliverable
              and dollar in view.
            </p>
            <div className="login-grid">
              {[
                "Product",
                "Engineering",
                "Finance",
                "Quality",
                "Security",
                "Operations",
              ].map((name, i) => (
                <div key={name}>
                  <span>0{i + 1}</span>
                  {name}
                  <ArrowRight size={16} />
                </div>
              ))}
            </div>
          </div>
          <small>Useful autonomy. Clear human control.</small>
        </div>
        <section className="login-form">
          <div className="login-card">
            <span className="eyebrow">WELCOME TO COMPANY OS</span>
            <h2>Your command center.</h2>
            <p>Sign in to supervise your AI workforce.</p>
            {error && (
              <div className="alert error" role="alert">
                {error}
              </div>
            )}
            <form onSubmit={login}>
              <label>
                Email
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="username"
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
              </label>
              <Button type="submit" disabled={busy}>
                Sign in <ArrowRight size={16} />
              </Button>
            </form>
            <RedeemInvitation onUser={setUser} />
            <div className="login-hint">
              <ShieldCheck size={18} />
              <p>
                Your local credentials are in the private <code>.env</code> file
                created by bootstrap.
              </p>
            </div>
          </div>
        </section>
      </main>
    );
  if (user.role !== "owner") return <ClientPortal user={user} />;
  if (!state) return <Loading />;
  const pending = state.proposals.filter(
    (p) => p.status === "awaiting_approval",
  ).length;
  const alerts = state.notifications.filter((n) => !n.acknowledged).length;
  const searchResults = search
    ? [
        ...state.agents
          .filter((a) => a.name.toLowerCase().includes(search.toLowerCase()))
          .slice(0, 4)
          .map((a) => ({
            id: a.id,
            title: a.name,
            view: "workforce",
            type: "Agent",
          })),
        ...state.projects
          .filter((p) => p.name.toLowerCase().includes(search.toLowerCase()))
          .slice(0, 4)
          .map((p) => ({
            id: p.id,
            title: p.name,
            view: `projects:${p.id}`,
            type: "Project",
          })),
        ...state.requirements
          .filter((r) => r.title.toLowerCase().includes(search.toLowerCase()))
          .slice(0, 4)
          .map((r) => ({
            id: r.id,
            title: r.title,
            view: `requirements:${r.id}`,
            type: "Requirement",
          })),
      ]
    : [];
  return (
    <AppContext.Provider value={{ state, refresh, run, navigate, busy }}>
      <div
        className={`shell ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${mobileMenu ? "menu-open" : ""} ${view === "chat" ? "chat-shell" : ""}`}
      >
        {mobileMenu && (
          <button
            className="nav-backdrop"
            aria-label="Close navigation"
            onClick={() => setMobileMenu(false)}
          />
        )}
        <aside className="sidebar" aria-label="Workspace sidebar">
          <div className="brand-row">
            <Logo />
            <button
              className="icon-button collapse-sidebar"
              aria-label={
                sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"
              }
              onClick={() => {
                setSidebarCollapsed(!sidebarCollapsed);
                localStorage.setItem(
                  "aiventra-sidebar",
                  sidebarCollapsed ? "expanded" : "collapsed",
                );
              }}
            >
              {sidebarCollapsed ? (
                <PanelLeftOpen size={17} />
              ) : (
                <PanelLeftClose size={17} />
              )}
            </button>
          </div>
          <button
            className="new-chat-button"
            onClick={() => navigate("chat")}
            aria-label="New chat"
          >
            <Plus size={18} />
            <span>New chat</span>
            <kbd>+</kbd>
          </button>
          <div className="workspace-switch">
            <span className="company-avatar">
              {state.organization.name[0]?.toUpperCase()}
            </span>
            <div>
              <strong>{state.organization.name}</strong>
              <small>Owner workspace</small>
            </div>
          </div>
          <nav aria-label="Main navigation">
            <div className="nav-group primary-navigation">
              {[
                ["home", "Home", LayoutDashboard],
                ["new-project", "New project", Plus],
                ["projects", "My projects", BriefcaseBusiness],
                ["crypto", "Crypto 2.0", Activity],
                ["activity", "Activity", Activity],
                ["proposals", "Approvals", ShieldCheck],
                ["settings", "Settings", Settings2],
              ].map(([key, label, Icon]) => {
                const NavigationIcon = Icon as typeof LayoutDashboard;
                return (
                  <button
                    key={String(key)}
                    className={`nav-item ${view === key ? "selected" : ""}`}
                    aria-label={String(label)}
                    aria-current={view === key ? "page" : undefined}
                    title={String(label)}
                    onClick={() => navigate(String(key))}
                  >
                    <NavigationIcon size={17} />
                    <span>{String(label)}</span>
                  </button>
                );
              })}
            </div>
            <button
              className="nav-item advanced-toggle"
              aria-label="Advanced"
              aria-expanded={advanced}
              onClick={() => {
                setAdvanced(!advanced);
                localStorage.setItem(
                  "aiventra-advanced",
                  advanced ? "closed" : "open",
                );
              }}
            >
              <Settings2 size={17} />
              <span>Advanced</span>
              <span aria-hidden="true">{advanced ? "−" : "+"}</span>
            </button>
            {advanced && (
              <>
                <div className="recent-conversations">
                  <span className="nav-label">RECENT CONVERSATIONS</span>
                  {state.conversations
                    .slice()
                    .sort((a, b) => b.updated_at - a.updated_at)
                    .slice(0, 4)
                    .map((conversation) => (
                      <button
                        className={`conversation-link ${conversationId === conversation.id && view === "chat" ? "selected" : ""}`}
                        key={conversation.id}
                        title={conversation.title}
                        onClick={() => navigate(`chat:${conversation.id}`)}
                      >
                        <MessageSquare size={14} />
                        <span>{conversation.title}</span>
                      </button>
                    ))}
                  {!state.conversations.length && (
                    <small>Your conversations will appear here.</small>
                  )}
                </div>
                {groups.map((group) => (
                  <div className="nav-group" key={group.label}>
                    <span className="nav-label">{group.label}</span>
                    {group.items.map(([key, label, Icon]) => (
                      <button
                        key={key}
                        aria-label={label}
                        className={`nav-item ${view === key ? "selected" : ""}`}
                        aria-current={view === key ? "page" : undefined}
                        title={label}
                        onClick={() => navigate(key)}
                      >
                        <Icon size={17} />
                        <span>{label}</span>
                        {key === "proposals" && pending > 0 && (
                          <span className="nav-count">{pending}</span>
                        )}
                      </button>
                    ))}
                  </div>
                ))}
              </>
            )}
          </nav>
          <div className="sidebar-bottom">
            <div className="connection">
              <span
                className={`dot ${state.organization.paused || state.runtime.worker.status !== "ready" ? "amber" : ""}`}
              />
              {state.organization.paused
                ? "Company paused"
                : state.runtime.worker.status === "ready"
                  ? "Worker ready"
                  : "Worker unavailable"}
              <Badge>{state.runtime.database}</Badge>
            </div>
            <button
              className="user-button"
              onClick={logout}
              disabled={busy}
              aria-label="Sign out"
            >
              <span className="owner-avatar">
                {user.email[0]?.toUpperCase()}
              </span>
              <div>
                <strong>Company owner</strong>
                <small>{user.email}</small>
              </div>
              <LogOut size={15} />
            </button>
          </div>
        </aside>
        <div className="main-wrap">
          <header className="topbar">
            <button
              className="icon-button mobile-menu-button"
              aria-label="Open navigation"
              aria-expanded={mobileMenu}
              onClick={() => {
                setSidebarCollapsed(false);
                setMobileMenu(!mobileMenu);
              }}
            >
              <Menu size={20} />
            </button>
            <div className="breadcrumb">
              Workspace <span>/</span> <strong>{titles[view][0]}</strong>
            </div>
            <div className="topbar-right">
              <Badge>ZERO-COST AI MODE</Badge>
              <div className="global-search">
                <Search size={15} />
                <input
                  aria-label="Search company"
                  ref={searchInput}
                  placeholder="Search your company…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <kbd>Ctrl K</kbd>
                {search && (
                  <div className="search-results">
                    {searchResults.length ? (
                      searchResults.map((r) => (
                        <button key={r.id} onClick={() => navigate(r.view)}>
                          <small>{r.type}</small>
                          {r.title}
                          <ArrowRight size={14} />
                        </button>
                      ))
                    ) : (
                      <p>No matching records</p>
                    )}
                  </div>
                )}
              </div>
              <button
                className="icon-button"
                aria-label={light ? "Use dark theme" : "Use light theme"}
                onClick={() => {
                  setLight(!light);
                  document.documentElement.dataset.theme = light
                    ? "dark"
                    : "light";
                  localStorage.setItem(
                    "aiventra-theme",
                    light ? "dark" : "light",
                  );
                }}
              >
                {light ? <Moon size={18} /> : <Sun size={18} />}
              </button>
              <button
                className="icon-button"
                aria-label="Monitoring alerts"
                onClick={() => navigate("security")}
              >
                <Bell size={18} />
                {alerts > 0 && <i />}
              </button>
              <span className="owner-avatar small">
                {user.email[0]?.toUpperCase()}
              </span>
            </div>
          </header>
          <main className="content">
            {!["chat", "home"].includes(view) && (
              <div className="page-heading">
                <div>
                  <div className="eyebrow">OWNER COMMAND CENTER</div>
                  <h1>{titles[view][0]}</h1>
                  <p>{titles[view][1]}</p>
                </div>
                <div className="heading-actions">
                  <Badge
                    mode={state.organization.paused ? "blocked" : "active"}
                  >
                    <span className="dot" />
                    {state.organization.paused
                      ? "Work paused"
                      : state.runtime.worker.status === "ready"
                        ? "Worker ready"
                        : "Worker unavailable"}
                  </Badge>
                  <Button onClick={() => navigate("new-project")}>
                    <Plus size={16} />
                    New project
                  </Button>
                </div>
              </div>
            )}
            {error && (
              <div className="alert error" role="alert">
                {error}
                <button aria-label="Dismiss error" onClick={() => setError("")}>
                  ×
                </button>
              </div>
            )}
            {notice && (
              <div className="alert success" role="status">
                {notice}
              </div>
            )}
            {view === "overview" && <Overview />}
            {view === "home" && <SimpleHome />}
            {view === "crypto" && <CryptoProject />}
            {view === "projects" && <CryptoProjectLink />}
            {view === "new-project" && (
              <ProjectWizard key={setupId} initialId={setupId} />
            )}
            {["workforce", "organization"].includes(view) && (
              <Workforce hierarchy={view === "organization"} />
            )}
            {["requirements", "proposals"].includes(view) && (
              <Consulting
                key={`${view}:${requirementId}`}
                approvals={view === "proposals"}
                initialId={requirementId}
              />
            )}
            {["projects", "engineering"].includes(view) && (
              <Projects
                key={`${view}:${projectId}`}
                engineering={view === "engineering"}
                initialId={projectId}
              />
            )}
            {["finance", "security", "settings", "activity"].includes(view) && (
              <Governance view={view} />
            )}
            {view === "models" && <Registry />}
            {["crm", "knowledge"].includes(view) && <Business view={view} />}
            {view === "memory" && <MemoryBrowser />}
            {view === "allocation" && <Staffing />}
            {["commands", "meetings"].includes(view) && (
              <Communications chat={view === "commands"} />
            )}
            {view === "chat" && (
              <CEOChat
                key={`${conversationId}:${draft}`}
                conversationId={conversationId}
                onCreated={(id) => {
                  setConversationId(id);
                  window.history.replaceState(
                    {},
                    "",
                    `/?view=chat&conversation=${id}`,
                  );
                }}
              />
            )}
            {view === "conversations" && <ConversationHistory />}
            {view !== "chat" && (
              <footer className="page-footer">
                <span>
                  AI Company OS <span className="muted">/</span> Human
                  direction. Accountable execution.
                </span>
                <button onClick={() => navigate("settings")}>
                  <CircleHelp size={14} />
                  Runtime & limitations
                </button>
              </footer>
            )}
          </main>
        </div>
      </div>
    </AppContext.Provider>
  );
}

function ClientPortal({ user }: { user: User }) {
  const [requirements, setRequirements] = useState<
    import("@/lib/types").Requirement[]
  >([]);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    api<import("@/lib/types").Requirement[]>("/requirements")
      .then(setRequirements)
      .catch((exc) => setError(exc.message));
  }, []);
  return (
    <main className="client-portal">
      <Logo />
      <h1>Client workspace</h1>
      <p>{user.email}</p>
      <Button
        secondary
        onClick={async () => {
          try {
            await api("/auth/logout", {});
            window.location.reload();
          } catch (cause) {
            setError(String(cause));
          }
        }}
      >
        Sign out of client workspace
      </Button>
      <ClientDeliveries />
      {error && <div className="alert error">{error}</div>}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api("/requirements", {
              client_id: user.client_id,
              title,
              text,
              mode: "live",
            });
            setRequirements(await api("/requirements"));
            setText("");
          } catch (exc) {
            setError(String(exc));
          }
        }}
      >
        <label>
          Title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            minLength={3}
          />
        </label>
        <label>
          Requirement
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            required
            minLength={20}
          />
        </label>
        <Button type="submit">Submit for consultation</Button>
      </form>
      {requirements.map((r) => (
        <div className="panel" key={r.id}>
          <h2>{r.title}</h2>
          <Badge>{r.status}</Badge>
          <p>{r.text}</p>
        </div>
      ))}
    </main>
  );
}
