import { useNavigate, useParams } from "react-router-dom";
import { Row, Section } from "../../components/ui";
import { useBack, useSalon } from "../../lib/hooks";

export function ScenarioPage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const salon = useSalon(slug);
  useBack(`/s/${slug}`);
  return (
    <div className="page">
      <div className="page-title">{salon.data?.name ?? "Запись"}</div>
      <Section>
        <Row
          left={<span style={{ fontSize: 26 }}>💇</span>}
          title="Выбрать услугу"
          sub="Сначала услуга, затем мастер и время"
          chevron
          onClick={() => navigate(`/s/${slug}/services`)}
        />
        <Row
          left={<span style={{ fontSize: 26 }}>👩‍🎨</span>}
          title="Выбрать мастера"
          sub="Если вы уже знаете, к кому записаться"
          chevron
          onClick={() => navigate(`/s/${slug}/masters`)}
        />
      </Section>
    </div>
  );
}
