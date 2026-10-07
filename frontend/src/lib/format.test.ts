import { describe, expect, it } from "vitest";
import {
  addDays,
  dateKey,
  formatDate,
  formatDateTime,
  formatDuration,
  formatPrice,
  formatRelative,
  formatTime,
  maskPhone,
  phoneDigits,
  pluralRu,
  prettyPhone,
  startOfWeek,
  weekdayOf,
  zonedToDate,
} from "./format";

const MSK = "Europe/Moscow";

describe("format", () => {
  it("formats dates in salon timezone", () => {
    const d = "2026-10-09T11:30:00Z"; // 14:30 по Москве
    expect(formatDate(d, MSK)).toBe("пт, 9 октября");
    expect(formatTime(d, MSK)).toBe("14:30");
    expect(formatDateTime(d, MSK)).toBe("пт, 9 октября, 14:30");
    expect(dateKey("2026-10-09T22:30:00Z", MSK)).toBe("2026-10-10");
    expect(formatTime(d, "Asia/Yekaterinburg")).toBe("16:30");
  });

  it("relative days", () => {
    const now = new Date("2026-10-09T06:00:00Z");
    expect(formatRelative("2026-10-09T08:00:00Z", MSK, now)).toBe("сегодня 11:00");
    expect(formatRelative("2026-10-10T08:30:00Z", MSK, now)).toBe("завтра 11:30");
  });

  it("prices and durations", () => {
    expect(formatPrice(1500)).toBe("1 500 ₽");
    expect(formatPrice(1500, true)).toBe("от 1 500 ₽");
    expect(formatDuration(90)).toBe("1 ч 30 мин");
    expect(formatDuration(60)).toBe("1 ч");
    expect(formatDuration(45)).toBe("45 мин");
  });

  it("date arithmetic", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(weekdayOf("2026-10-12")).toBe(0);
    expect(weekdayOf("2026-10-18")).toBe(6);
    expect(startOfWeek("2026-10-15")).toBe("2026-10-12");
  });

  it("zoned local time to instant", () => {
    expect(zonedToDate("2026-10-09", "14:30", MSK).toISOString()).toBe("2026-10-09T11:30:00.000Z");
    // переход на зимнее время в Берлине: 25 октября 2026
    expect(zonedToDate("2026-10-26", "10:00", "Europe/Berlin").toISOString()).toBe(
      "2026-10-26T09:00:00.000Z",
    );
    expect(zonedToDate("2026-10-24", "10:00", "Europe/Berlin").toISOString()).toBe(
      "2026-10-24T08:00:00.000Z",
    );
  });

  it("phones", () => {
    expect(maskPhone("89161234567")).toBe("+7 (916) 123-45-67");
    expect(maskPhone("916")).toBe("+7 (916)");
    expect(maskPhone("")).toBe("+7");
    expect(phoneDigits("+7 (916) 123-45-67")).toBe("79161234567");
    expect(prettyPhone("+79161234567")).toBe("+7 916 123-45-67");
  });

  it("plural", () => {
    expect(pluralRu(1, "запись", "записи", "записей")).toBe("запись");
    expect(pluralRu(3, "запись", "записи", "записей")).toBe("записи");
    expect(pluralRu(11, "запись", "записи", "записей")).toBe("записей");
  });
});
