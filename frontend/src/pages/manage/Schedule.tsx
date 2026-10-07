import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, qs } from "../../api/client";
import type { CalendarData, ManageAppointment, StaffCalendar, TimeOff } from "../../api/types";
import { Empty, ErrorView, Row, Section, Spinner, StatusBadge } from "../../components/ui";
import {
  addDays,
  dateKey,
  formatDateKey,
  formatTime,
  minutesOfDay,
  startOfWeek,
} from "../../lib/format";
import { useManage } from "./context";
import { useStaffList } from "./hooks";

const PX_PER_MIN = 1.1;

function blockClass(a: ManageAppointment): string {
  if (a.status === "cancelled_by_client" || a.status === "cancelled_by_salon") return "cancelled";
  return a.status;
}

function DayTimeline({
  day,
  staff,
  data,
  tz,
  onOpen,
}: {
  day: string;
  staff: StaffCalendar[];
  data: CalendarData;
  tz: string;
  onOpen: (id: number) => void;
}) {
  const visible = data.appointments.filter(
    (a) => a.status !== "cancelled_by_client" && a.status !== "cancelled_by_salon",
  );
  // часы отображения: 08–21 и шире, если есть записи раньше/позже
  let startMin = 8 * 60;
  let endMin = 21 * 60;
  for (const a of visible) {
    if (dateKey(a.starts_at, tz) === day) startMin = Math.min(startMin, minutesOfDay(a.starts_at, tz));
    if (dateKey(a.ends_at, tz) === day) endMin = Math.max(endMin, minutesOfDay(a.ends_at, tz));
  }
  startMin = Math.floor(startMin / 60) * 60;
  endMin = Math.min(24 * 60, Math.ceil(endMin / 60) * 60);
  const height = (endMin - startMin) * PX_PER_MIN;
  const HEAD = 36;

  const clamp = (iso: string, isEnd: boolean) => {
    const k = dateKey(iso, tz);
    if (k < day) return startMin;
    if (k > day) return endMin;
    const m = minutesOfDay(iso, tz);
    return Math.min(endMin, Math.max(startMin, isEnd && m === 0 ? 24 * 60 : m));
  };
  const top = (iso: string) => HEAD + (clamp(iso, false) - startMin) * PX_PER_MIN;
  const span = (s: string, e: string) => Math.max(18, (clamp(e, true) - clamp(s, false)) * PX_PER_MIN);

  const hours: number[] = [];
  for (let m = startMin; m <= endMin; m += 60) hours.push(m);

  const now = new Date();
  const showNow = dateKey(now, tz) === day;
  const nowMin = minutesOfDay(now, tz);

  return (
    <div className="timeline-wrap">
      <div className="timeline" style={{ height: height + HEAD + 14 }}>
        <div className="timeline-hours">
          {hours.map((m) => (
            <span key={m} style={{ top: HEAD + (m - startMin) * PX_PER_MIN }}>
              {String(Math.floor(m / 60)).padStart(2, "0")}:00
            </span>
          ))}
        </div>
        {staff.map((s) => (
          <div key={s.id} className="timeline-col">
            <div className="timeline-col-head">{s.display_name}</div>
            {hours.map((m) => (
              <div key={m} className="timeline-line" style={{ top: HEAD + (m - startMin) * PX_PER_MIN }} />
            ))}
            {showNow && nowMin >= startMin && nowMin <= endMin && (
              <div className="now-line" style={{ top: HEAD + (nowMin - startMin) * PX_PER_MIN }} />
            )}
            {data.time_off
              .filter((t: TimeOff) => t.staff_id === s.id)
              .map((t) => (
                <div
                  key={`t${t.id}`}
                  className="tl-block off"
                  style={{ top: top(t.starts_at), height: span(t.starts_at, t.ends_at) }}
                >
                  {t.reason || "Недоступен"}
                </div>
              ))}
            {visible
              .filter((a) => a.staff_id === s.id)
              .map((a) => (
                <button
                  key={a.id}
                  type="button"
                  className={`tl-block ${blockClass(a)}`}
                  style={{ top: top(a.starts_at), height: span(a.starts_at, a.ends_at) }}
                  onClick={() => onOpen(a.id)}
                >
                  <b>{formatTime(a.starts_at, tz)}</b> {a.client.name}
                  <div className="muted">{a.service.name}</div>
                </button>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function WeekList({
  from,
  data,
  tz,
  multiStaff,
  onOpen,
}: {
  from: string;
  data: CalendarData;
  tz: string;
  multiStaff: boolean;
  onOpen: (id: number) => void;
}) {
  const staffName = new Map(data.staff.map((s) => [s.id, s.display_name]));
  const days = Array.from({ length: 7 }, (_, i) => addDays(from, i));
  return (
    <>
      {days.map((d) => {
        const items = data.appointments.filter((a) => dateKey(a.starts_at, tz) === d);
        const offs = data.time_off.filter(
          (t) => dateKey(t.starts_at, tz) <= d && dateKey(t.ends_at, tz) >= d,
        );
        return (
          <Section key={d} title={formatDateKey(d)}>
            {items.length === 0 && offs.length === 0 && (
              <div className="row static hint">Записей нет</div>
            )}
            {offs.map((t) => (
              <Row
                key={`t${t.id}`}
                title={t.reason || "Недоступен"}
                sub={multiStaff ? staffName.get(t.staff_id) : undefined}
                side={`${formatTime(t.starts_at, tz)}–${formatTime(t.ends_at, tz)}`}
              />
            ))}
            {items.map((a) => (
              <Row
                key={a.id}
                title={
                  <>
                    {formatTime(a.starts_at, tz)} · {a.client.name}
                  </>
                }
                sub={
                  <>
                    {a.service.name}
                    {multiStaff ? ` · ${staffName.get(a.staff_id) ?? ""}` : ""}
                  </>
                }
                side={<StatusBadge status={a.status} />}
                onClick={() => onOpen(a.id)}
              />
            ))}
          </Section>
        );
      })}
    </>
  );
}

export function SchedulePage() {
  const { salonId, salon, isAdmin, base } = useManage();
  const tz = salon.timezone;
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const today = dateKey(new Date(), tz);
  const day = params.get("date") ?? today;
  const view = params.get("view") === "week" ? "week" : "day";
  const staffFilter = params.get("staff");
  const from = view === "week" ? startOfWeek(day) : day;
  const to = view === "week" ? addDays(from, 6) : day;

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    setParams(next, { replace: true });
  };

  const cal = useQuery({
    queryKey: ["manage", salonId, "calendar", from, to, staffFilter],
    queryFn: () =>
      api.get<CalendarData>(
        `/manage/${salonId}/calendar${qs({ from, to, staff_id: staffFilter })}`,
      ),
  });
  const staffList = useStaffList();
  const activeStaff = (staffList.data ?? []).filter((s) => s.is_active);

  const step = view === "week" ? 7 : 1;
  const open = (id: number) => navigate(`${base}/appointments/${id}`);
  const staffCols = cal.data?.staff ?? [];

  return (
    <div className="page">
      <div className="tabs">
        <button className={view === "day" ? "active" : ""} onClick={() => update({ view: null })}>
          День
        </button>
        <button className={view === "week" ? "active" : ""} onClick={() => update({ view: "week" })}>
          Неделя
        </button>
      </div>
      <div className="toolbar">
        <button className="icon-btn" onClick={() => update({ date: addDays(day, -step) })}>
          ‹
        </button>
        <div className="grow">
          {view === "day"
            ? formatDateKey(day)
            : `${formatDateKey(from)} — ${formatDateKey(to)}`}
        </div>
        <button className="icon-btn" onClick={() => update({ date: addDays(day, step) })}>
          ›
        </button>
        {day !== today && (
          <button className="icon-btn" onClick={() => update({ date: null })}>
            Сегодня
          </button>
        )}
      </div>
      {isAdmin && activeStaff.length > 1 && (
        <div className="section" style={{ padding: "4px 16px" }}>
          <select
            className="input"
            value={staffFilter ?? ""}
            onChange={(e) => update({ staff: e.target.value || null })}
          >
            <option value="">Все мастера</option>
            {activeStaff.map((s) => (
              <option key={s.id} value={s.id}>
                {s.display_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {cal.isLoading && <Spinner />}
      {cal.isError && <ErrorView error={cal.error} onRetry={() => cal.refetch()} />}
      {cal.data && staffCols.length === 0 && <Empty>Нет активных мастеров</Empty>}
      {cal.data && staffCols.length > 0 && view === "day" && (
        <DayTimeline day={day} staff={staffCols} data={cal.data} tz={tz} onOpen={open} />
      )}
      {cal.data && view === "week" && (
        <WeekList from={from} data={cal.data} tz={tz} multiStaff={staffCols.length > 1} onOpen={open} />
      )}

      <button
        className="fab"
        aria-label="Новая запись"
        onClick={() => navigate(`${base}/appointments/new?date=${day}${staffFilter ? `&staff=${staffFilter}` : ""}`)}
      >
        +
      </button>
    </div>
  );
}
