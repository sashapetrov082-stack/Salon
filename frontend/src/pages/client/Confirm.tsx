import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import type { ClientAppointment, ContactStatus } from "../../api/types";
import { ErrorView, Field, Section, Spinner } from "../../components/ui";
import { formatDateTime, isPhoneComplete, maskPhone, phoneDigits, prettyPhone } from "../../lib/format";
import { useBack } from "../../lib/hooks";
import {
  alertDialog,
  haptic,
  openLink,
  requestContact,
  telegramUserName,
  useMainButton,
} from "../../telegram/webapp";
import { BookingSummary, useBookingContext } from "./DateTime";

type PhoneMode = "auto" | "manual";

async function waitForContact(): Promise<string | null> {
  for (let i = 0; i < 15; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    try {
      const s = await api.get<ContactStatus>("/me/contact-status");
      if (s.received && s.phone) return s.phone;
    } catch {
      /* пробуем ещё */
    }
  }
  return null;
}

export function ConfirmPage() {
  const { slug = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const back = useBack(`/s/${slug}/start`);
  const ctx = useBookingContext(slug, params);
  const at = params.get("at");
  const slotStaff = Number(params.get("slot_staff")) || null;

  const contact = useQuery({
    queryKey: ["contact-status"],
    queryFn: () => api.get<ContactStatus>("/me/contact-status"),
  });

  const [name, setName] = useState("");
  const [comment, setComment] = useState("");
  const [phoneMode, setPhoneMode] = useState<PhoneMode>("auto");
  const [manualPhone, setManualPhone] = useState("+7");
  const [waiting, setWaiting] = useState(false);
  const [phoneHint, setPhoneHint] = useState<string | null>(null);

  useEffect(() => {
    if (!name && ctx.salon) setName(ctx.salon.client?.name || telegramUserName());
  }, [ctx.salon, name]);

  const knownPhone = ctx.salon?.client?.phone || contact.data?.phone || null;

  const book = useMutation({
    mutationFn: (phone: string | null) =>
      api.post<ClientAppointment>(`/salons/${slug}/appointments`, {
        service_id: ctx.serviceId,
        staff_id: ctx.staffId,
        starts_at: at,
        name: name.trim(),
        phone,
        comment: comment.trim() || null,
      }),
    onSuccess: (appt) => {
      haptic.success();
      queryClient.invalidateQueries({ queryKey: ["my-appointments"] });
      queryClient.invalidateQueries({ queryKey: ["salon", slug] });
      queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.removeQueries({ queryKey: ["slots"] });
      queryClient.removeQueries({ queryKey: ["days"] });
      navigate(`/s/${slug}/done/${appt.id}`, { replace: true, state: appt });
    },
    onError: async (e) => {
      haptic.error();
      if (e instanceof ApiError && e.code === "slot_taken") {
        queryClient.removeQueries({ queryKey: ["slots"] });
        queryClient.removeQueries({ queryKey: ["days"] });
        await alertDialog(e.message);
        back();
        return;
      }
      await alertDialog(e instanceof ApiError ? e.message : "Не удалось записаться");
    },
  });

  const submit = async () => {
    if (!name.trim()) {
      await alertDialog("Укажите имя");
      return;
    }
    if (phoneMode === "manual") {
      if (!isPhoneComplete(manualPhone)) {
        await alertDialog("Введите номер телефона полностью");
        return;
      }
      book.mutate(`+${phoneDigits(manualPhone)}`);
      return;
    }
    if (knownPhone) {
      book.mutate(knownPhone);
      return;
    }
    // Телефона нет — просим поделиться им через Telegram
    const shared = await requestContact();
    if (!shared) {
      setPhoneMode("manual");
      setPhoneHint("Введите номер телефона, чтобы салон мог связаться с вами");
      return;
    }
    setWaiting(true);
    const phone = await waitForContact();
    setWaiting(false);
    if (!phone) {
      setPhoneMode("manual");
      setPhoneHint("Не удалось получить номер из Telegram — введите его вручную");
      return;
    }
    queryClient.setQueryData(["contact-status"], { received: true, phone });
    book.mutate(phone);
  };

  useMainButton({
    text: "Записаться",
    onClick: () => void submit(),
    progress: book.isPending || waiting,
    disabled: book.isPending || waiting,
    visible: !!ctx.service && !!at,
  });

  if (ctx.loading || contact.isLoading) return <Spinner />;
  if (ctx.error) return <ErrorView error={ctx.error} />;
  if (!ctx.salon || !ctx.service || !at) return <ErrorView error={new Error()} />;

  const masterName =
    ctx.master?.display_name ??
    ctx.staffList?.find((s) => s.id === slotStaff)?.display_name ??
    "Любой мастер";

  return (
    <div className="page">
      <div className="page-title">Подтверждение</div>
      <BookingSummary
        serviceName={ctx.service.name}
        price={ctx.master?.price ?? ctx.service.price}
        priceIsFrom={ctx.service.price_is_from}
        duration={ctx.master?.duration_min ?? ctx.service.duration_min}
        master={masterName}
        when={formatDateTime(at, ctx.salon.timezone)}
      />
      {ctx.salon.address && <p className="hint" style={{ margin: "-4px 8px 12px" }}>📍 {ctx.salon.address}</p>}

      <Section title="Ваши данные">
        <Field label="Имя">
          <input
            className="input"
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
          />
        </Field>
        {phoneMode === "auto" && knownPhone && (
          <div className="field">
            <span className="field-label">Телефон</span>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>{prettyPhone(knownPhone)}</span>
              <button className="link-btn" onClick={() => setPhoneMode("manual")}>
                Изменить
              </button>
            </div>
          </div>
        )}
        {phoneMode === "auto" && !knownPhone && (
          <div className="field">
            <span className="field-label">Телефон</span>
            <div className="hint">
              {waiting
                ? "Ждём номер из Telegram…"
                : "При записи Telegram попросит поделиться номером — это нужно салону для связи."}
            </div>
            <button className="link-btn" style={{ marginTop: 6 }} onClick={() => setPhoneMode("manual")}>
              Ввести номер вручную
            </button>
          </div>
        )}
        {phoneMode === "manual" && (
          <Field label="Телефон">
            <input
              className="input"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              value={manualPhone}
              placeholder="+7 (___) ___-__-__"
              onChange={(e) => setManualPhone(maskPhone(e.target.value))}
            />
            {phoneHint && <div className="hint" style={{ marginTop: 4 }}>{phoneHint}</div>}
          </Field>
        )}
        <Field label="Комментарий (необязательно)">
          <textarea
            className="input"
            value={comment}
            maxLength={500}
            rows={2}
            onChange={(e) => setComment(e.target.value)}
          />
        </Field>
      </Section>

      <p className="legal">
        Нажимая кнопку, вы соглашаетесь с{" "}
        <a
          href="/privacy"
          onClick={(e) => {
            e.preventDefault();
            openLink(new URL("/privacy", window.location.origin).href);
          }}
        >
          политикой обработки персональных данных
        </a>
        .
      </p>
    </div>
  );
}
