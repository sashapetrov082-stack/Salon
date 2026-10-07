import enum


class StaffRole(enum.StrEnum):
    owner = "owner"
    admin = "admin"
    master = "master"


ADMIN_ROLES = (StaffRole.owner, StaffRole.admin)


class AppointmentStatus(enum.StrEnum):
    booked = "booked"
    confirmed = "confirmed"
    completed = "completed"
    cancelled_by_client = "cancelled_by_client"
    cancelled_by_salon = "cancelled_by_salon"
    no_show = "no_show"


ACTIVE_STATUSES = (AppointmentStatus.booked, AppointmentStatus.confirmed)


class AppointmentSource(enum.StrEnum):
    client_app = "client_app"
    manual = "manual"


class NotificationKind(enum.StrEnum):
    reminder_24h = "reminder_24h"
    reminder_2h = "reminder_2h"
    staff_new = "staff_new"
    staff_cancelled = "staff_cancelled"
    staff_rescheduled = "staff_rescheduled"
    client_booked = "client_booked"
    client_cancelled_by_salon = "client_cancelled_by_salon"


class NotificationStatus(enum.StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"
