import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import type { ClientAppointment, Slot } from "../../api/types";
import { SlotPicker } from "../../components/SlotPicker";
import { Empty, ErrorView, Section, Spinner, toast } from "../../components/ui";
import { formatDateTime, prettyPhone } from "../../lib/format";
import { useBack, useSalon } from "../../lib/hooks";
import { alertDialog, confirmDialog, haptic, useMainButton } from "../../telegram/webapp";

export function ReschedulePage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  useBack("/appointments");
  const [slot, setSlot] = useState<Slot | null>(null);

  const appt = useQuery({
    queryKey: ["my-appointment", id],
    queryFn: () => api.get<ClientAppointment>(`/me/appointments/${id}`),
  });
  const salon = useSalon(appt.data?.salon.slug ?? "");

  const move = useMutation({
    mutationFn: (s: Slot) =>
      api.post<ClientAppointment>(`/me/appointments/${id}/reschedule`, {
        starts_at: s.starts_at,
        staff_id: appt.data!.staff.id,
      }),
    onSuccess: () => {
      haptic.success();
      queryClient.invalidateQueries({ queryKey: ["my-appointments"] });
      queryClient.invalidateQueries({ queryKey: ["my-appointment", id] });
      queryClient.removeQueries({ queryKey: ["slots"] });
      queryClient.removeQueries({ queryKey: ["days"] });
      toast("Запись перенесена");
      navigate("/appointments", { replace: true });
    },
    onError: async (e) => {
      haptic.error();
      queryClient.removeQueries({ queryKey: ["slots"] });
      await alertDialog(e instanceof ApiError ? e.message : "Не удалось перенести запись");
      setSlot(null);
    },
  });

  useMainButton({
    text: "Перенести",
    visible: !!slot,
    progress: move.isPending,
    disabled: move.isPending,
    onClick: async () => {
      if (!slot || !appt.data) return;
      const tz = appt.data.salon.timezone;
      if (await confirmDialog(`Перенести запись на ${formatDateTime(slot.starts_at, tz)}?`)) {
        move.mutate(slot);
      }
    },
  });

  if (appt.isLoading || (appt.data && salon.isLoading)) return <Spinner />;
  if (appt.isError) return <ErrorView error={appt.error} />;
  if (salon.isError) return <ErrorView error={salon.error} />;
  const a = appt.data!;
  const tz = a.salon.timezone;

  return (
    <div className="page">
      <div className="page-title">Перенос записи</div>
      <Section>
        <div className="summary-card">
          <div className="title">{a.service.name}</div>
          <div className="kv">
            <span>Мастер</span>
            <span>{a.staff.display_name}</span>
          </div>
          <div className="kv">
            <span>Сейчас</span>
            <span>{formatDateTime(a.starts_at, tz)}</span>
          </div>
          {slot && (
            <div className="kv">
              <span>Новое время</span>
              <span style={{ fontWeight: 600 }}>{formatDateTime(slot.starts_at, tz)}</span>
            </div>
          )}
        </div>
      </Section>
      {!a.can_change ? (
        <Empty icon="☎️">
          Перенести запись онлайн можно не позже чем за {a.salon.cancel_deadline_hours} ч до визита.
          {a.salon.phone && (
            <>
              {" "}
              Позвоните в салон: <a href={`tel:${a.salon.phone}`}>{prettyPhone(a.salon.phone)}</a>
            </>
          )}
        </Empty>
      ) : (
        salon.data && (
          <SlotPicker
            salon={salon.data}
            serviceId={a.service.id}
            staffId={a.staff.id}
            appointmentId={a.id}
            selected={slot}
            onSelect={setSlot}
          />
        )
      )}
    </div>
  );
}
