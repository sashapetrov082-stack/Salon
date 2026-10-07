// Тонкая типизированная обёртка над window.Telegram.WebApp.
import { useEffect, useRef } from "react";

type ThemeParams = Partial<
  Record<
    | "bg_color"
    | "text_color"
    | "hint_color"
    | "link_color"
    | "button_color"
    | "button_text_color"
    | "secondary_bg_color"
    | "header_bg_color"
    | "accent_text_color"
    | "section_bg_color"
    | "section_header_text_color"
    | "subtitle_text_color"
    | "destructive_text_color",
    string
  >
>;

interface BottomButton {
  text: string;
  isVisible: boolean;
  isActive: boolean;
  setText(text: string): BottomButton;
  onClick(cb: () => void): BottomButton;
  offClick(cb: () => void): BottomButton;
  show(): BottomButton;
  hide(): BottomButton;
  enable(): BottomButton;
  disable(): BottomButton;
  showProgress(leaveActive?: boolean): BottomButton;
  hideProgress(): BottomButton;
}

interface TgWebApp {
  initData: string;
  initDataUnsafe: {
    user?: { id: number; first_name?: string; last_name?: string; username?: string };
    start_param?: string;
  };
  version: string;
  platform: string;
  colorScheme: "light" | "dark";
  themeParams: ThemeParams;
  MainButton: BottomButton;
  BackButton: {
    isVisible: boolean;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
    show(): void;
    hide(): void;
  };
  HapticFeedback: {
    impactOccurred(style: "light" | "medium" | "heavy" | "rigid" | "soft"): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
    selectionChanged(): void;
  };
  ready(): void;
  expand(): void;
  close(): void;
  isVersionAtLeast(v: string): boolean;
  onEvent(event: string, cb: (...args: unknown[]) => void): void;
  offEvent(event: string, cb: (...args: unknown[]) => void): void;
  requestContact?(cb?: (shared: boolean) => void): void;
  openLink(url: string): void;
  openTelegramLink(url: string): void;
  showConfirm?(message: string, cb: (ok: boolean) => void): void;
  showAlert?(message: string, cb?: () => void): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TgWebApp };
  }
}

const rawWebApp: TgWebApp | undefined = window.Telegram?.WebApp;
/** WebApp есть всегда после загрузки скрипта, но внутри Telegram — только если есть initData. */
export const tg: TgWebApp | undefined = rawWebApp?.initData ? rawWebApp : undefined;

const supports = (v: string) => !!tg && tg.isVersionAtLeast?.(v);

export function getInitData(): string {
  return tg?.initData || import.meta.env.VITE_DEV_INIT_DATA || "";
}

export function getStartParam(): string | null {
  const fromTg = tg?.initDataUnsafe?.start_param;
  if (fromTg) return fromTg;
  const q = new URLSearchParams(window.location.search);
  return q.get("startapp") || q.get("tgWebAppStartParam");
}

export function telegramUserName(): string {
  const u = tg?.initDataUnsafe?.user;
  if (!u) return "";
  return [u.first_name, u.last_name].filter(Boolean).join(" ").trim();
}

const THEME_VARS: Record<string, keyof ThemeParams> = {
  "--bg": "bg_color",
  "--text": "text_color",
  "--hint": "hint_color",
  "--link": "link_color",
  "--button": "button_color",
  "--button-text": "button_text_color",
  "--bg2": "secondary_bg_color",
  "--section": "section_bg_color",
  "--accent": "accent_text_color",
  "--section-header": "section_header_text_color",
  "--subtitle": "subtitle_text_color",
  "--destructive": "destructive_text_color",
};

export function applyTheme(): void {
  const root = document.documentElement;
  const params = rawWebApp?.themeParams ?? {};
  for (const [cssVar, key] of Object.entries(THEME_VARS)) {
    const value = params[key];
    if (value) root.style.setProperty(cssVar, value);
    else root.style.removeProperty(cssVar);
  }
  if (rawWebApp?.themeParams?.bg_color) root.dataset.scheme = rawWebApp.colorScheme;
  else delete root.dataset.scheme;
}

export function initTelegram(): void {
  applyTheme();
  rawWebApp?.onEvent?.("themeChanged", applyTheme);
  if (!tg) return;
  tg.ready();
  tg.expand();
}

