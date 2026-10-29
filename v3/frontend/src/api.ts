export type Stage = "exam" | "post_op" | "discharged";

export interface DepartmentPatient {
  caseId: string;
  number: string;
  surname: string;
  name: string;
  patronymic: string;
  age: number | null;
  diagnosis: string;
  eye: "OD" | "OS" | "OU" | null;
  admittedAt: string | null;
  day: number | null;
  stage: Stage;
  diaryToday: boolean;
  unprinted: number;
}

export interface Department {
  today: string;
  patients: DepartmentPatient[];
  summary: { beds: number | null; occupied: number; admittedToday: number; dischargedToday: number; dischargedMonth: number; issues: number };
  counts: { all: number; noDiary: number; unprinted: number; discharged: number };
}

export interface EyeVision {
  vis: string;
  status: string;
  corr: string;
  result: string;
  iop: string;
}
export interface Vision {
  od: EyeVision;
  os: EyeVision;
}

export interface RecordView {
  id: string;
  kind: "primary_exam" | "diary" | "operation_protocol" | "discharge_summary" | "plan" | "other";
  kindLabel: string;
  recordedAt: string;
  printedAt: string | null;
  vision: Vision | null;
  sections: { label: string; text: string }[];
  local: { name: string; od: string; os: string }[];
  title: string;
  hasLegacyHtml: boolean;
  editable: boolean;
  printable: boolean;
}

export interface StudyView {
  id: string;
  kind: string;
  date: string | null;
  unparsedDate: string | null;
  summary: string;
  flags?: string[];
}

export interface Step {
  key: string;
  title: string;
  sub: string;
  state: "done" | "now" | "todo";
}

export interface CaseCard {
  caseId: string;
  number: string;
  medCard: string;
  status: "active" | "discharged" | "archived";
  outcome: string;
  admittedAt: string | null;
  dischargedAt: string | null;
  day: number | null;
  patient: { surname: string; name: string; patronymic: string; dob: string | null; age: number | null; address: string };
  diagnosis: { main: string; admission: string; clinical: string; final: string; comorbid: string };
  latestVision: { at: string; eyes: Vision } | null;
  steps: Step[];
  records: RecordView[];
  studies: StudyView[];
  prescriptions: { id: string; category: string; name: string; method: string; freq: string; date_from: string | null; date_to: string | null }[];
  unprinted: number;
  printState: { sheet: number; used_mm: number; last_printed_at: string | null } | null;
}

/** Diary fields, same keys as in 2.9.x. */
export interface DiaryData {
  date: string;
  time: string;
  bp: string;
  hr: string;
  pulse: string;
  general_state: string;
  complaints: string;
  vis_od: string;
  vis_os: string;
  vis_correction_od: string;
  vis_correction_os: string;
  vis_od_corr: string;
  vis_os_corr: string;
  vis_od_result: string;
  vis_os_result: string;
  vgd_od: string;
  vgd_os: string;
  od_text: string;
  os_text: string;
  ou_text: string;
  treatment: string;
  discharge_note: string;
  basis: Record<string, { selected?: string[]; note?: string }>;
}

export interface DiaryDraft {
  previous: { recordId: string; date: string; data: DiaryData } | null;
  previousUnchanged: boolean;
  today: { recordId: string; printedAt: string | null; data: DiaryData } | null;
}

export interface RoundRow extends DiaryDraft {
  caseId: string;
  number: string;
  surname: string;
  name: string;
  patronymic: string;
  diagnosis: string;
  dayLabel: string;
  postOp: boolean;
}

export interface PrintPlan {
  state: { sheet: number; used_mm: number; last_printed_at: string | null; source: "v3" | "legacy" } | null;
  records: {
    id: string;
    kind: string;
    kindLabel: string;
    recordedAt: string;
    printedAt: string | null;
    printable: boolean;
    reason: string | null;
    summary: string;
    /** Where v3 printed it; null for unprinted records and for records printed by 2.9. */
    place: { sheet: number; startMm: number } | null;
  }[];
  suggestion: { mode: "continue" | "new"; sheet: number; startMm: number };
  doctor: string;
  lastOnSheet: string | null;
}

export type PrintMode = "continue" | "new" | "manual";
export type PrintKind = "sheet" | "copy";

