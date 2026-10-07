import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import type { AppointmentStatus, ManageAppointment } from "../../api/types";
import { ErrorView, Field, Row, Section, Spinner, StatusBadge, toast } from "../../components/ui";
import {
  dateKey,
  formatDateTime,
  formatPrice,
  formatTime,
  prettyPhone,
  zonedToDate,
} from "../../lib/format";
import { useBack } from "../../lib/hooks";
import { alertDialog, confirmDialog, haptic } from "../../telegram/webapp";
import { useManage } from "./context";
import { useStaffList } from "./hooks";

export function AppointmentDetailPage() {
  const { id = "" } = useParams();
  const { salonId, salon, isAdmin, base, staffId } = useManage();
  const tz = salon.timezone;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  useBack(base);
  const [moving, setMoving] = useState(false);
  const [moveDate, setMoveDate] = useState("");
  const [moveTime, setMoveTime] = useState("");
  const [moveStaff, setMoveStaff] = useState<number | null>(null);
  const staffList = useStaffList();

  const appt = useQuery({
    queryKey: ["manage", salonId, "appointment", id],
    queryFn: () => api.get<ManageAppointment>(`/manage/${salonId}/appointments/${id}`),
  });

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.patch<ManageAppointment>(`/manage/${salonId}/appointments/${id}`, body),
    onSuccess: (data) => {
      haptic.success();
      queryClient.setQueryData(["manage", salonId, "appointment", id], data);
      queryClient.invalidateQueries({ queryKey: ["manage", salonId, "calendar"] });
      queryClient.invalidateQueries({ queryKey: ["manage", salonId, "client"] });
      setMoving(false);
      toast("Сохранено");
    },
    onError: (e) => {
      haptic.error();
      alertDialog(e instanceof ApiError ? e.message : "Не удалось сохранить");
    },
  });

  if (appt.isLoading) return <Spinner />;
  if (appt.isError) return <ErrorView error={appt.error} />;
  const a = appt.data!;
  const active = a.status === "booked" || a.status === "confirmed";
  const setStatus = async (status: AppointmentStatus, question?: string) => {
    if (question && !(await confirmDialog(question))) return;
    patch.mutate({ status });
  };
  const startMove = () => {
    setMoveDate(dateKey(a.starts_at, tz));
    setMoveTime(formatTime(a.starts_at, tz));
    setMoveStaff(a.staff_id);
    setMoving(true);
  };
  const staffName = staffList.data?.find((s) => s.id === a.staff_id)?.display_name;

  return (
    <div className="page">
      <div className="page-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span>{a.service.name}</span>
        <StatusBadge status={a.status} />
      </div>
      <Section>
        <div className="summary-card">
          <div style={{ fontWeight: 600, fontSize: 16 }}>
            {formatDateTime(a.starts_at, tz)}–{formatTime(a.ends_at, tz)}
          </div>
          {staffName && (
            <div className="kv">
              <span>Мастер</span>
              <span>{staffName}</span>
            </div>
          )}
          <div className="kv">
            <span>Стоимость</span>
            <span>{formatPrice(a.price, a.price_is_from)}</span>
          </div>
          <div className="kv">
            <span>Источник</span>
            <span>{a.source === "manual" ? "Ручная запись" : "Онлайн-запись"}</span>
          </div>
          {a.comment && (
            <div className="kv">
              <span>Комментарий</span>
              <span>{a.comment}</span>
            </div>
          )}
        </div>
      </Section>

      <Section title="Клиент">
        <Row
          title={a.client.name}
          sub={`Визитов: ${a.client.visits_count} · неявок: ${a.client.no_show_count}`}
          chevron
          onClick={() => navigate(`${base}/clients/${a.client.id}`)}
        />
        <Row
          title={prettyPhone(a.client.phone)}
          side="Позвонить"
          onClick={() => {
            window.location.href = `tel:${a.client.phone}`;
          }}
        />
      </Section>

      {active && !moving && (
        <>
          <div className="btn-row" style={{ marginBottom: 8 }}>
            <button className="btn" disabled={patch.isPending} onClick={() => setStatus("completed")}>
              Пришёл
            </button>
            <button
              className="btn secondary"
              disabled={patch.isPending}
              onClick={() => setStatus("no_show", "Отметить, что клиент не пришёл?")}
            >
              Не пришёл
            </button>
          </div>
          <div className="btn-row">
            <button className="btn secondary" onClick={startMove}>
              Перенести
            </button>
            <button
              className="btn danger"
              disabled={patch.isPending}
              onClick={() =>
                setStatus("cancelled_by_salon", "Отменить запись? Клиент получит уведомление.")
              }
            >
              Отменить
            </button>
          </div>
        </>
      )}

      {(a.status === "completed" || a.status === "no_show") && (
        <button
          className="btn secondary block"
          disabled={patch.isPending}
          onClick={() => setStatus(a.status === "completed" ? "no_show" : "completed")}
        >
          {a.status === "completed" ? "Исправить: не пришёл" : "Исправить: пришёл"}
        </button>
      )}

      {moving && (
        <Section title="Перенос">
          <Field label="Дата">
            <input className="input" type="date" value={moveDate} onChange={(e) => setMoveDate(e.target.value)} />
          </Field>
          <Field label="Время">
            <input
              className="input"
              type="time"
              step={salon.slot_step_min * 60}
              value={moveTime}
              onChange={(e) => setMoveTime(e.target.value)}
            />
          </Field>
          {isAdmin && (
            <Field label="Мастер">
              <select
                className="input"
                value={moveStaff ?? ""}
                onChange={(e) => setMoveStaff(Number(e.target.value))}
              >
                {(staffList.data ?? [])
                  .filter((s) => s.is_active)
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.display_name}
                    </option>
                  ))}
              </select>
            </Field>
          )}
          <div className="section-pad btn-row">
            <button className="btn secondary" onClick={() => setMoving(false)}>
              Отмена
            </button>
            <button
              className="btn"
              disabled={!moveDate || !moveTime || patch.isPending}
              onClick={() =>
                patch.mutate({
                  starts_at: zonedToDate(moveDate, moveTime, tz).toISOString(),
                  staff_id: isAdmin ? moveStaff : staffId,
                })
              }
            >
              Сохранить
            </button>
          </div>
        </Section>
      )}
    </div>
  );
}
