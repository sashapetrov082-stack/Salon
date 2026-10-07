import { type ReactNode, useEffect, useState, useSyncExternalStore } from "react";
import { errorMessage } from "../api/client";
import type { AppointmentStatus } from "../api/types";
import { STATUS_LABELS } from "../lib/format";
import { fallbackMainButton, tg } from "../telegram/webapp";

export function Spinner() {
  return <div className="spinner" aria-label="Загрузка" />;
}

export function ErrorView({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="empty">
      <div className="big">⚠️</div>
      <div>{errorMessage(error)}</div>
      {onRetry && (
        <button className="btn secondary small" style={{ marginTop: 12 }} onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  );
}

export function Empty({ icon = "🗓", children }: { icon?: string; children: ReactNode }) {
  return (
    <div className="empty">
      <div className="big">{icon}</div>
      <div>{children}</div>
    </div>
  );
}

export function Section({
  title,
  children,
  pad,
}: {
  title?: ReactNode;
  children: ReactNode;
  pad?: boolean;
}) {
  return (
    <>
      {title && <div className="section-header">{title}</div>}
      <div className={pad ? "section section-pad" : "section"}>{children}</div>
    </>
  );
}

export function Row({
  title,
  sub,
  side,
  left,
  onClick,
  chevron,
}: {
  title: ReactNode;
  sub?: ReactNode;
  side?: ReactNode;
  left?: ReactNode;
  onClick?: () => void;
  chevron?: boolean;
}) {
  const content = (
    <>
      {left}
      <div className="row-main">
        <div className="row-title">{title}</div>
        {sub && <div className="row-sub">{sub}</div>}
      </div>
      {side !== undefined && <div className="row-side">{side}</div>}
      {chevron && <span className="chevron" />}
    </>
  );
  if (!onClick) return <div className="row static">{content}</div>;
  return (
    <button type="button" className="row" onClick={onClick}>
      {content}
    </button>
  );
}

export function Avatar({ url, name, size }: { url?: string | null; name: string; size?: "lg" }) {
  const cls = size === "lg" ? "avatar lg" : "avatar";
  if (url) return <img className={cls} src={url} alt="" loading="lazy" />;
  const initials = name
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
  return <div className={cls}>{initials || "•"}</div>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

export function Check({
  label,
  checked,
  onChange,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function StatusBadge({ status }: { status: AppointmentStatus }) {
  const color =
    status === "confirmed"
      ? "green"
      : status === "completed"
        ? "gray"
        : status === "booked"
          ? ""
          : "red";
  return <span className={`badge ${color}`}>{STATUS_LABELS[status]}</span>;
}

/** Обычная кнопка внизу экрана, если приложение открыто не в Telegram (разработка). */
export function FallbackMainButton() {
  const state = useSyncExternalStore(
    (cb) => fallbackMainButton.subscribe(cb),
    () => fallbackMainButton.get(),
  );
  if (tg || !state) return null;
  return (
    <div className="fallback-main-button">
      <button
        className="btn block"
        disabled={state.disabled}
        onClick={() => fallbackMainButton.click()}
      >
        {state.text}
      </button>
    </div>
  );
}

// ---- Тосты ----
let toastSetter: ((s: string | null) => void) | null = null;

export function toast(message: string) {
  toastSetter?.(message);
}

export function ToastHost() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    toastSetter = setMsg;
    return () => {
      toastSetter = null;
    };
  }, []);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 2500);
    return () => clearTimeout(t);
  }, [msg]);
  return msg ? <div className="toast">{msg}</div> : null;
}