export interface PrintJob {
  jobId: string;
  kind: PrintKind;
  pages: { sheet: number; insert: string; shade: number[][]; fresh: boolean }[];
  movedToNewSheet: boolean;
  newStart: { sheet: number; mm: number } | null;
  newEnd: { sheet: number; mm: number } | null;
  leftMm: number;
  newCount: number;
  reprintCount: number;
  count: number;
}

export interface Settings {
  doctor_signature: string;
  org_header: string;
  department: string;
  default_printer: string;
  beds: string;
  bed_days_plan: string;
  theme: string;
}

export interface Dictionaries {
  ophthalmic: string[];
  comorbid: string[];
  examinations: string[];
  treatment: Record<string, string[]>;
  cities: string[];
  streets: string[];
  nextNumber: string;
  channels: string[];
  residence: string[];
}

export interface PatientMatch {
  id: string;
  surname: string;
  name: string;
  patronymic: string;
  dob: string | null;
  city: string;
  street: string;
  house: string;
  residence: string;
  lastCase: { number: string; admittedAt: string | null; status: string; diagnosis: string } | null;
}

export interface AdmissionIn {
  patientId: string | null;
  surname: string;
  name: string;
  patronymic: string;
  dob: string | null;
  city: string;
  street: string;
  house: string;
  medCard: string;
  admittedDate: string;
  admittedTime: string;
  dxAdmission: string;
  dxClinical: string;
  dxComorbid: string;
  channel: string;
  residence: string;
}

/** Primary exam in the 2.9 format (primary_exam_v1); loosely typed on purpose — it is a large form. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ExamData = Record<string, any>;

export interface ExamTemplate {
  id: string;
  name: string;
  keywords: string;
  useCount: number;
  suggested: boolean;
  data: ExamData;
}

export interface ExamDraft {
  case: { id: string; number: string; status: string; admittedAt: string | null; dxAdmission: string; dxClinical: string; dxComorbid: string };
  existing: { id: string; printedAt: string | null; data: ExamData | null; legacyOnly: boolean } | null;
  previous: { number: string; date: string; data: ExamData } | null;
  prefill: ExamData;
  templates: ExamTemplate[];
  options: {
    local: Record<string, string[] | null>;
    anterior: { depth: string[]; fluid: string[] };
    anteriorRow: string;
    norms: Record<string, string[]>;
    anteriorNorm: { depth: string; fluid: string };
    objective: Record<string, string[]>;
    allergy: string[];
    insurance: string[];
    diagTypes: string[];
    complaintWords: string[];
    treatmentLabels: Record<string, string>;
  };
  base: ExamData;
}

/** Discharge form in 2.9's payload keys, plus destination/workplace that 2.9 kept only in its HTML. */
export interface DischargeForm {
  discharge_date: string;
  discharge_time: string;
  destination: string;
  workplace: string;
  outcome: string;
  final_diagnosis: string;
  report_group: string;
  epicrisis: string;
  recommendations: string;
  vis_od: string; vis_os: string;
  vis_correction_od: string; vis_correction_os: string;
  vis_od_corr: string; vis_os_corr: string;
  vis_od_result: string; vis_os_result: string;
  vgd_od: string; vgd_os: string;
  vgd_od_max: string; vgd_od_min: string; vgd_os_max: string; vgd_os_min: string;
  elasto_od: string; elasto_os: string;
  tono_od_ro: string; tono_od_c: string; tono_od_kb: string; tono_od_f: string;
  tono_os_ro: string; tono_os_c: string; tono_os_kb: string; tono_os_f: string;
  treatment_summary: string;
  sig_dep_chief: boolean;
  sig_chief: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  discharge_local: Record<string, Record<string, any>>;
}

export interface DischargeDraft {
  case: {
    id: string; number: string; medCard: string; status: CaseCard["status"]; admittedAt: string | null; dischargedAt: string | null;
    patient: string; dob: string | null; address: string; dxAdmission: string; dxClinical: string; dxComorbid: string;
  };
  saved: boolean;
  form: DischargeForm;
  sources: {
    admissionVision: Partial<DischargeForm> | null;
    dischargeVisionFrom: string | null;
    localFrom: string | null;
    complaints: string;
    lastDiary: { date: string; od: string; os: string; ou: string } | null;
    studies: { id: string; line: string }[];
    recentRecommendations: { text: string; dx: string }[];
    recentDestinations: string[];
  };
  options: {
    outcomes: string[];
    reportGroups: string[];
    local: Record<string, string[] | null>;
    anterior: { depth: string[]; fluid: string[] };
    anteriorRow: string;
  };
}

