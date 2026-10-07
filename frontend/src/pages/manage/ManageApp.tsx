import { useQuery } from "@tanstack/react-query";
import { NavLink, Route, Routes, useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { SalonSettings } from "../../api/types";
import { Empty, ErrorView, Spinner } from "../../components/ui";
import { useMe } from "../../lib/hooks";
import { AppointmentDetailPage } from "./AppointmentDetail";
import { ClientCardPage, ClientsPage } from "./Clients";
import { ManageContext, type ManageCtx } from "./context";
import { MorePage } from "./More";
import { MySchedulePage } from "./MySchedule";
import { NewAppointmentPage } from "./NewAppointment";
import { SalonSettingsPage } from "./SalonSettings";
import { SchedulePage } from "./Schedule";
import { ServicesAdminPage } from "./ServicesAdmin";
import { StaffAdminPage, StaffEditPage } from "./StaffAdmin";

function BottomNav({ base, isAdmin }: { base: string; isAdmin: boolean }) {
  const items = [
    { to: base, label: "Расписание", ico: "🗓", end: true },
    { to: `${base}/clients`, label: "Клиенты", ico: "👥" },
    { to: `${base}/my-schedule`, label: "График", ico: "⏰" },
  ];
  if (isAdmin) items.push({ to: `${base}/more`, label: "Салон", ico: "⚙️" });
  return (
    <nav className="bottom-nav">
      {items.map((i) => (
        <NavLink key={i.to} to={i.to} end={i.end} replace>
          <span className="ico">{i.ico}</span>
          {i.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function ManageApp() {
  const { salonId: raw = "" } = useParams();
  const salonId = Number(raw);
  const me = useMe();
  const membership = me.data?.staff_salons.find((s) => s.salon_id === salonId);
  const settings = useQuery({
    queryKey: ["manage", salonId, "settings"],
    queryFn: () => api.get<SalonSettings>(`/manage/${salonId}/settings`),
    enabled: !!membership,
  });

  if (me.isLoading || settings.isLoading) return <Spinner />;
  if (me.isError) return <ErrorView error={me.error} />;
  if (!membership) {
    return (
      <div className="page">
        <Empty icon="🔒">У вас нет доступа к кабинету этого салона.</Empty>
      </div>
    );
  }
  if (settings.isError) return <ErrorView error={settings.error} onRetry={() => settings.refetch()} />;

  const isAdmin = membership.role === "owner" || membership.role === "admin";
  const ctx: ManageCtx = {
    salonId,
    staffId: membership.staff_id,
    role: membership.role,
    isAdmin,
    salon: settings.data!,
    base: `/manage/${salonId}`,
  };

  return (
    <ManageContext.Provider value={ctx}>
      <Routes>
        <Route index element={<SchedulePage />} />
        <Route path="appointments/new" element={<NewAppointmentPage />} />
        <Route path="appointments/:id" element={<AppointmentDetailPage />} />
        <Route path="my-schedule" element={<MySchedulePage />} />
        <Route path="clients" element={<ClientsPage />} />
        <Route path="clients/:id" element={<ClientCardPage />} />
        {isAdmin && (
          <>
            <Route path="more" element={<MorePage />} />
            <Route path="services" element={<ServicesAdminPage />} />
            <Route path="staff" element={<StaffAdminPage />} />
            <Route path="staff/:id" element={<StaffEditPage />} />
            <Route path="salon" element={<SalonSettingsPage />} />
          </>
        )}
      </Routes>
      <BottomNav base={ctx.base} isAdmin={isAdmin} />
    </ManageContext.Provider>
  );
}
