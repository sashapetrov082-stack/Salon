import { useMemo, useState } from "react";
import { MONTHS, WEEKDAYS_MON, addDays, weekdayOf } from "../lib/format";

interface Props {
  /** Первый и последний доступные дни «YYYY-MM-DD» */
  from: string;
  to: string;
  today: string;
  selected: string | null;
  /** Дни, в которые есть слоты; undefined — ещё загружаются */
  available?: Set<string>;
  onSelect: (day: string) => void;
}

function monthKey(day: string) {
  return day.slice(0, 7);
}

function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function Calendar({ from, to, today, selected, available, onSelect }: Props) {
  const [month, setMonth] = useState(monthKey(selected ?? from));

  const cells = useMemo(() => {
    const first = `${month}-01`;
    const offset = weekdayOf(first);
    const result: (string | null)[] = Array.from({ length: offset }, () => null);
    let d = first;
    while (monthKey(d) === month) {
      result.push(d);
      d = addDays(d, 1);
    }
    return result;
  }, [month]);

  const [y, m] = month.split("-").map(Number);
  const canPrev = month > monthKey(from);
  const canNext = month < monthKey(to);

  return (
    <div className="calendar">
      <div className="calendar-head">
        <button type="button" disabled={!canPrev} onClick={() => setMonth(shiftMonth(month, -1))}>
          ‹
        </button>
        <span>
          {MONTHS[m - 1]} {y}
        </span>
        <button type="button" disabled={!canNext} onClick={() => setMonth(shiftMonth(month, 1))}>
          ›
        </button>
      </div>
      <div className="calendar-grid">
        {WEEKDAYS_MON.map((w) => (
          <div key={w} className="wd">
            {w}
          </div>
        ))}
        {cells.map((day, i) => {
          if (!day) return <div key={`e${i}`} />;
          const inRange = day >= from && day <= to;
          const has = inRange && (available ? available.has(day) : false);
          const cls = [
            "day",
            has ? "available" : "",
            day === selected ? "selected" : "",
            day === today ? "today" : "",
          ].join(" ");
          return (
            <button
              key={day}
              type="button"
              className={cls}
              disabled={!has}
              onClick={() => onSelect(day)}
            >
              {Number(day.slice(8))}
            </button>
          );
        })}
      </div>
    </div>
  );
}
