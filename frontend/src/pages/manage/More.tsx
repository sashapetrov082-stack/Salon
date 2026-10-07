import { useNavigate } from "react-router-dom";
import { Row, Section } from "../../components/ui";
import { useManage } from "./context";

export function MorePage() {
  const { base, salon } = useManage();
  const navigate = useNavigate();
  return (
    <div className="page">
      <div className="page-title">{salon.name}</div>
      <Section>
        <Row left={<span>💅</span>} title="Услуги" sub="Категории, цены, длительность" chevron onClick={() => navigate(`${base}/services`)} />
        <Row left={<span>👩‍🎨</span>} title="Сотрудники" sub="Мастера, приглашения, услуги мастеров" chevron onClick={() => navigate(`${base}/staff`)} />
        <Row left={<span>🏠</span>} title="Салон" sub="Витрина, фото, параметры записи" chevron onClick={() => navigate(`${base}/salon`)} />
      </Section>
      <Section>
        <Row left={<span>↩️</span>} title="Клиентский режим" chevron onClick={() => navigate("/")} />
      </Section>
    </div>
  );
}
