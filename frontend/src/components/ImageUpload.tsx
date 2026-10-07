import { useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import { alertDialog } from "../telegram/webapp";

const MAX = 5 * 1024 * 1024;

export function useUpload(salonId: number) {
  const [busy, setBusy] = useState(false);
  const upload = async (file: File): Promise<string | null> => {
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      await alertDialog("Поддерживаются JPEG, PNG и WebP");
      return null;
    }
    if (file.size > MAX) {
      await alertDialog("Файл больше 5 МБ");
      return null;
    }
    setBusy(true);
    try {
      return (await api.upload(salonId, file)).url;
    } catch (e) {
      await alertDialog(e instanceof ApiError ? e.message : "Не удалось загрузить файл");
      return null;
    } finally {
      setBusy(false);
    }
  };
  return { upload, busy };
}

export function ImageUpload({
  salonId,
  value,
  onChange,
  label,
  round,
}: {
  salonId: number;
  value: string | null;
  onChange: (url: string | null) => void;
  label: string;
  round?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const { upload, busy } = useUpload(salonId);
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {value ? (
          <img
            src={value}
            alt=""
            style={{
              width: 64,
              height: 64,
              objectFit: "cover",
              borderRadius: round ? "50%" : 10,
            }}
          />
        ) : (
          <div className="avatar" style={{ width: 64, height: 64, borderRadius: round ? "50%" : 10 }}>
            🖼
          </div>
        )}
        <button type="button" className="btn secondary small" disabled={busy} onClick={() => input.current?.click()}>
          {busy ? "Загрузка…" : value ? "Заменить" : "Загрузить"}
        </button>
        {value && (
          <button type="button" className="link-btn" onClick={() => onChange(null)}>
            Убрать
          </button>
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          const url = await upload(file);
          if (url) onChange(url);
        }}
      />
    </div>
  );
}