export interface StudyField { key: string; label: string; unit: string; range: [number, number] | null; kind: string }

export interface Study {
  id: string;
  date: string | null;
  unparsedDate: string | null;
  type: string;
  name: string;
  fields: Record<string, string>;
  text: string;
  result: string;
  flags: string[];
}

export interface StudyList {
  locked: boolean;
  studies: Study[];
  plan: { name: string; done: boolean; type: string }[];
  forms: Record<string, StudyField[]>;
  types: string[];
}

export interface StudyIn { date: string; type: string; fields: Record<string, string>; name: string; text: string }

export interface Prescription {
  id: string; category: string; name: string; method: string; freq: string;
  dateFrom: string | null; dateTo: string | null; active: boolean;
}

export interface PrescriptionList {
  locked: boolean;
  items: Prescription[];
  categories: Record<string, string>;
  plain: string[];
  templates: Record<string, string[]>;
  methods: string[];
  freqs: string[];
}

export interface ArchiveRow {
  caseId: string; number: string; patient: string; dob: string | null; dx: string; eye: string; groups: string[];
  admittedAt: string | null; dischargedAt: string | null; days: number | null; outcome: string;
}

export interface ArchiveResult {
  total: number; found: number; page: number; pages: number; size: number;
  rows: ArchiveRow[];
  firstDate: string | null;
  lastDate: string | null;
  dxGroups: { value: string; count: number }[];
  outcomes: { value: string; count: number }[];
}

/** from/to: the discharge date range, either end may be empty. */
export interface ArchiveQuery { q: string; from: string; to: string; dx: string; outcome: string; page?: number }

const archiveParams = ({ from, to, ...rest }: ArchiveQuery) =>
  new URLSearchParams(Object.entries({ ...rest, date_from: from, date_to: to })
    .filter(([, v]) => v !== "" && v !== undefined).map(([k, v]) => [k, String(v)])).toString();

export interface BackupItem { name: string; kind: string; kindLabel: string; at: string; size: number }

export interface BackupList {
  folder: string;
  extraDir: string;
  extraError: string | null;
  last: string | null;
  items: BackupItem[];
  keep: { daily: number; months: number };
}

export type SimpleKind = "operation_protocol" | "other";
export interface SimpleRecordIn {
  date: string; time: string; title: string; text: string;
  op_type: string; urgency: string; complication: boolean;    // the protocol only
}
export interface SimpleRecord extends SimpleRecordIn {
  id: string; caseId: string; kind: SimpleKind; printedAt: string | null; editable: boolean;
}
export interface OperationTemplate { name: string; description: string }
export interface RecordOptions { textTitles: string[]; templates: OperationTemplate[]; now: string; opTypes: string[]; urgency: string[] }

export interface StatsPoint { key: string; label: string; value: number | null; n?: number }
export interface Stats {
  from: string; to: string; group: "day" | "month" | "year";
  totals: { admitted: number; discharged: number; avgStay: number | null; inDepartment: number };
  admissions: StatsPoint[]; discharges: StatsPoint[]; avgStay: StatsPoint[];
  diagnoses: { label: string; value: number }[]; outcomes: { label: string; value: number }[];
  daily: { date: string; inDepartment: number; admitted: number }[];
  beds: number | null;
}

export interface ReportRow { label: string; count: number; share: number | null; bedDays: number; avgStay: number | null }
export interface ReportMain {
  beds: number; treated: number; admitted: number; discharged: number; died: number; bedDays: number;
  avgStay: number | null; bedWork: number | null; turnover: number | null; bedIdle: number | null; planPercent: number | null;
  rural: number; ruralPercent: number | null; nonresident: number; foreign: number; children: number; teens: number;
  emergency: number; planned: number; channelUnknown: number;
}
export interface ReportPeriod {
  from: string; to: string; hasData: boolean; main: ReportMain;
  channels: { label: string; kind: "emergency" | "planned"; count: number }[];
  outcomes: { label: string; count: number }[];
  structure: ReportRow[]; operations: ReportRow[];
  surgery: { operations: number; urgent: number; planned: number; urgencyUnknown: number; operatedUrgent: number;
    operatedPlanned: number; complicationsUrgent: number; complicationsPlanned: number };
  autoGroups?: { caseId: string; number: string; patient: string; dx: string; group: string }[];
}
export interface DeptReport {
  current: ReportPeriod; previous: ReportPeriod; groups: string[]; title: string; villages: string[];
  periods: { key: string; label: string; from: string; to: string }[];
}

