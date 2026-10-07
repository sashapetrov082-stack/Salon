import { useNavigate, useParams } from "react-router-dom";
import { Avatar, ErrorView, Row, Section, Spinner } from "../../components/ui";
import { prettyPhone } from "../../lib/format";
import { useBack, useSalon } from "../../lib/hooks";
import { openLink, useMainButton } from "../../telegram/webapp";

export function SalonPage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const salon = useSalon(slug);
  useBack();
  useMainButton({
    text: "Записаться",
    onClick: () => navigate(`/s/${slug}/start`),
    visible: !!salon.data?.is_active,
  });

  if (salon.isLoading) return <Spinner />;
  if (salon.isError) return <ErrorView error={salon.error} onRetry={() => salon.refetch()} />;
  const s = salon.data!;

  return (
    <div className="page">
      <div
        className="cover"
        style={s.cover_url ? { backgroundImage: `url("${encodeURI(s.cover_url)}")` } : undefined}
      />
      <div className="salon-head">
        <Avatar url={s.logo_url} name={s.name} size="lg" />
        <div style={{ paddingBottom: 4 }}>
          <div className="page-title" style={{ margin: 0 }}>
            {s.name}
          </div>
        </div>
      </div>

      {!s.is_active && (
        <div className="announcement">Салон временно не принимает онлайн-записи.</div>
      )}
      {s.announcement && <div className="announcement">📣 {s.announcement}</div>}

      {s.description && (
        <Section pad>
          <div style={{ whiteSpace: "pre-line" }}>{s.description}</div>
        </Section>
      )}

      {s.photos.length > 0 && (
        <div className="gallery">
          {s.photos.map((p) => (
            <img key={p.id} src={p.url} alt="" loading="lazy" />
          ))}
        </div>
      )}

      <Section>
        {s.address && (
          <Row
            left={<span style={{ fontSize: 20 }}>📍</span>}
            title={s.address}
            side={s.map_url ? "Карта" : undefined}
            onClick={s.map_url ? () => openLink(s.map_url!) : undefined}
          />
        )}
        {s.phone && (
          <Row
            left={<span style={{ fontSize: 20 }}>📞</span>}
            title={prettyPhone(s.phone)}
            side="Позвонить"
            onClick={() => {
              window.location.href = `tel:${s.phone}`;
            }}
          />
        )}
        <Row
          left={<span style={{ fontSize: 20 }}>🗓</span>}
          title="Мои записи"
          chevron
          onClick={() => navigate("/appointments")}
        />
      </Section>

      {s.is_active && (
        <div className="btn-row" style={{ marginTop: 8 }}>
          <button className="btn" onClick={() => navigate(`/s/${slug}/start`)}>
            Записаться
          </button>
          {s.phone && (
            <a className="btn secondary" href={`tel:${s.phone}`}>
              Позвонить
            </a>
          )}
        </div>
      )}
    </div>
  );
}
