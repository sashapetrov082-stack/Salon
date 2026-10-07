import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import type { ClientAppointment } from "../../api/types";
import { Avatar, Empty, ErrorView, Row, Section, Spinner } from "../../components/ui";
import { formatRelative } from "../../lib/format";
import { useMe } from "../../lib/hooks";

export function HomePage() {
  const navigate = useNavigate();
  const me = useMe();
  const upcoming = useQuery({
    queryKey: ["my-appointments", "upcoming"],
    queryFn: () => api.get<ClientAppointment[]>("/me/appointments?scope=upcoming"),
  });

  if (me.isLoading) return <Spinner />;
  if (me.isError) return <ErrorView error={me.error} onRetry={() => me.refetch()} />;
  const data = me.data!;

  return (
    <div className="page">
      <div className="page-title">
        {data.first_name ? `Здравствуйте, ${data.first_name}!` : "Здравствуйте!"}
      </div>

      {data.is_staff && (
        <Section>
          <Row
            left={<span style={{ fontSize: 22 }}>💼</span>}
            title="Кабинет"
            sub={data.staff_salons.map((s) => s.salon_name).join(", ")}
            chevron
            onClick={() =>
              navigate(
                data.staff_salons.length === 1
                  ? `/manage/${data.staff_salons[0].salon_id}`
                  : "/manage",
              )
            }
          />
        </Section>
      )}

      <Section
        title={
          <span style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Ближайшие записи</span>
            <button className="link-btn" onClick={() => navigate("/appointments")}>
              Все записи
            </button>
          </span>
        }
      >
        {upcoming.isLoading && <Spinner />}
        {upcoming.isError && <ErrorView error={upcoming.error} />}
        {upcoming.data?.length === 0 && <Empty>Предстоящих записей нет</Empty>}
        {upcoming.data?.slice(0, 3).map((a) => (
          <Row
            key={a.id}
            title={a.service.name}
            sub={`${a.salon.name} · ${a.staff.display_name}`}
            side={formatRelative(a.starts_at, a.salon.timezone)}
            onClick={() => navigate("/appointments")}
          />
        ))}
      </Section>

      {data.visited_salons.length > 0 && (
        <Section title="Мои салоны">
          {data.visited_salons.map((s) => (
            <Row
              key={s.id}
              left={<Avatar url={s.logo_url} name={s.name} />}
              title={s.name}
              sub={s.address}
              chevron
              onClick={() => navigate(`/s/${s.slug}`)}
            />
          ))}
        </Section>
      )}

      {data.visited_salons.length === 0 && !data.is_staff && (
        <p className="hint center" style={{ margin: "24px 16px" }}>
          Чтобы записаться, откройте ссылку на запись, которую прислал ваш салон.
        </p>
      )}
    </div>
  );
}