export type DictName = "ophthalmic" | "comorbid" | "examinations" | "treatment" | "prescriptions" | "addresses";
export type DictValue = string[] | Record<string, string[]>;
export interface DictInfo {
  name: DictName;
  title: string;
  hint: string;
  groups: Record<string, string> | null;
  value: DictValue;
  edited: boolean;
  canReset: boolean;
}

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  return send<T>(method, path, body === undefined ? undefined : JSON.stringify(body),
    body === undefined ? undefined : { "Content-Type": "application/json" });
}

async function send<T>(method: string, path: string, body?: BodyInit, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(path, { method, headers, body });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const detail = (await res.json()).detail;
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail)) message = "Проверьте поля: " + detail.map((d) => d.loc?.slice(-1)[0]).join(", ");
    } catch {
      /* keep the status text */
    }
    throw new ApiError(message);
  }
  return res.json() as Promise<T>;
}

export interface CheckItem { item: string; caseId: string; number: string; fio: string; detail: string; link: string }
export interface CheckGroup { key: string; title: string; hint: string; fix: string; items: CheckItem[] }
export interface Checks { total: number; confirmed: number; groups: CheckGroup[] }

const get = <T,>(path: string) => request<T>("GET", path);

export const api = {
  department: () => get<Department>("/api/department"),
  caseCard: (id: string) => get<CaseCard>(`/api/cases/${encodeURIComponent(id)}`),
  legacyHtmlUrl: (recordId: string) => `/api/records/${encodeURIComponent(recordId)}/legacy`,
  diaryDraft: (caseId: string, day: string) =>
    get<DiaryDraft>(`/api/cases/${encodeURIComponent(caseId)}/diary-draft?day=${day}`),
  diary: (recordId: string) =>
    get<{ id: string; caseId: string; printedAt: string | null; data: DiaryData }>(`/api/diaries/${encodeURIComponent(recordId)}`),
  createDiary: (caseId: string, data: DiaryData) =>
    request<{ id: string }>("POST", `/api/cases/${encodeURIComponent(caseId)}/diaries`, data),
  updateDiary: (recordId: string, data: DiaryData) =>
    request<{ id: string }>("PUT", `/api/diaries/${encodeURIComponent(recordId)}`, data),
  round: (day: string) => get<{ day: string; rows: RoundRow[] }>(`/api/round?day=${day}`),
  printPlan: (caseId: string) => get<PrintPlan>(`/api/cases/${encodeURIComponent(caseId)}/print-plan`),
  createPrintJob: (caseId: string, kind: PrintKind, recordIds: string[], mode: PrintMode, startMm?: number,
    handwrittenTo?: number, handwrittenSheet?: number) =>
    request<PrintJob>("POST", `/api/cases/${encodeURIComponent(caseId)}/print-jobs`,
      { kind, recordIds, mode, startMm, handwrittenTo, handwrittenSheet }),
  printJobPageUrl: (jobId: string, page: number, dpi?: number) =>
    `/api/print-jobs/${jobId}/pages/${page}.png${dpi ? `?dpi=${dpi}` : ""}`,
  printJobPdfUrl: (jobId: string) => `/api/print-jobs/${jobId}/pdf`,
  printers: () => get<{ printers: string[]; default: string | null; error?: string }>("/api/printers"),
  sendToPrinter: (jobId: string, printer: string) => request<{ ok: true }>("POST", `/api/print-jobs/${jobId}/print`, { printer }),
  confirmPrint: (jobId: string) =>
    request<{ marked: number; sheet: number | null; usedMm: number | null }>("POST", `/api/print-jobs/${jobId}/confirm`),
  cancelPrint: (jobId: string) => request<{ ok: true }>("POST", `/api/print-jobs/${jobId}/cancel`),
  dictionaries: () => get<Dictionaries>("/api/dictionaries"),
  searchPatients: (q: string) => get<PatientMatch[]>(`/api/patients/search?q=${encodeURIComponent(q)}`),
  caseEdit: (caseId: string) =>
    get<{ caseId: string; number: string; status: string; dischargedAt: string | null; otherCases: number; form: AdmissionIn }>(
      `/api/cases/${encodeURIComponent(caseId)}/edit`),
  saveCaseEdit: (caseId: string, f: AdmissionIn) =>
    request<{ caseId: string }>("PUT", `/api/cases/${encodeURIComponent(caseId)}/edit`, f),
  admit: (a: AdmissionIn) => request<{ caseId: string; number: string; patientId: string }>("POST", "/api/admissions", a),
  examDraft: (caseId: string) => get<ExamDraft>(`/api/cases/${encodeURIComponent(caseId)}/exam-draft`),
  saveExam: (caseId: string, data: ExamData, recordId: string | null, templateId: string | null) =>
    recordId
      ? request<{ id: string }>("PUT", `/api/cases/${encodeURIComponent(caseId)}/exam/${encodeURIComponent(recordId)}`, { data, templateId })
      : request<{ id: string }>("POST", `/api/cases/${encodeURIComponent(caseId)}/exam`, { data, templateId }),
  examPreview: async (data: ExamData) => {
    const res = await fetch("/api/exam-preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data }) });
    if (!res.ok) throw new ApiError(`${res.status}`);
    return res.text();
  },
  saveTemplate: (name: string, keywords: string, data: ExamData) =>
    request<{ id: string }>("POST", "/api/exam-templates", { name, keywords, data }),
  discharge: (caseId: string) => get<DischargeDraft>(`/api/cases/${encodeURIComponent(caseId)}/discharge`),
  saveDischarge: (caseId: string, f: DischargeForm) =>
    request<{ id: string }>("PUT", `/api/cases/${encodeURIComponent(caseId)}/discharge`, f),
  dischargePages: (caseId: string) => get<{ pages: number }>(`/api/cases/${encodeURIComponent(caseId)}/discharge/pages`),
  dischargePageUrl: (caseId: string, page: number, stamp: number, dpi?: number) =>
    `/api/cases/${encodeURIComponent(caseId)}/discharge/pages/${page}.png?v=${stamp}${dpi ? `&dpi=${dpi}` : ""}`,
  dischargePdfUrl: (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/discharge/pdf`,
  printDischarge: (caseId: string, printer: string, copies: number) =>
    request<{ ok: true }>("POST", `/api/cases/${encodeURIComponent(caseId)}/discharge/print`, { printer, copies }),
  archive: (caseId: string) => request<{ ok: true }>("POST", `/api/cases/${encodeURIComponent(caseId)}/archive`),
  unarchive: (caseId: string) => request<{ ok: true }>("POST", `/api/cases/${encodeURIComponent(caseId)}/unarchive`),
  reopen: (caseId: string) => request<{ ok: true }>("POST", `/api/cases/${encodeURIComponent(caseId)}/reopen`),
  studies: (caseId: string) => get<StudyList>(`/api/cases/${encodeURIComponent(caseId)}/studies`),
  saveStudy: (caseId: string, s: StudyIn, id: string | null) =>
    id
      ? request<{ id: string }>("PUT", `/api/studies/${encodeURIComponent(id)}`, s)
      : request<{ id: string }>("POST", `/api/cases/${encodeURIComponent(caseId)}/studies`, s),
  deleteStudy: (id: string) => request<{ ok: true }>("DELETE", `/api/studies/${encodeURIComponent(id)}`),
  prescriptions: (caseId: string) => get<PrescriptionList>(`/api/cases/${encodeURIComponent(caseId)}/prescriptions`),
  addPrescriptions: (caseId: string, p: { category: string; names: string[]; method: string; freq: string; date_from: string | null; date_to: string | null }) =>
    request<{ ids: string[] }>("POST", `/api/cases/${encodeURIComponent(caseId)}/prescriptions`, p),
  updatePrescription: (id: string, p: { name: string; method: string; freq: string; date_from: string | null; date_to: string | null }) =>
    request<{ id: string }>("PUT", `/api/prescriptions/${encodeURIComponent(id)}`, p),
  cancelPrescription: (id: string) => request<{ ok: true }>("POST", `/api/prescriptions/${encodeURIComponent(id)}/cancel`),
  deletePrescription: (id: string) => request<{ ok: true }>("DELETE", `/api/prescriptions/${encodeURIComponent(id)}`),
  savePrescriptionTemplates: (templates: Record<string, string[]>) =>
    request<Record<string, string[]>>("PUT", "/api/prescription-templates", { templates }),
  archiveList: (a: ArchiveQuery) => get<ArchiveResult>(`/api/archive?${archiveParams(a)}`),
  archiveCsvUrl: (a: ArchiveQuery) => `/api/archive.csv?${archiveParams(a)}`,
  backups: () => get<BackupList>("/api/backups"),
  makeBackup: () => request<{ name: string; extraError: string | null }>("POST", "/api/backups"),
  restoreBackup: (name: string) => request<{ restored: string; savedAs: string }>("POST", `/api/backups/${encodeURIComponent(name)}/restore`),
  deleteBackup: (name: string) => request<{ ok: true }>("DELETE", `/api/backups/${encodeURIComponent(name)}`),
  setBackupExtraDir: (path: string) => request<{ extraDir: string }>("PUT", "/api/backups/extra-dir", { path }),
  openBackupFolder: () => request<{ ok: true }>("POST", "/api/backups/open-folder"),
  dictionary: (name: DictName) => get<DictInfo>(`/api/dictionaries/${name}`),
  saveDictionary: (name: DictName, value: DictValue) => request<DictInfo>("PUT", `/api/dictionaries/${name}`, { value }),
  resetDictionary: (name: DictName) => request<DictInfo>("DELETE", `/api/dictionaries/${name}`),
  recordOptions: () => get<RecordOptions>("/api/record-options"),
  record: (id: string) => get<SimpleRecord>(`/api/records/${encodeURIComponent(id)}`),
  saveRecord: (caseId: string, kind: SimpleKind, r: SimpleRecordIn, id: string | null) =>
    id
      ? request<{ id: string }>("PUT", `/api/records/${encodeURIComponent(id)}`, r)
      : request<{ id: string }>("POST", `/api/cases/${encodeURIComponent(caseId)}/records/${kind}`, r),
  deleteRecord: (id: string) => request<{ ok: true }>("DELETE", `/api/records/${encodeURIComponent(id)}`),
  saveOperationTemplate: (t: OperationTemplate) => request<OperationTemplate[]>("POST", "/api/operation-templates", t),
  deleteOperationTemplate: (name: string) =>
    request<OperationTemplate[]>("DELETE", `/api/operation-templates?name=${encodeURIComponent(name)}`),
  prescriptionPages: (caseId: string) => get<{ pages: number }>(`/api/cases/${encodeURIComponent(caseId)}/prescriptions/pages`),
  prescriptionPageUrl: (caseId: string, page: number, stamp: number) =>
    `/api/cases/${encodeURIComponent(caseId)}/prescriptions/pages/${page}.png?v=${stamp}`,
  prescriptionPdfUrl: (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/prescriptions/pdf`,
  printPrescriptions: (caseId: string, printer: string, copies: number) =>
    request<{ ok: true }>("POST", `/api/cases/${encodeURIComponent(caseId)}/prescriptions/print`, { printer, copies }),
  report: (from: string, to: string) =>
    get<DeptReport>(`/api/report?${new URLSearchParams({ date_from: from, date_to: to }).toString()}`),
  reportDocxUrl: (from: string, to: string) => `/api/report.docx?${new URLSearchParams({ date_from: from, date_to: to }).toString()}`,
  setReportGroup: (caseId: string, group: string) =>
    request<{ ok: true }>("PUT", `/api/cases/${encodeURIComponent(caseId)}/report-group`, { group }),
  checks: () => get<Checks>("/api/checks"),
  confirmCheck: (check: string, item: string) => request<Checks>("POST", "/api/checks/confirm", { check, item }),
  stats: (from: string, to: string) =>
    get<Stats>(`/api/stats?${new URLSearchParams({ date_from: from, date_to: to }).toString()}`),
  settings: () => get<Settings>("/api/settings"),
  saveSettings: (s: Settings) => request<Settings>("PUT", "/api/settings", s),
};
