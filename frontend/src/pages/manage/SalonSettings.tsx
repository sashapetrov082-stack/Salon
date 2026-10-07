import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api/client";
import type { Photo, SalonSettings } from "../../api/types";
import { ImageUpload, useUpload } from "../../components/ImageUpload";
import { Field, Section, toast } from "../../components/ui";
import { useBack } from "../../lib/hooks";
import { alertDialog, copyText, haptic, openTelegramLink, useMainButton } from "../../telegram/webapp";
import { useManage } from "./context";

const TIMEZONES = [
  "Europe/Kaliningrad",
  "Europe/Moscow",
  "Europe/Samara",
  "Asia/Yekaterinburg",
  "Asia/Omsk",
  "Asia/Novosibirsk",
  "Asia/Krasnoyarsk",
  "Asia/Irkutsk",
  "Asia/Yakutsk",
  "Asia/Vladivostok",
  "Asia/Magadan",
  "Asia/Kamchatka",
];

type Form = Pick<
  SalonSettings,
  | "name"
  | "description"
  | "address"
  | "map_url"
  | "phone"
  | "cover_url"
  | "logo_url"
  | "announcement"
  | "timezone"
  | "slot_step_min"
  | "min_lead_time_min"
  | "booking_horizon_days"
  | "cancel_deadline_hours"
>;

function pick(s: SalonSettings): Form {
  return {
    name: s.name,
    description: s.description,
    address: s.address,
    map_url: s.map_url,
    phone: s.phone,
    cover_url: s.cover_url,
    logo_url: s.logo_url,
    announcement: s.announcement,
    timezone: s.timezone,
    slot_step_min: s.slot_step_min,
    min_lead_time_min: s.min_lead_time_min,
    booking_horizon_days: s.booking_horizon_days,
    cancel_deadline_hours: s.cancel_deadline_hours,
  };
}

