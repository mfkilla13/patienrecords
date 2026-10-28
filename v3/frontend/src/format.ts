/** Local date as "2026-10-29". */
export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** "2026-10-29" -> "Среда, 29 октября" */
export function longToday(iso: string): string {
  const text = new Intl.DateTimeFormat("ru-RU", { weekday: "long", day: "numeric", month: "long" }).format(
    new Date(iso + "T00:00"),
  );
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "2026-04-21T11:46" -> "21.04" */
export function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}`;
}

const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

/** "2026-04-21T11:46" -> { day: "21.04, вт", time: "11:46" } */
export function recordDate(iso: string): { day: string; time: string } {
  const d = new Date(iso.slice(0, 10) + "T00:00");
  const time = iso.length >= 16 ? iso.slice(11, 16) : "";
  return { day: `${shortDate(iso)}, ${WEEKDAYS[d.getDay()]}`, time: time === "00:00" ? "" : time };
}

/** "2026-04-21..." -> "21.04.2026" */
export function fullDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

/** 1 запись, 2 записи, 5 записей */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export function initials(surname: string, name: string): string {
  return (surname.charAt(0) + name.charAt(0)).toUpperCase();
}
