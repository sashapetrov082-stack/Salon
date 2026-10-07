import { Navigate, useNavigate } from "react-router-dom";
import { ErrorView, Row, Section, Spinner } from "../../components/ui";
import { useBack, useMe } from "../../lib/hooks";

const ROLE_LABELS = { owner: "Владелец", admin: "Администратор", master: "Мастер" } as const;

export function ManagePicker() {
  const me = useMe();
  const navigate = useNavigate();
  useBack("/");
  if (me.isLoading) return <Spinner />;
  if (me.isError) return <ErrorView error={me.error} />;
  const salons = me.data!.staff_salons;
  if (salons.length === 1) return <Navigate to={`/manage/${salons[0].salon_id}`} replace />;
  return (
    <div className="page">
      <div className="page-title">Кабинет</div>
      {salons.length === 0 && <ErrorView error={new Error()} />}
      <Section>
        {salons.map((s) => (
          <Row
            key={s.salon_id}
            title={s.salon_name}
            sub={ROLE_LABELS[s.role]}
            chevron
            onClick={() => navigate(`/manage/${s.salon_id}`)}
          />
        ))}
      </Section>
    </div>
  );
}

export { ROLE_LABELS };
