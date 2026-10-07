import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import type { Override, Schedule, TimeOff, WeeklyInterval } from "../../api/types";
import { ErrorView, Field, Row, Section, Spinner, toast } from "../../components/ui";
import {

  dateKey,
  formatDateKey,
  formatDateTime,
  hhmm,
  zonedToDate,
} from "../../lib/format";
import { alertDialog, confirmDialog, haptic, useMainButton } from "../../telegram/webapp";
import { useManage } from "./context";
import { useStaffList } from "./hooks";

const FULL_WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];

type Interval = { start: string; end: string };
type Week = Interval[][]; // 7 дней

function toWeek(rows: WeeklyInterval[]): Week {
  const week: Week = Array.from({ length: 7 }, () => []);
  for (const r of rows) week[r.weekday].push({ start: hhmm(r.start_time), end: hhmm(r.end_time) });
  return week;
}

function fromWeek(week: Week): WeeklyInterval[] {
  return week.flatMap((items, weekday) =>
    items.map((i) => ({ weekday, start_time: i.start, end_time: i.end })),
  );
}

function validWeek(week: Week): boolean {
  return week.every((items) =>
    items.every((i) => /^\d\d:\d\d$/.test(i.start) && /^\d\d:\d\d$/.test(i.end) && (i.end === "00:00" || i.start < i.end)),
  );
}

function IntervalsEditor({
  week,
  onChange,
  addLabel,
  defaults,
}: {
  week: Week;
  onChange: (w: Week) => void;
  addLabel: string;
  defaults: Interval;
}) {
  const update = (day: number, idx: number, patch: Partial<Interval>) => {
    const next = week.map((d) => d.slice());
    next[day][idx] = { ...next[day][idx], ...patch };
    onChange(next);
  };
  return (
    <>
      {week.map((items, day) => (
        <div key={day} className="field">
          <span className="field-label">{FULL_WEEKDAYS[day]}</span>
          {items.length === 0 && <div className="hint">—</div>}
          {items.map((i, idx) => (
            <div key={idx} className="interval-row">
              <input
                className="input input-boxed"
                type="time"
                value={i.start}
                onChange={(e) => update(day, idx, { start: e.target.value })}
              />
              <span>–</span>
              <input
                className="input input-boxed"
                type="time"
                value={i.end}
                onChange={(e) => update(day, idx, { end: e.target.value })}
              />
              <button
                type="button"
                className="icon-btn"
                aria-label="Удалить"
                onClick={() => {
                  const next = week.map((d) => d.slice());
                  next[day].splice(idx, 1);
                  onChange(next);
                }}
              >
                ✕
              </button>
            </div>
          ))}
          <button
            type="button"
            className="link-btn"
            style={{ marginTop: 4 }}
            onClick={() => {
              const next = week.map((d) => d.slice());
              next[day].push({ ...defaults });
              onChange(next);
            }}
          >
            + {addLabel}
          </button>
        </div>
      ))}
    </>
  );
}

