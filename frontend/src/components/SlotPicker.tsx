import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, qs } from "../api/client";
import type { DayAvailability, SalonPublic, Slot } from "../api/types";
import { addDays, dateKey, formatDateKey, formatTime } from "../lib/format";
import { haptic } from "../telegram/webapp";
import { Calendar } from "./Calendar";
import { Empty, ErrorView, Spinner } from "./ui";

interface Props {
  salon: SalonPublic;
  serviceId: number;
  staffId: number | null;
  appointmentId?: number;
  selected: Slot | null;
  onSelect: (slot: Slot) => void;
}

export function SlotPicker({ salon, serviceId, staffId, appointmentId, selected, onSelect }: Props) {
  const today = dateKey(new Date(), salon.timezone);
  const last = addDays(today, salon.booking_horizon_days - 1);
  const [day, setDay] = useState<string | null>(
    selected ? dateKey(selected.starts_at, salon.timezone) : null,
  );

  const days = useQuery({
    queryKey: ["days", salon.slug, serviceId, staffId, appointmentId, today],
    queryFn: () =>
      api.get<DayAvailability[]>(
        `/salons/${salon.slug}/availability/days${qs({
          service_id: serviceId,
          staff_id: staffId,
          from: today,
          to: last,
          appointment_id: appointmentId,
        })}`,
      ),
  });
  const available = useMemo(
    () => (days.data ? new Set(days.data.filter((d) => d.has_slots).map((d) => d.date)) : undefined),
    [days.data],
  );

  // автоматически выбираем первый день со слотами
  useEffect(() => {
    if (!day && available && available.size) setDay([...available].sort()[0]);
  }, [available, day]);

  const slots = useQuery({
    queryKey: ["slots", salon.slug, serviceId, staffId, appointmentId, day],
    queryFn: () =>
      api.get<Slot[]>(
        `/salons/${salon.slug}/availability/slots${qs({
          service_id: serviceId,
          staff_id: staffId,
          date: day,
          appointment_id: appointmentId,
        })}`,
      ),
    enabled: !!day,
  });

  if (days.isError) return <ErrorView error={days.error} onRetry={() => days.refetch()} />;

  return (
    <>
      <div className="section">
        <Calendar
          from={today}
          to={last}
          today={today}
          selected={day}
          available={available}
          onSelect={(d) => {
            haptic.select();
            setDay(d);
          }}
        />
      </div>
      {days.isLoading && <Spinner />}
      {available && available.size === 0 && (
        <Empty icon="😔">
          Свободного времени нет на ближайшие {salon.booking_horizon_days} дн. Попробуйте выбрать
          другого мастера или позвоните в салон.
        </Empty>
      )}
      {day && (
        <>
          <div className="section-header">{formatDateKey(day)}</div>
          <div className="section section-pad">
            {slots.isLoading && <Spinner />}
            {slots.isError && <ErrorView error={slots.error} onRetry={() => slots.refetch()} />}
            {slots.data && slots.data.length === 0 && (
              <div className="hint center">На этот день свободного времени нет</div>
            )}
            {slots.data && slots.data.length > 0 && (
              <div className="chips">
                {slots.data.map((s) => {
                  const active = selected?.starts_at === s.starts_at;
                  return (
                    <button
                      key={s.starts_at}
                      type="button"
                      className={active ? "chip active" : "chip"}
                      onClick={() => {
                        haptic.select();
                        onSelect(s);
                      }}
                    >
                      {formatTime(s.starts_at, salon.timezone)}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
