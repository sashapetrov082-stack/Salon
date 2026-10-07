// Даты и время всегда показываем в часовом поясе салона.

const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const WEEKDAYS_MON = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
const MONTHS_GEN = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];
const MONTHS = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];

export { MONTHS, WEEKDAYS_MON };

interface Parts {
  year: number;
  month: number; // 1..12
  day: number;
  hour: number;
  minute: number;
}

const partsCache = new Map<string, Intl.DateTimeFormat>();

function formatter(tz: string): Intl.DateTimeFormat {
  let f = partsCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
      hourCycle: "h23",
    });
    partsCache.set(tz, f);
  }
  return f;
}

export function zonedParts(date: Date, tz: string): Parts {
  const out: Record<string, number> = {};
  for (const p of formatter(tz).formatToParts(date)) {
    if (p.type !== "literal") out[p.type] = Number(p.value);
  }
  return {
    year: out.year,
    month: out.month,
    day: out.day,
    hour: out.hour === 24 ? 0 : out.hour,
    minute: out.minute,
  };
}

const pad = (n: number) => String(n).padStart(2, "0");

/** «YYYY-MM-DD» в поясе салона */
export function dateKey(date: Date | string, tz: string): string {
  const p = zonedParts(typeof date === "string" ? new Date(date) : date, tz);
  return `${p.year}-${pad(p.month)}-${pad(p.day)}`;
}

/** «14:30» */
export function formatTime(date: Date | string, tz: string): string {
  const p = zonedParts(typeof date === "string" ? new Date(date) : date, tz);
  return `${pad(p.hour)}:${pad(p.minute)}`;
}

/** Дата «YYYY-MM-DD» → «пт, 9 октября» (без учёта пояса — это уже локальная дата салона) */
export function formatDateKey(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${WEEKDAYS[wd]}, ${d} ${MONTHS_GEN[m - 1]}`;
}

/** «пт, 9 октября» */
export function formatDate(date: Date | string, tz: string): string {
  return formatDateKey(dateKey(date, tz));
}

/** «пт, 9 октября, 14:30» */
export function formatDateTime(date: Date | string, tz: string): string {
  return `${formatDate(date, tz)}, ${formatTime(date, tz)}`;
}

/** «сегодня 11:30» / «завтра 11:30» / «пт, 9 октября, 11:30» */
export function formatRelative(date: Date | string, tz: string, now = new Date()): string {
  const key = dateKey(date, tz);
  const today = dateKey(now, tz);
  if (key === today) return `сегодня ${formatTime(date, tz)}`;
  if (key === addDays(today, 1)) return `завтра ${formatTime(date, tz)}`;
  return formatDateTime(date, tz);
}

export function formatPrice(price: number, isFrom = false): string {
  const body = `${price.toLocaleString("ru-RU").replace(/\s/g, " ")} ₽`;
  return isFrom ? `от ${body}` : body;
}

export function formatDuration(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h && m) return `${h} ч ${m} мин`;
  if (h) return `${h} ч`;
  return `${m} мин`;
}

/** Добавить дни к «YYYY-MM-DD» */
export function addDays(key: string, days: number): string {
  const [y, m, d] = key.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + days));
  return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`;
}

/** День недели «YYYY-MM-DD»: 0=пн..6=вс */
export function weekdayOf(key: string): number {
  const [y, m, d] = key.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

export function startOfWeek(key: string): string {
  return addDays(key, -weekdayOf(key));
}

/** Локальные дата+время салона → Date (UTC-момент). */
export function zonedToDate(key: string, time: string, tz: string): Date {
  const [y, m, d] = key.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const asUtc = Date.UTC(y, m - 1, d, hh, mm);
  const offset = (ts: number) => {
    const p = zonedParts(new Date(ts), tz);
    return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) - ts;
  };
  let ts = asUtc - offset(asUtc);
  ts = asUtc - offset(ts);
  return new Date(ts);
}

/** Минуты от полуночи салона */
export function minutesOfDay(date: Date | string, tz: string): number {
  const p = zonedParts(typeof date === "string" ? new Date(date) : date, tz);
  return p.hour * 60 + p.minute;
}

export function hhmm(time: string): string {
  return time.slice(0, 5);
}

export const STATUS_LABELS: Record<string, string> = {
  booked: "Записан",
  confirmed: "Подтвердил",
  completed: "Пришёл",
  cancelled_by_client: "Отменил клиент",
  cancelled_by_salon: "Отменено салоном",
  no_show: "Не пришёл",
};

// ---- Телефон ----

/** Цифры номера в формате 7XXXXXXXXXX (для РФ) */
export function phoneDigits(raw: string): string {
  let d = raw.replace(/\D/g, "");
  if (d.length === 11 && d[0] === "8") d = "7" + d.slice(1);
  if (d.length === 10 && d[0] === "9") d = "7" + d;
  return d;
}

/** Маска «+7 (916) 123-45-67» для ввода */
export function maskPhone(raw: string): string {
  let d = raw.replace(/\D/g, "");
  if (d.startsWith("8")) d = "7" + d.slice(1);
  if (!d.startsWith("7")) d = "7" + d;
  d = d.slice(0, 11);
  const r = d.slice(1);
  let out = "+7";
  if (r.length) out += ` (${r.slice(0, 3)}`;
  if (r.length >= 3) out += ")";
  if (r.length > 3) out += ` ${r.slice(3, 6)}`;
  if (r.length > 6) out += `-${r.slice(6, 8)}`;
  if (r.length > 8) out += `-${r.slice(8, 10)}`;
  return out;
}

export function isPhoneComplete(raw: string): boolean {
  return phoneDigits(raw).length === 11;
}

/** «+79161234567» → «+7 916 123-45-67» */
export function prettyPhone(phone: string): string {
  const d = phone.replace(/\D/g, "");
  if (d.length === 11 && d[0] === "7") {
    return `+7 ${d.slice(1, 4)} ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9)}`;
  }
  return phone;
}

export function pluralRu(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}