export function MySchedulePage() {
  const { salonId, salon, isAdmin, staffId: myStaffId } = useManage();
  const tz = salon.timezone;
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const staffId = isAdmin ? Number(params.get("staff")) || myStaffId : myStaffId;
  const staffList = useStaffList();
  const path = `/manage/${salonId}/staff/${staffId}`;
  const today = dateKey(new Date(), tz);

  const schedule = useQuery({
    queryKey: ["manage", salonId, "schedule", staffId],
    queryFn: () => api.get<Schedule>(`${path}/schedule`),
  });
  const overrides = useQuery({
    queryKey: ["manage", salonId, "overrides", staffId],
    queryFn: () => api.get<Override[]>(`${path}/overrides`),
  });
  const timeOff = useQuery({
    queryKey: ["manage", salonId, "time-off", staffId],
    queryFn: () => api.get<TimeOff[]>(`${path}/time-off`),
  });

  const [work, setWork] = useState<Week | null>(null);
  const [breaks, setBreaks] = useState<Week | null>(null);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (schedule.data) {
      setWork(toWeek(schedule.data.work));
      setBreaks(toWeek(schedule.data.breaks));
      setDirty(false);
    }
  }, [schedule.data]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["manage", salonId] });
    queryClient.removeQueries({ queryKey: ["slots"] });
    queryClient.removeQueries({ queryKey: ["days"] });
  };
  const onError = (e: unknown) => {
    haptic.error();
    alertDialog(e instanceof ApiError ? e.message : "Не удалось сохранить");
  };

  const save = useMutation({
    mutationFn: () =>
      api.put<Schedule>(`${path}/schedule`, { work: fromWeek(work!), breaks: fromWeek(breaks!) }),
    onSuccess: () => {
      haptic.success();
      toast("График сохранён");
      invalidate();
    },
    onError,
  });

  useMainButton({
    text: "Сохранить график",
    visible: dirty,
    progress: save.isPending,
    disabled: save.isPending,
    onClick: () => {
      if (!work || !breaks || !validWeek(work) || !validWeek(breaks)) {
        alertDialog("Проверьте время: начало должно быть раньше конца");
        return;
      }
      save.mutate();
    },
  });

  // исключения
  const [ovDate, setOvDate] = useState(today);
  const [ovDayOff, setOvDayOff] = useState(true);
  const [ovStart, setOvStart] = useState("10:00");
  const [ovEnd, setOvEnd] = useState("18:00");
  const addOverride = useMutation({
    mutationFn: () =>
      api.post<Override>(`${path}/overrides`, {
        date: ovDate,
        is_day_off: ovDayOff,
        start_time: ovDayOff ? null : ovStart,
        end_time: ovDayOff ? null : ovEnd,
      }),
    onSuccess: () => {
      toast("Исключение добавлено");
      invalidate();
    },
    onError,
  });
  const delOverride = useMutation({
    mutationFn: (id: number) => api.delete(`${path}/overrides/${id}`),
    onSuccess: invalidate,
    onError,
  });

  // блокировки
  const [toFromDate, setToFromDate] = useState(today);
  const [toFromTime, setToFromTime] = useState("13:00");
  const [toToDate, setToToDate] = useState(today);
  const [toToTime, setToToTime] = useState("14:00");
  const [toReason, setToReason] = useState("");
  const addTimeOff = useMutation({
    mutationFn: () =>
      api.post<TimeOff>(`${path}/time-off`, {
        starts_at: zonedToDate(toFromDate, toFromTime, tz).toISOString(),
        ends_at: zonedToDate(toToDate, toToTime, tz).toISOString(),
        reason: toReason.trim() || null,
      }),
    onSuccess: () => {
      toast("Время заблокировано");
      setToReason("");
      invalidate();
    },
    onError,
  });
  const delTimeOff = useMutation({
    mutationFn: (id: number) => api.delete(`${path}/time-off/${id}`),
    onSuccess: invalidate,
    onError,
  });

  if (schedule.isLoading) return <Spinner />;
  if (schedule.isError) return <ErrorView error={schedule.error} onRetry={() => schedule.refetch()} />;

  return (
    <div className="page">
      <div className="page-title">График</div>
      {isAdmin && (
        <div className="section" style={{ padding: "4px 16px" }}>
          <select
            className="input"
            value={staffId}
            onChange={(e) => setParams({ staff: e.target.value }, { replace: true })}
          >
            {(staffList.data ?? [])
              .filter((s) => s.is_active)
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.display_name}
                </option>
              ))}
          </select>
        </div>
      )}

      {work && (
        <Section title="Рабочие часы по дням недели">
          <IntervalsEditor
            week={work}
            addLabel="смена"
            defaults={{ start: "10:00", end: "19:00" }}
            onChange={(w) => {
              setWork(w);
              setDirty(true);
            }}
          />
        </Section>
      )}
      {breaks && (
        <Section title="Регулярные перерывы">
          <IntervalsEditor
            week={breaks}
            addLabel="перерыв"
            defaults={{ start: "13:00", end: "14:00" }}
            onChange={(w) => {
              setBreaks(w);
              setDirty(true);
            }}
          />
        </Section>
      )}

      <Section title="Исключения по датам">
        {overrides.data?.map((o) => (
          <Row
            key={o.id}
            title={formatDateKey(o.date)}
            sub={o.is_day_off ? "Выходной" : `${hhmm(o.start_time!)}–${hhmm(o.end_time!)}`}
            side={
              <button
                className="link-btn"
                onClick={async () => {
                  if (await confirmDialog("Удалить исключение?")) delOverride.mutate(o.id);
                }}
              >
                Удалить
              </button>
            }
          />
        ))}
        <Field label="Дата">
          <input className="input" type="date" min={today} value={ovDate} onChange={(e) => setOvDate(e.target.value)} />
        </Field>
        <label className="check">
          <input type="checkbox" checked={ovDayOff} onChange={(e) => setOvDayOff(e.target.checked)} />
          <span>Выходной весь день</span>
        </label>
        {!ovDayOff && (
          <div className="field">
            <span className="field-label">Рабочие часы в этот день</span>
            <div className="interval-row">
              <input className="input input-boxed" type="time" value={ovStart} onChange={(e) => setOvStart(e.target.value)} />
              <span>–</span>
              <input className="input input-boxed" type="time" value={ovEnd} onChange={(e) => setOvEnd(e.target.value)} />
            </div>
          </div>
        )}
        <div className="section-pad">
          <button className="btn secondary block" disabled={addOverride.isPending} onClick={() => addOverride.mutate()}>
            Добавить исключение
          </button>
        </div>
      </Section>

      <Section title="Блокировка времени и отпуск">
        {timeOff.data?.map((t) => (
          <Row
            key={t.id}
            title={t.reason || "Недоступен"}
            sub={`${formatDateTime(t.starts_at, tz)} — ${formatDateTime(t.ends_at, tz)}`}
            side={
              <button
                className="link-btn"
                onClick={async () => {
                  if (await confirmDialog("Снять блокировку?")) delTimeOff.mutate(t.id);
                }}
              >
                Удалить
              </button>
            }
          />
        ))}
        <div className="field">
          <span className="field-label">С</span>
          <div className="interval-row">
            <input className="input input-boxed" type="date" value={toFromDate} onChange={(e) => {
              setToFromDate(e.target.value);
              if (e.target.value > toToDate) setToToDate(e.target.value);
            }} />
            <input className="input input-boxed" type="time" value={toFromTime} onChange={(e) => setToFromTime(e.target.value)} />
          </div>
        </div>
        <div className="field">
          <span className="field-label">По</span>
          <div className="interval-row">
            <input className="input input-boxed" type="date" value={toToDate} onChange={(e) => setToToDate(e.target.value)} />
            <input className="input input-boxed" type="time" value={toToTime} onChange={(e) => setToToTime(e.target.value)} />
          </div>
        </div>
        <Field label="Причина (необязательно)">
          <input className="input" value={toReason} maxLength={200} placeholder="Отпуск, обучение…" onChange={(e) => setToReason(e.target.value)} />
        </Field>
        <div className="section-pad">
          <button className="btn secondary block" disabled={addTimeOff.isPending} onClick={() => addTimeOff.mutate()}>
            Заблокировать время
          </button>
        </div>
      </Section>
      <p className="hint" style={{ margin: "0 8px" }}>
        Все время указано в часовом поясе салона ({tz}).
      </p>
    </div>
  );
}
