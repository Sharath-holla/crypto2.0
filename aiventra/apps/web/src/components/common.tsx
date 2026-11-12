"use client";
import { createContext, useContext } from "react";
import { ArrowUpRight, CircleDashed, LoaderCircle } from "lucide-react";
import type { State } from "@/lib/types";
export const AppContext = createContext<{
  state: State;
  refresh: () => Promise<void>;
  run: (operation: () => Promise<unknown>, message?: string) => Promise<void>;
  navigate: (view: string) => void;
  busy: boolean;
} | null>(null);
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("App context missing");
  return value;
}
export function Badge({
  children,
  mode,
}: {
  children: React.ReactNode;
  mode?: string;
}) {
  return (
    <span className={`badge ${mode || String(children).replaceAll(" ", "_")}`}>
      {children}
    </span>
  );
}
export function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <CircleDashed size={32} />
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
export function Panel({
  title,
  subtitle,
  children,
  action,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Pretty({ value }: { value: unknown }) {
  return (
    <pre className="code">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}
export function Button({
  children,
  onClick,
  secondary = false,
  disabled = false,
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  secondary?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      className={secondary ? "button secondary" : "button"}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
export function ViewLink({
  view,
  children,
}: {
  view: string;
  children: React.ReactNode;
}) {
  const { navigate } = useApp();
  return (
    <button className="text-button" onClick={() => navigate(view)}>
      {children}
      <ArrowUpRight size={14} />
    </button>
  );
}
export function Loading() {
  return (
    <div className="empty">
      <LoaderCircle className="spin" size={28} />
      <p>Connecting to your company…</p>
    </div>
  );
}