export function SalonSettingsPage() {
  const { salonId, salon, base } = useManage();
  const queryClient = useQueryClient();
  useBack(`${base}/more`);
  const [form, setForm] = useState<Form>(pick(salon));
  useEffect(() => setForm(pick(salon)), [salon]);
  const dirty = JSON.stringify(form) !== JSON.stringify(pick(salon));
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...form, [k]: v });
  const text = (k: keyof Form) => ({
    value: (form[k] as string | null) ?? "",
    onChange: (e: { target: { value: string } }) => set(k, (e.target.value || null) as never),
  });
  const int = (k: keyof Form) => ({
    value: form[k] as number,
    onChange: (e: { target: { value: string } }) => set(k, Math.max(0, Math.floor(Number(e.target.value)) || 0) as never),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["manage", salonId, "settings"] });
    queryClient.invalidateQueries({ queryKey: ["salon", salon.slug] });
  };
  const onError = (e: unknown) => {
    haptic.error();
    alertDialog(e instanceof ApiError ? e.message : "Не удалось сохранить");
  };

  const save = useMutation({
    mutationFn: () => api.patch<SalonSettings>(`/manage/${salonId}/settings`, form),
    onSuccess: (data) => {
      haptic.success();
      toast("Сохранено");
      queryClient.setQueryData(["manage", salonId, "settings"], data);
      refresh();
    },
    onError,
  });

  const fileInput = useRef<HTMLInputElement>(null);
  const { upload, busy } = useUpload(salonId);
  const addPhoto = useMutation({
    mutationFn: (url: string) =>
      api.post<Photo>(`/manage/${salonId}/photos`, { url, sort_order: salon.photos.length }),
    onSuccess: refresh,
    onError,
  });
  const removePhoto = useMutation({
    mutationFn: (id: number) => api.delete(`/manage/${salonId}/photos/${id}`),
    onSuccess: refresh,
    onError,
  });

  useMainButton({
    text: "Сохранить",
    visible: dirty,
    progress: save.isPending,
    disabled: save.isPending,
    onClick: () => {
      if (!form.name.trim()) return void alertDialog("Укажите название салона");
      if (form.map_url && !/^https?:\/\//.test(form.map_url)) {
        return void alertDialog("Ссылка на карту должна начинаться с https://");
      }
      save.mutate();
    },
  });

  return (
    <div className="page">
      <div className="page-title">Салон</div>

      <Section title="Ссылка для записи">
        <div className="section-pad">
          <div className="input-boxed" style={{ wordBreak: "break-all", fontSize: 13, marginBottom: 10 }}>
            {salon.booking_link}
          </div>
          <div className="btn-row">
            <button
              className="btn secondary"
              onClick={async () =>
                toast((await copyText(salon.booking_link)) ? "Ссылка скопирована" : "Не удалось скопировать")
              }
            >
              Копировать
            </button>
            <button
              className="btn secondary"
              onClick={() =>
                openTelegramLink(
                  `https://t.me/share/url?url=${encodeURIComponent(salon.booking_link)}&text=${encodeURIComponent(`Онлайн-запись в «${salon.name}»`)}`,
                )
              }
            >
              Поделиться
            </button>
          </div>
        </div>
      </Section>

      <Section title="Витрина">
        <Field label="Название">
          <input className="input" maxLength={120} {...text("name")} />
        </Field>
        <Field label="Описание">
          <textarea className="input" rows={3} maxLength={2000} {...text("description")} />
        </Field>
        <Field label="Объявление (плашка на витрине)">
          <input className="input" maxLength={500} placeholder="Например: 1 ноября не работаем" {...text("announcement")} />
        </Field>
        <Field label="Адрес">
          <input className="input" maxLength={300} {...text("address")} />
        </Field>
        <Field label="Ссылка на Яндекс Карты">
          <input className="input" type="url" placeholder="https://yandex.ru/maps/-/..." {...text("map_url")} />
        </Field>
        <Field label="Телефон для кнопки «Позвонить»">
          <input className="input" type="tel" maxLength={32} placeholder="+7 495 000-00-00" {...text("phone")} />
        </Field>
        <ImageUpload salonId={salonId} label="Логотип" round value={form.logo_url} onChange={(u) => set("logo_url", u)} />
        <ImageUpload salonId={salonId} label="Обложка" value={form.cover_url} onChange={(u) => set("cover_url", u)} />
      </Section>

      <Section title="Галерея">
        <div className="section-pad">
          <div className="thumbs">
            {salon.photos.map((p) => (
              <div key={p.id} className="thumb">
                <img src={p.url} alt="" />
                <button aria-label="Удалить" onClick={() => removePhoto.mutate(p.id)}>
                  ✕
                </button>
              </div>
            ))}
          </div>
          <button
            className="btn secondary block"
            style={{ marginTop: 10 }}
            disabled={busy || addPhoto.isPending}
            onClick={() => fileInput.current?.click()}
          >
            {busy ? "Загрузка…" : "Добавить фото"}
          </button>
          <input
            ref={fileInput}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            hidden
            onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              const url = await upload(file);
              if (url) addPhoto.mutate(url);
            }}
          />
        </div>
      </Section>

      <Section title="Параметры записи">
        <Field label="Шаг сетки слотов, мин">
          <select className="input" value={form.slot_step_min} onChange={(e) => set("slot_step_min", Number(e.target.value))}>
            {[5, 10, 15, 20, 30, 60].map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Минимум минут до начала записи">
          <input className="input" type="number" inputMode="numeric" min={0} {...int("min_lead_time_min")} />
        </Field>
        <Field label="Запись открыта на дней вперёд">
          <input className="input" type="number" inputMode="numeric" min={1} max={365} {...int("booking_horizon_days")} />
        </Field>
        <Field label="Отмена и перенос клиентом — не позже чем за, ч">
          <input className="input" type="number" inputMode="numeric" min={0} {...int("cancel_deadline_hours")} />
        </Field>
        <Field label="Часовой пояс">
          <select className="input" value={form.timezone} onChange={(e) => set("timezone", e.target.value)}>
            {(TIMEZONES.includes(form.timezone) ? TIMEZONES : [form.timezone, ...TIMEZONES]).map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </Field>
      </Section>
    </div>
  );
}
