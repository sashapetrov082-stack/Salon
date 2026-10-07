import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Empty, ErrorView, Row, Section, Spinner } from "../../components/ui";
import { formatDuration, formatPrice } from "../../lib/format";
import { useBack, useNumberParam, useServices, useStaff } from "../../lib/hooks";
import { haptic } from "../../telegram/webapp";

export function ServicesPage() {
  const { slug = "" } = useParams();
  const [params] = useSearchParams();
  const staffId = useNumberParam(params, "staff");
  const navigate = useNavigate();
  useBack(`/s/${slug}/start`);
  const services = useServices(slug);
  const staff = useStaff(slug, null);

  if (services.isLoading || (staffId && staff.isLoading)) return <Spinner />;
  if (services.isError) return <ErrorView error={services.error} onRetry={() => services.refetch()} />;

  const master = staffId ? staff.data?.find((s) => s.id === staffId) : undefined;
  const allowed = master ? new Set(master.service_ids) : null;
  const categories = (services.data ?? [])
    .map((c) => ({ ...c, services: c.services.filter((s) => !allowed || allowed.has(s.id)) }))
    .filter((c) => c.services.length > 0);

  const choose = (serviceId: number) => {
    haptic.select();
    if (staffId) navigate(`/s/${slug}/time?service=${serviceId}&staff=${staffId}`);
    else navigate(`/s/${slug}/masters?service=${serviceId}`);
  };

  return (
    <div className="page">
      <div className="page-title">Услуги</div>
      {master && <p className="hint" style={{ margin: "-6px 4px 8px" }}>Мастер: {master.display_name}</p>}
      {categories.length === 0 && <Empty icon="✂️">Пока нет услуг для онлайн-записи</Empty>}
      {categories.map((c) => (
        <Section key={c.id} title={c.name}>
          {c.services.map((s) => (
            <Row
              key={s.id}
              title={s.name}
              sub={
                <>
                  {formatDuration(s.duration_min)}
                  {s.description ? ` · ${s.description}` : ""}
                </>
              }
              side={formatPrice(s.price, s.price_is_from)}
              onClick={() => choose(s.id)}
            />
          ))}
        </Section>
      ))}
    </div>
  );
}
