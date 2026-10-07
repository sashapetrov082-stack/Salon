import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api, qs } from "../../api/client";
import type { ClientDetail, ClientRow } from "../../api/types";
import { Empty, ErrorView, Field, Row, Section, Spinner, StatusBadge, toast } from "../../components/ui";
import { formatDateTime, formatPrice, prettyPhone } from "../../lib/format";
import { useBack } from "../../lib/hooks";
import { alertDialog, haptic } from "../../telegram/webapp";
import { useManage } from "./context";

export function ClientsPage() {
  const { salonId, base } = useManage();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);
  const list = useQuery({
    queryKey: ["manage", salonId, "clients", q],
    queryFn: () => api.get<ClientRow[]>(`/manage/${salonId}/clients${qs({ q })}`),
  });

  return (
    <div className="page">
      <div className="page-title">Клиенты</div>
      <Section>
        <Field label="Поиск">
          <input
            className="input"
            value={query}
            placeholder="Имя или телефон"
            onChange={(e) => setQuery(e.target.value)}
          />
        </Field>
      </Section>
      {list.isLoading && <Spinner />}
      {list.isError && <ErrorView error={list.error} onRetry={() => list.refetch()} />}
      {list.data?.length === 0 && <Empty icon="👥">{q ? "Никого не нашли" : "Клиентов пока нет"}</Empty>}
      {!!list.data?.length && (
        <Section>
          {list.data.map((c) => (
            <Row
              key={c.id}
              title={c.name}
              sub={prettyPhone(c.phone)}
              side={`${c.visits_count} виз.`}
              chevron
              onClick={() => navigate(`${base}/clients/${c.id}`)}
            />
          ))}
        </Section>
      )}
    </div>
  );
}

export function ClientCardPage() {
  const { id = "" } = useParams();
  const { salonId, salon, base } = useManage();
  const tz = salon.timezone;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  useBack(`${base}/clients`);
  const client = useQuery({
    queryKey: ["manage", salonId, "client", id],
    queryFn: () => api.get<ClientDetail>(`/manage/${salonId}/clients/${id}`),
  });
  const [notes, setNotes] = useState<string | null>(null);
  useEffect(() => {
    if (client.data && notes === null) setNotes(client.data.notes ?? "");
  }, [client.data, notes]);

  const save = useMutation({
    mutationFn: () => api.patch<ClientDetail>(`/manage/${salonId}/clients/${id}`, { notes }),
    onSuccess: (data) => {
      haptic.success();
      queryClient.setQueryData(["manage", salonId, "client", id], data);
      toast("Заметка сохранена");
    },
    onError: (e) => alertDialog(e instanceof ApiError ? e.message : "Не удалось сохранить"),
  });

  if (client.isLoading) return <Spinner />;
  if (client.isError) return <ErrorView error={client.error} />;
  const c = client.data!;

  return (
    <div className="page">
      <div className="page-title">{c.name}</div>
      <Section>
        <Row
          title={prettyPhone(c.phone)}
          sub={c.has_telegram ? "Записывается через Telegram" : "Добавлен вручную"}
          side="Позвонить"
          onClick={() => {
            window.location.href = `tel:${c.phone}`;
          }}
        />
        <div className="row static">
          <div className="row-main">
            <div className="split">
              <div>
                <div className="hint">Визитов</div>
                <div style={{ fontSize: 20, fontWeight: 600 }}>{c.visits_count}</div>
              </div>
              <div>
                <div className="hint">Неявок</div>
                <div style={{ fontSize: 20, fontWeight: 600, color: c.no_show_count ? "var(--destructive)" : undefined }}>
                  {c.no_show_count}
                </div>
              </div>
            </div>
          </div>
        </div>
      </Section>

      <Section title="Заметка">
        <Field label="Видна только сотрудникам салона">
          <textarea
            className="input"
            rows={3}
            maxLength={2000}
            value={notes ?? ""}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Field>
        {notes !== (c.notes ?? "") && (
          <div className="section-pad">
            <button className="btn block" disabled={save.isPending} onClick={() => save.mutate()}>
              Сохранить заметку
            </button>
          </div>
        )}
      </Section>

      <Section title="История визитов">
        {c.appointments.length === 0 && <div className="row static hint">Пока нет записей</div>}
        {c.appointments.map((a) => (
          <Row
            key={a.id}
            title={a.service.name}
            sub={`${formatDateTime(a.starts_at, tz)} · ${a.staff_name} · ${formatPrice(a.price, a.price_is_from)}`}
            side={<StatusBadge status={a.status} />}
            onClick={() => navigate(`${base}/appointments/${a.id}`)}
          />
        ))}
      </Section>
    </div>
  );
}