export const haptic = {
  select() {
    if (supports("6.1")) tg?.HapticFeedback.selectionChanged();
  },
  success() {
    if (supports("6.1")) tg?.HapticFeedback.notificationOccurred("success");
  },
  error() {
    if (supports("6.1")) tg?.HapticFeedback.notificationOccurred("error");
  },
};

export function confirmDialog(message: string): Promise<boolean> {
  if (tg?.showConfirm && supports("6.2")) {
    return new Promise((resolve) => tg!.showConfirm!(message, resolve));
  }
  return Promise.resolve(window.confirm(message));
}

export function alertDialog(message: string): Promise<void> {
  if (tg?.showAlert && supports("6.2")) {
    return new Promise((resolve) => tg!.showAlert!(message, () => resolve()));
  }
  window.alert(message);
  return Promise.resolve();
}

/** Запрашивает номер телефона. true — пользователь согласился поделиться. */
export function requestContact(): Promise<boolean> {
  if (!tg?.requestContact || !supports("6.9")) return Promise.resolve(false);
  return new Promise((resolve) => tg!.requestContact!((shared) => resolve(!!shared)));
}

export function openLink(url: string): void {
  if (tg) tg.openLink(url);
  else window.open(url, "_blank", "noopener");
}

export function openTelegramLink(url: string): void {
  if (tg && supports("6.1")) tg.openTelegramLink(url);
  else window.open(url, "_blank", "noopener");
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}

interface MainButtonOptions {
  text: string;
  onClick: () => void;
  visible?: boolean;
  disabled?: boolean;
  progress?: boolean;
}

/**
 * MainButton Telegram для основного действия экрана.
 * Вне Telegram рисуем обычную кнопку внизу (см. <FallbackMainButton/>).
 */
export function useMainButton({
  text,
  onClick,
  visible = true,
  disabled = false,
  progress = false,
}: MainButtonOptions): void {
  const handler = useRef(onClick);
  handler.current = onClick;

  useEffect(() => {
    const cb = () => handler.current();
    if (tg) {
      tg.MainButton.onClick(cb);
      return () => {
        tg.MainButton.offClick(cb);
        tg.MainButton.hideProgress();
        tg.MainButton.hide();
      };
    }
    fallbackListeners.add(cb);
    return () => {
      fallbackListeners.delete(cb);
      setFallback(null);
    };
  }, []);

  useEffect(() => {
    if (tg) {
      const mb = tg.MainButton;
      mb.setText(text);
      if (disabled) mb.disable();
      else mb.enable();
      if (progress) mb.showProgress(false);
      else mb.hideProgress();
      if (visible) mb.show();
      else mb.hide();
    } else {
      setFallback(visible ? { text, disabled: disabled || progress } : null);
    }
  }, [text, visible, disabled, progress]);
}

// Состояние кнопки для режима разработки в обычном браузере.
type FallbackState = { text: string; disabled: boolean } | null;
const fallbackListeners = new Set<() => void>();
const fallbackSubscribers = new Set<(s: FallbackState) => void>();
let fallbackState: FallbackState = null;
function setFallback(s: FallbackState) {
  fallbackState = s;
  fallbackSubscribers.forEach((fn) => fn(s));
}
export const fallbackMainButton = {
  get: () => fallbackState,
  subscribe(fn: (s: FallbackState) => void) {
    fallbackSubscribers.add(fn);
    return () => fallbackSubscribers.delete(fn);
  },
  click() {
    fallbackListeners.forEach((fn) => fn());
  },
};

/** BackButton Telegram. Вне Telegram — ничего (есть системная навигация браузера). */
export function useBackButton(onBack: (() => void) | null): void {
  const handler = useRef(onBack);
  handler.current = onBack;
  const enabled = onBack !== null;
  useEffect(() => {
    if (!tg || !enabled) return;
    const cb = () => handler.current?.();
    tg.BackButton.onClick(cb);
    tg.BackButton.show();
    return () => {
      tg.BackButton.offClick(cb);
      tg.BackButton.hide();
    };
  }, [enabled]);
}

export const isTelegram = !!tg;
