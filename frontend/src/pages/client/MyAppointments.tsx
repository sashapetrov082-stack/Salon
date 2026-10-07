import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import type { ClientAppointment } from "../../api/types";
import { Empty, ErrorView, Section, Spinner, StatusBadge, toast } from "../../components/ui";
import { formatDateTime, formatPrice, prettyPhone } from "../../lib/format";
import { useBack } from "../../lib/hooks";
import { alertDialog, confirmDialog, haptic, openLink } from "../../telegram/webapp";

type Scope = "upcoming" | "past";

function AppointmentCard({ a, scope }: { a: ClientAppointment; scope: Scope }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tz = a.salon.timezone;

  const cancel = useMutation({
    mutationFn: () => api.post<ClientAppointment>(`/me/appointments/${a.id}/cancel`),
    onSuccess: () => {
      haptic.success();
      toast("Запись отменена");
      queryClient.invalidateQueries({ queryKey: ["my-appointments"] });
    },
    onError: (e) => alertDialog(e instanceof ApiError ? e.message : "Не удалось отменить"),
  });

  const onCancel = async () => {
    if (await confirmDialog(`Отменить запись на ${formatDateTime(a.starts_at, tz)}?`)) {
      cancel.mutate();
    }
  };

  return (
    <Section>
      <div className="summary-card">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <div className="title">{a.service.name}</div>
          <StatusBadge status={a.status} />
        </div>
        <div style={{ margin: "4px 0 6px", fontWeight: 500 }}>{formatDateTime(a.starts_at, tz)}</div>
        <div className="kv">
          <span>Салон</span>
          <span>{a.salon.name}</span>
        </div>
        <div className="kv">
          <span>Мастер</span>
          <span>{a.staff.display_name}</span>
        </div>
        {a.salon.address && (
          <div className="kv">
            <span>Адрес</span>
            <span>
              {a.salon.map_url ? (
                <button className="link-btn" onClick={() => openLink(a.salon.map_url!)}>
                  {a.salon.address}
                </button>
              ) : (
                a.salon.address
              )}
            </span>
          </div>
        )}
        <div className="kv">
          <span>Стоимость</span>
          <span>{formatPrice(a.price, a.price_is_from)}</span>
        </div>

        {scope === "upcoming" && a.can_change && (
          <div className="btn-row" style={{ marginTop: 12 }}>
            <button className="btn secondary small" onClick={() => navigate(`/reschedule/${a.id}`)}>
              Перенести
            </button>
            <button className="btn danger small" disabled={cancel.isPending} onClick={onCancel}>
              Отменить
            </button>
          </div>
        )}
        {scope === "upcoming" && !a.can_change && (
          <div className="hint" style={{ marginTop: 10 }}>
            Отменить или перенести запись онлайн можно не позже чем за{" "}
            {a.salon.cancel_deadline_hours} ч. Позвоните в салон
            {a.salon.phone && (
              <>
                : <a href={`tel:${a.salon.phone}`}>{prettyPhone(a.salon.phone)}</a>
              </>
            )}
            .
          </div>
        )}
        {scope === "past" && (
          <button
            className="btn secondary small"
            style={{ marginTop: 12 }}
            onClick={() => navigate(`/s/${a.salon.slug}`)}
          >
            Записаться снова
          </button>
        )}
      </div>
    </Section>
  );
}

export function MyAppointmentsPage() {
  useBack("/");
  const [scope, setScope] = useState<Scope>("upcoming");
  const list = useQuery({
    queryKey: ["my-appointments", scope],
    queryFn: () => api.get<ClientAppointment[]>(`/me/appointments?scope=${scope}`),
  });

  return (
    <div className="page">
      <div className="page-title">Мои записи</div>
      <div className="tabs">
        <button className={scope === "upcoming" ? "active" : ""} onClick={() => setScope("upcoming")}>
          Предстоящие
        </button>
        <button className={scope === "past" ? "active" : ""} onClick={() => setScope("past")}>
          Прошедшие
        </button>
      </div>
      {list.isLoading && <Spinner />}
      {list.isError && <ErrorView error={list.error} onRetry={() => list.refetch()} />}
      {list.data?.length === 0 && (
        <Empty>{scope === "upcoming" ? "Предстоящих записей нет" : "Здесь появится история визитов"}</Empty>
      )}
      {list.data?.map((a) => <AppointmentCard key={a.id} a={a} scope={scope} />)}
    </div>
  );
}
