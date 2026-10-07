import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api, qs } from "../../api/client";
import type { ClientRow, ManageAppointment, Slot, StaffService } from "../../api/types";
import { Field, Row, Section, Spinner } from "../../components/ui";
import {
  dateKey,
  formatDuration,
  formatTime,
  isPhoneComplete,
  maskPhone,
  phoneDigits,
  prettyPhone,
  zonedToDate,
} from "../../lib/format";
import { useBack } from "../../lib/hooks";
import { alertDialog, haptic, useMainButton } from "../../telegram/webapp";
import { useManage } from "./context";
import { useServiceList, useStaffList } from "./hooks";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function NewAppointmentPage() {
  const { salonId, salon, isAdmin, staffId: myStaffId, base } = useManage();
  const tz = salon.timezone;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  useBack(base);

  const staffList = useStaffList();
  const services = useServiceList();
  const bookable = (staffList.data ?? []).filter((s) => s.is_active);

  const [staffId, setStaffId] = useState<number | null>(
    isAdmin ? Number(params.get("staff")) || null : myStaffId,
  );
  useEffect(() => {
    if (staffId === null && bookable.length) {
      setStaffId(bookable.find((s) => s.is_bookable)?.id ?? bookable[0].id);
    }
  }, [bookable, staffId]);

  const staffServices = useQuery({
    queryKey: ["manage", salonId, "staff-services", staffId],
    queryFn: () => api.get<StaffService[]>(`/manage/${salonId}/staff/${staffId}/services`),
    enabled: !!staffId,
  });
  const offered = useMemo(() => {
    const ids = new Map((staffServices.data ?? []).map((s) => [s.service_id, s]));
    return (services.data ?? [])
      .filter((s) => s.is_active && ids.has(s.id))
      .map((s) => ({
        ...s,
        duration_min: ids.get(s.id)!.duration_override_min ?? s.duration_min,
      }));
  }, [services.data, staffServices.data]);
  const [serviceId, setServiceId] = useState<number | null>(null);
  useEffect(() => {
    if (offered.length && !offered.some((s) => s.id === serviceId)) setServiceId(offered[0].id);
    if (!offered.length) setServiceId(null);
  }, [offered, serviceId]);

  const [day, setDay] = useState(params.get("date") ?? dateKey(new Date(), tz));
  const [time, setTime] = useState("");
  const slots = useQuery({
    queryKey: ["manage-slots", salon.slug, serviceId, staffId, day],
    queryFn: () =>
      api.get<Slot[]>(
        `/salons/${salon.slug}/availability/slots${qs({ service_id: serviceId, staff_id: staffId, date: day })}`,
      ),
    enabled: !!serviceId && !!staffId,
  });

  // клиент
  const [clientMode, setClientMode] = useState<"search" | "new">("search");
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim(), 300);
  const [client, setClient] = useState<ClientRow | null>(null);
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("+7");
  const [comment, setComment] = useState("");
  const found = useQuery({
    queryKey: ["manage", salonId, "clients", q],
    queryFn: () => api.get<ClientRow[]>(`/manage/${salonId}/clients${qs({ q, limit: 10 })}`),
    enabled: clientMode === "search" && q.length >= 2 && !client,
  });

  const create = useMutation({
    mutationFn: () =>
      api.post<ManageAppointment>(`/manage/${salonId}/appointments`, {
        staff_id: staffId,
        service_id: serviceId,
        starts_at: zonedToDate(day, time, tz).toISOString(),
        client_id: clientMode === "search" ? client?.id : null,
        client:
          clientMode === "new"
            ? { name: newName.trim(), phone: `+${phoneDigits(newPhone)}` }
            : null,
        comment: comment.trim() || null,
      }),
    onSuccess: (a) => {
      haptic.success();
      queryClient.invalidateQueries({ queryKey: ["manage", salonId] });
      queryClient.removeQueries({ queryKey: ["manage-slots"] });
      navigate(`${base}/appointments/${a.id}`, { replace: true });
    },
    onError: (e) => {
      haptic.error();
      alertDialog(e instanceof ApiError ? e.message : "Не удалось создать запись");
    },
  });

  const clientReady =
    clientMode === "search" ? !!client : newName.trim().length > 0 && isPhoneComplete(newPhone);
  const ready = !!staffId && !!serviceId && !!day && /^\d\d:\d\d$/.test(time) && clientReady;

  useMainButton({
    text: "Создать запись",
    onClick: () => {
      if (ready) create.mutate();
      else alertDialog("Заполните мастера, услугу, время и клиента");
    },
    progress: create.isPending,
    disabled: create.isPending,
  });

  if (staffList.isLoading || services.isLoading) return <Spinner />;

  return (
    <div className="page">
      <div className="page-title">Новая запись</div>

      <Section>
        {isAdmin && (
          <Field label="Мастер">
            <select
              className="input"
              value={staffId ?? ""}
              onChange={(e) => {
                setStaffId(Number(e.target.value));
                setTime("");
              }}
            >
              {bookable.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.display_name}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Услуга">
          {offered.length ? (
            <select
              className="input"
              value={serviceId ?? ""}
              onChange={(e) => {
                setServiceId(Number(e.target.value));
                setTime("");
              }}
            >
              {offered.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {formatDuration(s.duration_min)}
                </option>
              ))}
            </select>
          ) : (
            <div className="hint">У мастера нет услуг. Назначьте их в разделе «Сотрудники».</div>
          )}
        </Field>
        <Field label="Дата">
          <input
            className="input"
            type="date"
            value={day}
            onChange={(e) => {
              setDay(e.target.value);
              setTime("");
            }}
          />
        </Field>
        <Field label="Время">
          <input
            className="input"
            type="time"
            value={time}
            step={salon.slot_step_min * 60}
            onChange={(e) => setTime(e.target.value)}
          />
        </Field>
      </Section>

      {serviceId && (
        <Section title="Свободное время" pad>
          {slots.isLoading && <Spinner />}
          {slots.data?.length === 0 && (
            <div className="hint">
              Свободных слотов по графику нет — можно указать время вручную.
            </div>
          )}
          <div className="chips">
            {slots.data?.map((s) => {
              const t = formatTime(s.starts_at, tz);
              return (
                <button
                  key={s.starts_at}
                  type="button"
                  className={t === time ? "chip active" : "chip"}
                  onClick={() => {
                    haptic.select();
                    setTime(t);
                  }}
                >
                  {t}
                </button>
              );
            })}
          </div>
        </Section>
      )}

      <div className="section-header">Клиент</div>
      <div className="tabs">
        <button className={clientMode === "search" ? "active" : ""} onClick={() => setClientMode("search")}>
          Из базы
        </button>
        <button className={clientMode === "new" ? "active" : ""} onClick={() => setClientMode("new")}>
          Новый клиент
        </button>
      </div>
      {clientMode === "search" && (
        <Section>
          {client ? (
            <Row
              title={client.name}
              sub={prettyPhone(client.phone)}
              side={
                <button className="link-btn" onClick={() => setClient(null)}>
                  Изменить
                </button>
              }
            />
          ) : (
            <>
              <Field label="Поиск по имени или телефону">
                <input
                  className="input"
                  value={query}
                  placeholder="Например, Анна или 916"
                  onChange={(e) => setQuery(e.target.value)}
                />
              </Field>
              {found.data?.map((c) => (
                <Row
                  key={c.id}
                  title={c.name}
                  sub={prettyPhone(c.phone)}
                  onClick={() => {
                    setClient(c);
                    haptic.select();
                  }}
                />
              ))}
              {found.data?.length === 0 && <div className="row static hint">Никого не нашли</div>}
            </>
          )}
        </Section>
      )}
      {clientMode === "new" && (
        <Section>
          <Field label="Имя">
            <input className="input" value={newName} maxLength={120} onChange={(e) => setNewName(e.target.value)} />
          </Field>
          <Field label="Телефон">
            <input
              className="input"
              type="tel"
              inputMode="tel"
              value={newPhone}
              onChange={(e) => setNewPhone(maskPhone(e.target.value))}
            />
          </Field>
        </Section>
      )}
      <Section>
        <Field label="Комментарий">
          <textarea className="input" rows={2} maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
        </Field>
      </Section>
    </div>
  );
}
