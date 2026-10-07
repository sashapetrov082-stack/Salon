export type AppointmentStatus =
  | "booked"
  | "confirmed"
  | "completed"
  | "cancelled_by_client"
  | "cancelled_by_salon"
  | "no_show";

export type StaffRole = "owner" | "admin" | "master";

export interface Photo {
  id: number;
  url: string;
  sort_order: number;
}

export interface SalonPublic {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  address: string | null;
  map_url: string | null;
  phone: string | null;
  cover_url: string | null;
  logo_url: string | null;
  announcement: string | null;
  timezone: string;
  slot_step_min: number;
  min_lead_time_min: number;
  booking_horizon_days: number;
  cancel_deadline_hours: number;
  is_active: boolean;
  photos: Photo[];
  client: { name: string; phone: string } | null;
}

export interface Service {
  id: number;
  category_id: number;
  name: string;
  description: string | null;
  price: number;
  price_is_from: boolean;
  duration_min: number;
}

export interface CategoryWithServices {
  id: number;
  name: string;
  services: Service[];
}

export interface StaffPublic {
  id: number;
  display_name: string;
  photo_url: string | null;
  description: string | null;
  nearest_slot: string | null;
  price: number | null;
  price_is_from: boolean;
  duration_min: number | null;
  service_ids: number[];
}

export interface DayAvailability {
  date: string;
  has_slots: boolean;
}

export interface Slot {
  starts_at: string;
  staff_id: number;
}

export interface SalonBrief {
  id: number;
  slug: string;
  name: string;
  address: string | null;
  phone: string | null;
  map_url: string | null;
  timezone: string;
  cancel_deadline_hours: number;
  logo_url: string | null;
}

export interface ClientAppointment {
  id: number;
  status: AppointmentStatus;
  starts_at: string;
  ends_at: string;
  price: number;
  price_is_from: boolean;
  comment: string | null;
  salon: SalonBrief;
  service: { id: number; name: string; duration_min: number };
  staff: { id: number; display_name: string; photo_url: string | null };
  can_change: boolean;
}

export interface Me {
  id: number;
  telegram_id: number;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
  is_staff: boolean;
  staff_salons: {
    salon_id: number;
    salon_name: string;
    salon_slug: string;
    staff_id: number;
    role: StaffRole;
  }[];
  visited_salons: {
    id: number;
    slug: string;
    name: string;
    logo_url: string | null;
    address: string | null;
  }[];
}

export interface ContactStatus {
  received: boolean;
  phone: string | null;
}

// ---- Кабинет ----

export interface ClientBrief {
  id: number;
  name: string;
  phone: string;
  visits_count: number;
  no_show_count: number;
}

export interface ManageAppointment {
  id: number;
  status: AppointmentStatus;
  source: "client_app" | "manual";
  staff_id: number;
  starts_at: string;
  ends_at: string;
  blocked_until: string;
  price: number;
  price_is_from: boolean;
  comment: string | null;
  service: { id: number; name: string };
  client: ClientBrief;
}

export interface TimeOff {
  id: number;
  staff_id: number;
  starts_at: string;
  ends_at: string;
  reason: string | null;
}

export interface StaffCalendar {
  id: number;
  display_name: string;
  photo_url: string | null;
  is_bookable: boolean;
  sort_order: number;
}

export interface CalendarData {
  appointments: ManageAppointment[];
  time_off: TimeOff[];
  staff: StaffCalendar[];
}

export interface WeeklyInterval {
  weekday: number;
  start_time: string;
  end_time: string;
}

export interface Schedule {
  work: WeeklyInterval[];
  breaks: WeeklyInterval[];
}

export interface Override {
  id: number;
  staff_id: number;
  date: string;
  is_day_off: boolean;
  start_time: string | null;
  end_time: string | null;
}

export interface Category {
  id: number;
  name: string;
  sort_order: number;
}

export interface ServiceAdmin {
  id: number;
  category_id: number;
  name: string;
  description: string | null;
  price: number;
  price_is_from: boolean;
  duration_min: number;
  buffer_after_min: number;
  is_active: boolean;
  sort_order: number;
}

export interface StaffService {
  service_id: number;
  price_override: number | null;
  duration_override_min: number | null;
}

export interface StaffAdmin {
  id: number;
  display_name: string;
  role: StaffRole;
  photo_url: string | null;
  description: string | null;
  is_bookable: boolean;
  is_active: boolean;
  sort_order: number;
  is_linked: boolean;
  telegram_username: string | null;
  services: StaffService[];
}

export interface Invite {
  token: string;
  url: string;
  expires_at: string;
}

export interface ClientRow extends ClientBrief {
  notes: string | null;
  has_telegram: boolean;
}

export interface ClientDetail extends ClientRow {
  appointments: {
    id: number;
    status: AppointmentStatus;
    starts_at: string;
    price: number;
    price_is_from: boolean;
    service: { id: number; name: string };
    staff_name: string;
  }[];
}

export interface SalonSettings {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  address: string | null;
  map_url: string | null;
  phone: string | null;
  cover_url: string | null;
  logo_url: string | null;
  announcement: string | null;
  timezone: string;
  slot_step_min: number;
  min_lead_time_min: number;
  booking_horizon_days: number;
  cancel_deadline_hours: number;
  is_active: boolean;
  booking_link: string;
  photos: Photo[];
}
