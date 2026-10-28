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
export const TREATMENT_PRESETS = ["продолжить", "по листу назначения"];

/** Text that is carried over from yesterday. Measurements are never copied. */
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
