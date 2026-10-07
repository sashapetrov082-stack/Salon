import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { ClientAppointment } from "../../api/types";
import { ErrorView, Section, Spinner } from "../../components/ui";
import { formatDateTime } from "../../lib/format";
import { useMainButton } from "../../telegram/webapp";
import { BookingSummary } from "./DateTime";

export function SuccessPage() {
  const { id = "", slug = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const initial = location.state as ClientAppointment | null;
  const appt = useQuery({
    queryKey: ["my-appointment", id],
    queryFn: () => api.get<ClientAppointment>(`/me/appointments/${id}`),
    initialData: initial ?? undefined,
  });
  useMainButton({ text: "Мои записи", onClick: () => navigate("/appointments", { replace: true }) });

  if (appt.isLoading) return <Spinner />;
  if (appt.isError) return <ErrorView error={appt.error} />;
  const a = appt.data!;
  return (
    <div className="page">
      <div className="empty" style={{ paddingBottom: 8 }}>
        <div className="big">✅</div>
        <div className="page-title" style={{ margin: 0 }}>
          Вы записаны!
        </div>
        <div className="hint" style={{ marginTop: 6 }}>
          Напомним о визите в Telegram за сутки и за 2 часа.
        </div>
      </div>
      <BookingSummary
        serviceName={a.service.name}
        price={a.price}
        priceIsFrom={a.price_is_from}
        duration={a.service.duration_min}
        master={a.staff.display_name}
        when={formatDateTime(a.starts_at, a.salon.timezone)}
      />
      <Section pad>
        <div className="title" style={{ fontWeight: 600 }}>{a.salon.name}</div>
        {a.salon.address && <div className="muted">{a.salon.address}</div>}
      </Section>
      <button className="btn secondary block" onClick={() => navigate(`/s/${slug}`, { replace: true })}>
        На страницу салона
      </button>
    </div>
  );
}
