import { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { Slot } from "../../api/types";
import { SlotPicker } from "../../components/SlotPicker";
import { ErrorView, Section, Spinner } from "../../components/ui";
import { formatDuration, formatPrice } from "../../lib/format";
import { useBack, useNumberParam, useSalon, useServices, useStaff } from "../../lib/hooks";
import { useMainButton } from "../../telegram/webapp";

export function BookingSummary({
  serviceName,
  price,
  priceIsFrom,
  duration,
  master,
  when,
}: {
  serviceName: string;
  price: number;
  priceIsFrom: boolean;
  duration: number;
  master: string;
  when?: string;
}) {
  return (
    <Section>
      <div className="summary-card">
        <div className="title">{serviceName}</div>
        <div className="kv">
          <span>Мастер</span>
          <span>{master}</span>
        </div>
        {when && (
          <div className="kv">
            <span>Когда</span>
            <span>{when}</span>
          </div>
        )}
        <div className="kv">
          <span>Длительность</span>
          <span>{formatDuration(duration)}</span>
        </div>
        <div className="kv">
          <span>Стоимость</span>
          <span>{formatPrice(price, priceIsFrom)}</span>
        </div>
      </div>
    </Section>
  );
}

/** Данные о выбранной услуге и мастере для экранов записи. */
export function useBookingContext(slug: string, params: URLSearchParams) {
  const serviceId = useNumberParam(params, "service");
  const staffId = useNumberParam(params, "staff"); // null — любой мастер
  const salon = useSalon(slug);
  const services = useServices(slug);
  const staff = useStaff(slug, serviceId);
  const service = useMemo(
    () => services.data?.flatMap((c) => c.services).find((s) => s.id === serviceId),
    [services.data, serviceId],
  );
  const master = staff.data?.find((s) => s.id === staffId);
  const loading = salon.isLoading || services.isLoading || staff.isLoading;
  const error = salon.error || services.error || staff.error;
  return { serviceId, staffId, salon: salon.data, service, master, staffList: staff.data, loading, error };
}

export function DateTimePage() {
  const { slug = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  useBack(`/s/${slug}/start`);
  const ctx = useBookingContext(slug, params);
  const [slot, setSlot] = useState<Slot | null>(null);

  useMainButton({
    text: "Далее",
    visible: !!slot,
    onClick: () => {
      if (!slot) return;
      const q = new URLSearchParams(params);
      q.set("at", slot.starts_at);
      q.set("slot_staff", String(slot.staff_id));
      navigate(`/s/${slug}/confirm?${q.toString()}`);
    },
  });

  if (ctx.loading) return <Spinner />;
  if (ctx.error) return <ErrorView error={ctx.error} />;
  if (!ctx.salon || !ctx.service || !ctx.serviceId) {
    return <ErrorView error={new Error()} />;
  }
  const masterName = ctx.master?.display_name ?? "Любой мастер";
  const price = ctx.master?.price ?? ctx.service.price;
  const duration = ctx.master?.duration_min ?? ctx.service.duration_min;

  return (
    <div className="page">
      <div className="page-title">Дата и время</div>
      <BookingSummary
        serviceName={ctx.service.name}
        price={price}
        priceIsFrom={ctx.service.price_is_from}
        duration={duration}
        master={masterName}
      />
      <SlotPicker
        salon={ctx.salon}
        serviceId={ctx.serviceId}
        staffId={ctx.staffId}
        selected={slot}
        onSelect={setSlot}
      />
    </div>
  );
}
