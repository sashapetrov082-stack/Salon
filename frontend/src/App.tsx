import { useEffect, useRef } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { FallbackMainButton, ToastHost } from "./components/ui";
import { ConfirmPage } from "./pages/client/Confirm";
import { DateTimePage } from "./pages/client/DateTime";
import { HomePage } from "./pages/client/Home";
import { MastersPage } from "./pages/client/Masters";
import { MyAppointmentsPage } from "./pages/client/MyAppointments";
import { ReschedulePage } from "./pages/client/Reschedule";
import { SalonPage } from "./pages/client/Salon";
import { ScenarioPage } from "./pages/client/Scenario";
import { ServicesPage } from "./pages/client/Services";
import { SuccessPage } from "./pages/client/Success";
import { ManageApp } from "./pages/manage/ManageApp";
import { ManagePicker } from "./pages/manage/ManagePicker";
import { getStartParam } from "./telegram/webapp";

/** Маршрутизация по start_param при запуске: s_<slug>, r_<id>, m_<salon_id>. */
function startRoute(param: string | null): string | null {
  if (!param) return null;
  let m = /^s_([a-z0-9-]+)$/.exec(param);
  if (m) return `/s/${m[1]}`;
  m = /^r_(\d+)$/.exec(param);
  if (m) return `/reschedule/${m[1]}`;
  m = /^m_(\d+)$/.exec(param);
  if (m) return `/manage/${m[1]}`;
  return null;
}

function StartRedirect() {
  const navigate = useNavigate();
  const location = useLocation();
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    // start_param применяем только при открытии в корне приложения
    if (location.pathname !== "/") return;
    const target = startRoute(getStartParam());
    if (target) navigate(target, { replace: true });
  }, [navigate, location.pathname]);
  return null;
}

export function App() {
  return (
    <>
      <StartRedirect />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/s/:slug" element={<SalonPage />} />
        <Route path="/s/:slug/start" element={<ScenarioPage />} />
        <Route path="/s/:slug/services" element={<ServicesPage />} />
        <Route path="/s/:slug/masters" element={<MastersPage />} />
        <Route path="/s/:slug/time" element={<DateTimePage />} />
        <Route path="/s/:slug/confirm" element={<ConfirmPage />} />
        <Route path="/s/:slug/done/:id" element={<SuccessPage />} />
        <Route path="/appointments" element={<MyAppointmentsPage />} />
        <Route path="/reschedule/:id" element={<ReschedulePage />} />
        <Route path="/manage" element={<ManagePicker />} />
        <Route path="/manage/:salonId/*" element={<ManageApp />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <FallbackMainButton />
      <ToastHost />
    </>
  );
}
