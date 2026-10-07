import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Avatar, Empty, ErrorView, Row, Section, Spinner } from "../../components/ui";
import { formatDuration, formatPrice, formatRelative } from "../../lib/format";
import { useBack, useNumberParam, useSalon, useStaff } from "../../lib/hooks";
import { haptic } from "../../telegram/webapp";

export function MastersPage() {
  const { slug = "" } = useParams();
  const [params] = useSearchParams();
  const serviceId = useNumberParam(params, "service");
  const navigate = useNavigate();
  useBack(`/s/${slug}/start`);
  const salon = useSalon(slug);
  const staff = useStaff(slug, serviceId);

  if (staff.isLoading || salon.isLoading) return <Spinner />;
  if (staff.isError) return <ErrorView error={staff.error} onRetry={() => staff.refetch()} />;
  const tz = salon.data?.timezone ?? "Europe/Moscow";

  const choose = (staffId: number | null) => {
    haptic.select();
    if (serviceId) {
      navigate(`/s/${slug}/time?service=${serviceId}&staff=${staffId ?? "any"}`);
    } else {
      navigate(`/s/${slug}/services?staff=${staffId}`);
    }
  };

  const list = staff.data ?? [];
  return (
    <div className="page">
      <div className="page-title">Мастер</div>
      {list.length === 0 && <Empty icon="👩‍🎨">Нет мастеров для записи</Empty>}
      {list.length > 0 && (
        <Section>
          {serviceId && (
            <Row
              left={<div className="avatar">✨</div>}
              title="Любой мастер"
              sub="Подберём свободного мастера на удобное время"
              chevron
              onClick={() => choose(null)}
            />
          )}
          {list.map((s) => (
            <Row
              key={s.id}
              left={<Avatar url={s.photo_url} name={s.display_name} />}
              title={s.display_name}
              sub={
                <>
                  {s.description && <div>{s.description}</div>}
                  <div>
                    {s.nearest_slot
                      ? `Ближайшее свободное: ${formatRelative(s.nearest_slot, tz)}`
                      : "Нет свободного времени в ближайшие 2 недели"}
                  </div>
                </>
              }
              side={
                s.price !== null ? (
                  <>
                    <div>{formatPrice(s.price, s.price_is_from)}</div>
                    {s.duration_min && <div className="hint">{formatDuration(s.duration_min)}</div>}
                  </>
                ) : undefined
              }
              onClick={() => choose(s.id)}
            />
          ))}
        </Section>
      )}
    </div>
  );
}
