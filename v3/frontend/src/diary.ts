import { DiaryData, EyeVision, Vision } from "./api";

/** Vis status options, exactly as in 2.9.x. */
export const VIS_STATUSES = [
  "пусто",
  "с коррекцией",
  "n.k. (не коррег.)",
  "счет пальцев у лица",
  "движ. руки у лица",
  "pr. certa",
  "pr. incerta",
  "(ноль)",
  "анофтальм",
  "эксцентрично",
];
export const WITH_CORRECTION = "с коррекцией";
export const GENERAL_STATES = ["удовлетворительное", "средней тяжести", "тяжёлое"];
/** The colour of a general state: green, amber, red. */
export const stateTone = (s: string) =>
  s === "тяжёлое" || s === "тяжелое" ? " sev-bad" : s === "средней тяжести" ? " sev-mid" : s === "удовлетворительное" ? " sev-ok" : "";
export const TREATMENT_PRESETS = ["продолжить", "по листу назначения"];

/** Text that is carried over from yesterday by «Скопировать вчерашний». Measurements: see fillYesterday. */
export const COPIED_FIELDS = ["general_state", "complaints", "od_text", "os_text", "ou_text", "treatment"] as const;

export function emptyDiary(date: string): DiaryData {
  return {
    date,
    time: "",
    bp: "",
    hr: "",
    pulse: "",
    general_state: "удовлетворительное",
    complaints: "",
    vis_od: "",
    vis_os: "",
    vis_correction_od: "пусто",
    vis_correction_os: "пусто",
    vis_od_corr: "",
    vis_os_corr: "",
    vis_od_result: "",
    vis_os_result: "",
    vgd_od: "",
    vgd_os: "",
    od_text: "",
    os_text: "",
    ou_text: "",
    treatment: "",
    discharge_note: "",
    basis: {},
  };
}

/** A new diary for `date` filled with yesterday's text; the Vis status (n.k. ...) is kept, values are not. */
export function copyFrom(prev: DiaryData, date: string): DiaryData {
  const d = emptyDiary(date);
  for (const k of COPIED_FIELDS) d[k] = prev[k] ?? "";
  d.basis = prev.basis ?? {};
  for (const eye of ["od", "os"] as const) {
    const status = prev[`vis_correction_${eye}`];
    if (status && status !== WITH_CORRECTION) d[`vis_correction_${eye}`] = status;
  }
  return d;
}

function statusText(s: string): string {
  if (!s || s === "пусто" || s === WITH_CORRECTION) return "";
  return s === "n.k. (не коррег.)" ? "n.k." : s;
}

function diopters(s: string): string {
  const t = s.trim();
  if (!t || /(d|дптр)$/i.test(t)) return t;
  return `${t} D`;
}

/** Same normalization as the server uses for display. */
export function toVision(d: DiaryData): Vision | null {
  const eye = (e: "od" | "os"): EyeVision => {
    const corrected = d[`vis_correction_${e}`] === WITH_CORRECTION;
    return {
      vis: d[`vis_${e}`].trim(),
      status: statusText(d[`vis_correction_${e}`]),
      corr: corrected ? diopters(d[`vis_${e}_corr`]) : "",
      result: corrected ? d[`vis_${e}_result`].trim() : "",
      iop: d[`vgd_${e}`].trim(),
    };
  };
  const v = { od: eye("od"), os: eye("os") };
  return Object.values(v).some((e) => Object.values(e).some(Boolean)) ? v : null;
}

const BASIS_LABELS: Record<string, string> = {
  angio_retino: "Ангиоретинопротектор", metabolism: "Для улучшения обмена веществ", desensitization: "Десенсибилизанты",
  antibiotics: "Антибиотики", angioprotectors: "Ангиопротекторы", myotics: "Миотики", biostimulators: "Биостимуляторы",
  vasodilators: "Сосудорасширяющие", analgesics: "Анальгетики", antiaggregants: "Антиагреганты",
  antifungal: "Противогрибковые", mydriatics: "Мидриатики", k_sparing: "К-сберегающий", anesthetics: "Анестетики",
  hypoglycemic: "Сахоропонижающие", hypotensive: "Гипотензивное", diuretic: "Мочегонное",
  antithrombotic: "Антитромбической цели",
};

export function basisLines(basis: DiaryData["basis"]): string[] {
  return Object.entries(basis ?? {}).flatMap(([key, item]) => {
    const values = [...(item.selected ?? []).filter((x) => x.trim())];
    if (item.note?.trim()) values.push(`прим.: ${item.note.trim()}`);
    return values.length ? [`${BASIS_LABELS[key] ?? key}: ${values.join(", ")}`] : [];
  });
}

export function hasMeasurements(d: DiaryData): boolean {
  return Boolean(d.vis_od || d.vis_os || d.vgd_od || d.vgd_os);
}

/** Measurements taken over from the previous diary. They are filled in at once (changing a number is quicker
 *  than typing it), but stay marked «как вчера» until the doctor changes them or says today is the same, and
 *  saving asks about any still marked — so a value nobody measured today is never saved unnoticed. */
export const MEASUREMENTS = ["bp", "hr", "pulse", "vis_od", "vis_os", "vis_correction_od", "vis_correction_os",
  "vis_od_corr", "vis_os_corr", "vis_od_result", "vis_os_result", "vgd_od", "vgd_os"] as const;
export type Measurement = (typeof MEASUREMENTS)[number];

const MEASUREMENT_NAMES: Record<Measurement, string> = {
  bp: "АД", hr: "ЧСС", pulse: "пульс", vis_od: "Vis OD", vis_os: "Vis OS",
  // The status and the correction are part of the eye's Vis: one name for all of them.
  vis_correction_od: "Vis OD", vis_correction_os: "Vis OS", vis_od_corr: "Vis OD", vis_os_corr: "Vis OS",
  vis_od_result: "Vis OD", vis_os_result: "Vis OS", vgd_od: "ВГД OD", vgd_os: "ВГД OS",
};

const blank = (v: string | undefined) => !v || v === "пусто";

/** Empty measurement fields of `form` get the previous diary's values; returns which were filled. */
export function fillYesterday(form: DiaryData, prev: DiaryData): { form: DiaryData; keys: Measurement[] } {
  const next = { ...form };
  const keys: Measurement[] = [];
  for (const k of MEASUREMENTS) {
    if (!blank(prev[k]) && blank(form[k])) {
      next[k] = prev[k];
      keys.push(k);
    }
  }
  return { form: next, keys };
}

/** Of the filled-in fields, those still as yesterday (not changed today). */
export const stillYesterday = (form: DiaryData, prev: DiaryData | undefined, keys: Measurement[]) =>
  prev ? keys.filter((k) => form[k] === prev[k]) : [];

export function yesterdayQuestion(keys: Measurement[], who = ""): string {
  return `${who}как вчера, сегодня не изменены: ${[...new Set(keys.map((k) => MEASUREMENT_NAMES[k]))].join(", ")}.\n\n`
    + "Сохранить так? «Отмена» — вернуться и ввести сегодняшние.";
}
