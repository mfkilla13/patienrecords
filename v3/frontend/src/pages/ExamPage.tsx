import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, Dictionaries, ExamData, ExamDraft } from "../api";
import { VIS_STATUSES, WITH_CORRECTION } from "../diary";
import { fullDate, shortDate, todayIso } from "../format";
import { MultiChips } from "../components/MultiChips";
import "./exam.css";

type Eye = "od" | "os";
type Section = "anamnesis" | "objective" | "diagnosis" | "plan" | "treatment";

const OBJECTIVE_LABELS: Record<string, string> = {
  general_state: "Общее состояние", lymph_nodes: "Лимфоузлы", skin_state: "Кожные покровы", skin_color: "Окраска кожи",
  breathing: "Дыхание", breathing_side: "Симметричность", wheeze: "Хрипы", heart_tones: "Тоны сердца",
  heart_rhythm: "Ритм", pulse_rhythm: "Пульс: ритм", pulse_quality: "Пульс: свойства", abdomen_size: "Живот",
  abdomen_state: "Живот: тонус", abdomen_pain: "Живот: болезненность", liver_position: "Печень: положение",
  liver_edge: "Печень: край", liver_consistency: "Печень: консистенция", liver_pain: "Печень: болезненность",
  stool: "Стул", stool_form: "Стул: форма", urination: "Мочеиспускание", urination_pain: "Мочеиспускание: болезненность",
};
const NOT_VISIBLE = "не просматривается";
const FUNDUS = "Глазное дно";
const BEHIND_FUNDUS = ["Стекловидное тело", "Сосуды", "Сетчатка"];
const MEASURED: [string, string][] = [["vis_od", "Vis OD"], ["vis_os", "Vis OS"], ["vgd_od", "ВГД OD"], ["vgd_os", "ВГД OS"], ["bp_sys", "АД"], ["hr", "ЧСС"]];

const clone = <T,>(x: T): T => structuredClone(x);
const nowHm = () => new Date().toTimeString().slice(0, 5);

/** A template or an earlier exam replaces everything except what was measured and the diagnoses. */
function applyPart(form: ExamData, part: ExamData): ExamData {
  return { ...clone(form), ...clone(part) };
}

function fundusRule(d: ExamData, norms: Record<string, string[]>): ExamData {
  for (const eye of ["od", "os"] as Eye[]) {
    if ((d.local[FUNDUS]?.[`${eye}_selected`] ?? []).includes(NOT_VISIBLE)) {
      for (const name of BEHIND_FUNDUS) {
        const cell = d.local[name] ?? (d.local[name] = { od_selected: [], od_note: "", os_selected: [], os_note: "" });
        const vals: string[] = cell[`${eye}_selected`] ?? [];
        if (!vals.includes(NOT_VISIBLE)) cell[`${eye}_selected`] = [NOT_VISIBLE, ...vals.filter((v) => !(norms[name] ?? []).includes(v))];
      }
    }
  }
  return d;
}

/** «не просматривается» excludes every other finding: ticking it clears the rest, ticking another clears it. */
function exclusiveNotVisible(before: string[], after: string[]): string[] {
  const added = after.filter((v) => !before.includes(v));
  if (added.includes(NOT_VISIBLE)) return [NOT_VISIBLE];
  if (added.length && after.includes(NOT_VISIBLE)) return after.filter((v) => v !== NOT_VISIBLE);
  return after;
}

function cellText(cell: ExamData, eye: Eye, anterior: boolean): string {
  if (anterior) {
    return [cell[`${eye}_depth`] && `глубина ${cell[`${eye}_depth`]}`, cell[`${eye}_fluid`] && `влага ${cell[`${eye}_fluid`]}`].filter(Boolean).join(", ");
  }
  const s = (cell[`${eye}_selected`] ?? []).join("; ");
  const note = (cell[`${eye}_note`] ?? "").trim();
  return note ? `${s}${s ? " " : ""}(прим.: ${note})` : s;
}

export function ExamPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<ExamDraft | null>(null);
  const [dict, setDict] = useState<Dictionaries | null>(null);
  const [form, setForm] = useState<ExamData | null>(null);
  const [recordId, setRecordId] = useState<string | null>(null);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [source, setSource] = useState<string>("");
  const [readOnly, setReadOnly] = useState<string | null>(null);
  const [editingRow, setEditingRow] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState<Section | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [opNote, setOpNote] = useState<string | null>(null);
  const opTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    api.dictionaries().then(setDict, () => undefined);
    api.examDraft(caseId).then((d) => {
      setDraft(d);
      if (d.existing?.legacyOnly) {
        setReadOnly("Этот осмотр записан в 2.9 без разбивки по полям — его можно только напечатать, как он был сохранён.");
        return;
      }
      if (d.existing?.data) {
        setForm(d.existing.data);
        setRecordId(d.existing.id);
        setSource("сохранённый осмотр");
        if (d.existing.printedAt) setReadOnly(`Осмотр напечатан ${shortDate(d.existing.printedAt)} — изменить его нельзя, чтобы он не разошёлся с бумагой.`);
        return;
      }
      const tpl = d.templates.find((t) => t.suggested) ?? d.templates[0];
      const admitted = d.case.admittedAt ?? "";
      const day = admitted.slice(0, 10) || todayIso();
      let f = applyPart(d.base, tpl?.data ?? {});
      f = { ...f, ...d.prefill, visit_date: day, visit_time: day === todayIso() ? nowHm() : admitted.slice(11, 16) };
      setForm(fundusRule(f, d.options.norms));
      setTemplateId(tpl?.id ?? null);
      setSource(tpl ? `шаблон «${tpl.name}»` : "");
    }, (e: Error) => setError(e.message));
  }, [caseId]);

  // Live print preview: exactly the HTML that will be saved and printed.
  useEffect(() => {
    if (!form) return;
    const t = window.setTimeout(() => api.examPreview(form).then(setPreview, () => undefined), 350);
    return () => window.clearTimeout(t);
  }, [form]);

  const opts = draft?.options;
  const edit = (fn: (d: ExamData) => void) =>
    setForm((f) => {
      if (!f || readOnly) return f;
      const d = clone(f);
      fn(d);
      return opts ? fundusRule(d, opts.norms) : d;
    });
  const setField = (k: string, v: unknown) => edit((d) => { d[k] = v; });

  const useTemplate = (id: string, part: ExamData, label: string) => {
    if (!form || !opts) return;
    setForm(fundusRule(applyPart(form, part), opts.norms));
    setTemplateId(id.startsWith("prev:") ? null : id);
    setSource(label);
  };

  const deviations = useMemo(() => {
    if (!form || !opts) return [];
    const out: { name: string; eye: Eye; text: string }[] = [];
    for (const [name, cell] of Object.entries(form.local as Record<string, ExamData>)) {
      for (const eye of ["od", "os"] as Eye[]) {
        let normal: boolean;
        if (name === opts.anteriorRow) {
          normal = cell[`${eye}_depth`] === opts.anteriorNorm.depth && cell[`${eye}_fluid`] === opts.anteriorNorm.fluid;
        } else {
          const v = [...(cell[`${eye}_selected`] ?? [])].sort().join("|");
          normal = v === [...(opts.norms[name] ?? [])].sort().join("|") && !(cell[`${eye}_note`] ?? "").trim();
        }
        if (!normal) out.push({ name, eye, text: cellText(cell, eye, name === opts.anteriorRow) || "не заполнено" });
      }
    }
    return out;
  }, [form, opts]);

  const missing = form ? MEASURED.filter(([k]) => !(form[k] ?? "").trim()).map(([, l]) => l) : [];

  const save = async () => {
    if (!form) return;
    setError(null);
    if (missing.length && !window.confirm(`Не введено: ${missing.join(", ")}. Сохранить осмотр без этого?`)) return;
    setSaving(true);
    try {
      await api.saveExam(caseId, form, recordId, templateId);
      navigate(`/case/${caseId}`);
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  };

  const saveAsTemplate = async () => {
    if (!form) return;
    const name = window.prompt("Название шаблона (например: «Птеригиум»)", "");
    if (!name?.trim()) return;
    const keywords = window.prompt("По каким словам диагноза предлагать этот шаблон? (можно оставить пустым)", name.split(/[\s,]/)[0]) ?? "";
    try {
      await api.saveTemplate(name.trim(), keywords.trim(), form);
      window.alert(`Шаблон «${name.trim()}» сохранён. Он будет предлагаться в следующих осмотрах.`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  /** Quick local status actions; each one says what it did, or why nothing changed. */
  const localOps = (op: "norm-ou" | "od-os" | "os-od" | "mirror") => {
    if (!form || !opts || readOnly) return;
    const d = clone(form);
    for (const [name, cell] of Object.entries(d.local as Record<string, ExamData>)) {
      const anterior = name === opts.anteriorRow;
      const keys = anterior ? ["depth", "fluid"] : ["selected", "note"];
      if (op === "norm-ou") {
        for (const eye of ["od", "os"]) {
          if (anterior) Object.assign(cell, { [`${eye}_depth`]: opts.anteriorNorm.depth, [`${eye}_fluid`]: opts.anteriorNorm.fluid });
          else Object.assign(cell, { [`${eye}_selected`]: [...(opts.norms[name] ?? [])], [`${eye}_note`]: "" });
        }
        continue;
      }
      for (const k of keys) {
        const od = clone(cell[`od_${k}`]);
        const os = clone(cell[`os_${k}`]);
        if (op === "od-os") cell[`os_${k}`] = od;
        if (op === "os-od") cell[`od_${k}`] = os;
        if (op === "mirror") [cell[`od_${k}`], cell[`os_${k}`]] = [os, od];
      }
    }
    const next = fundusRule(d, opts.norms);
    const changed = JSON.stringify(next.local) !== JSON.stringify(form.local);
    setForm(next);
    const done = { "norm-ou": "Норма на оба глаза", "od-os": "OD скопирован на OS", "os-od": "OS скопирован на OD", mirror: "OD и OS поменялись местами" };
    const same = op === "norm-ou" ? "Уже всё в норме — менять нечего" : "Глаза и так одинаковые — менять нечего";
    setOpNote(changed ? `✓ ${done[op]}` : same);
    window.clearTimeout(opTimer.current);
    opTimer.current = window.setTimeout(() => setOpNote(null), 2600);
  };

  if (error && !draft) return <main className="page ex"><div className="card" style={{ padding: 24 }}>Не удалось открыть осмотр: {error}</div></main>;
  if (!draft || !opts) return <main className="page ex"><p className="muted">Загружаем осмотр…</p></main>;

  const rowEditor = (name: string) => {
    const cell = form!.local[name] ?? {};
    const anterior = name === opts.anteriorRow;
    return (
      <div className="ex-rowedit" key={name}>
        <b className="ex-rowname">{name}</b>
        {(["od", "os"] as Eye[]).map((eye) => (
          <div key={eye} className="ex-eye">
            <span className="ex-eyelabel">{eye.toUpperCase()}</span>
            {anterior ? (
              <span className="ex-chips">
                {(["depth", "fluid"] as const).map((k) => (
                  <label key={k} className="ex-inline">{k === "depth" ? "глубина" : "влага"}
                    <select className="in" value={cell[`${eye}_${k}`] ?? ""} disabled={Boolean(readOnly)}
                      onChange={(e) => edit((d) => { d.local[name][`${eye}_${k}`] = e.target.value; })}>
                      <option value="">—</option>
                      {opts.anterior[k].map((o) => <option key={o}>{o}</option>)}
                    </select>
                  </label>
                ))}
              </span>
            ) : (
              <span className="ex-eyebody">
                <MultiChips options={opts.local[name] ?? []} value={cell[`${eye}_selected`] ?? []} disabled={Boolean(readOnly)}
                  onChange={(v) => edit((d) => { d.local[name][`${eye}_selected`] = exclusiveNotVisible(cell[`${eye}_selected`] ?? [], v); })} />
                <input className="in ex-note" placeholder="примечание" value={cell[`${eye}_note`] ?? ""} disabled={Boolean(readOnly)}
                  onChange={(e) => edit((d) => { d.local[name][`${eye}_note`] = e.target.value; })} />
              </span>
            )}
          </div>
        ))}
      </div>
    );
  };

  const f = form;
  const summary: Record<Section, string> = f ? {
    anamnesis: [f.complaints && `жалобы ${f.complaints}`, f.disease_anamnesis, `аллергия: ${f.allergy_combo === opts.allergy[0] ? "не отягощен" : f.allergy_text || "есть"}`, f.insurance].filter(Boolean).join("; "),
    objective: Object.entries(opts.objective).filter(([k, o]) => f[k] !== o[0]).map(([k]) => `${OBJECTIVE_LABELS[k] ?? k}: ${f[k]}`).join("; ") || "всё в норме",
    diagnosis: [`${f.diag_type}: ${[f.diagnosis_free, ...(["od", "os", "ou"].map((e) => (f[`selected_diagnoses_${e}`] ?? []).length ? `${f[`selected_diagnoses_${e}`].join(", ")} ${e.toUpperCase()}` : ""))].filter(Boolean).join(". ") || "не указан"}`,
      [...(f.selected_comorbid_diagnoses ?? []), f.custom_comorbid_diagnosis].filter(Boolean).join(", ")].filter(Boolean).join(" · сопутствующий: "),
    plan: (f.selected_examinations ?? []).join(", ") || "не выбран",
    treatment: Object.entries(f.treatment as Record<string, { selected: string[] }>).filter(([, v]) => v.selected?.length).map(([k, v]) => `${opts.treatmentLabels[k]}: ${v.selected.join(", ")}`).join("; ") || "не выбрано",
  } : { anamnesis: "", objective: "", diagnosis: "", plan: "", treatment: "" };

  return (
    <main className="page ex">
      <div className="ex-top">
        <Link to={`/case/${caseId}`} className="round-btn white" aria-label="Назад к истории">
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <div style={{ flex: "1 1 300px" }}>
          <h1>Первичный осмотр</h1>
          <div className="muted">История № {draft.case.number}{draft.case.admittedAt && ` · поступил(а) ${fullDate(draft.case.admittedAt)}`} · <b style={{ color: "var(--text)" }}>{draft.case.dxClinical || draft.case.dxAdmission}</b></div>
        </div>
        {f && !readOnly && (
          <>
            <label className="ex-inline">Дата <input className="in white" type="date" value={f.visit_date} onChange={(e) => setField("visit_date", e.target.value)} /></label>
            <label className="ex-inline">Время <input className="in white" style={{ width: 84 }} value={f.visit_time} onChange={(e) => setField("visit_time", e.target.value)} /></label>
          </>
        )}
      </div>

      {error && <div className="dy-banner dy-error" role="alert">{error}</div>}
      {readOnly && <div className="dy-banner">{readOnly} <Link to={`/case/${caseId}`}>Вернуться в историю</Link></div>}

      {f && (
        <>
          {!recordId && (
            <section className="card ex-card">
              <div className="ex-step"><span className="pr-num">1</span><b>Шаблон</b><span className="muted">{source ? `сейчас: ${source}` : ""}</span></div>
              <div className="ex-templates">
                {draft.previous && (
                  <button type="button" className={"ex-tpl prev" + (source.startsWith("история") ? " on" : "")}
                    onClick={() => useTemplate(`prev:${draft.previous!.number}`, draft.previous!.data, `история № ${draft.previous!.number}`)}>
                    <b>Из прошлой истории № {draft.previous.number}</b>
                    <span className="muted">осмотр от {shortDate(draft.previous.date)}, без измерений</span>
                  </button>
                )}
                {draft.templates.map((t) => (
                  <button key={t.id} type="button" className={"ex-tpl" + (templateId === t.id ? " on" : "")} aria-pressed={templateId === t.id}
                    onClick={() => useTemplate(t.id, t.data, `шаблон «${t.name}»`)}>
                    <b>{t.name}</b>
                    <span className="muted">{t.suggested ? "подобран по диагнозу" : t.useCount ? `использован ${t.useCount} раз` : "шаблон"}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <div className="ex-body">
            <div className="ex-form">
              <section className="card ex-card">
                <div className="ex-step">
                  <span className="pr-num">{recordId ? 1 : 2}</span><b>Измерения</b><span className="muted">шаблон их не заполняет</span>
                  <div style={{ flex: 1 }} />
                  {missing.length > 0 && <span className="pill tone-amber">осталось {missing.length}</span>}
                </div>
                <table className="dy-vis">
                  <thead><tr><th style={{ width: 44 }}></th><th>Vis</th><th>Статус</th><th>Коррекция = результат</th><th>ВГД</th></tr></thead>
                  <tbody>
                    {(["od", "os"] as Eye[]).map((eye) => (
                      <tr key={eye}>
                        <td className="dy-eye">{eye.toUpperCase()}</td>
                        <td><input className={"in" + (!f[`vis_${eye}`] ? " need" : "")} style={{ width: 90 }} inputMode="decimal" value={f[`vis_${eye}`]} disabled={Boolean(readOnly)} onChange={(e) => setField(`vis_${eye}`, e.target.value)} /></td>
                        <td>
                          <select className="in" style={{ width: 190 }} value={f[`vis_correction_${eye}`]} disabled={Boolean(readOnly)}
                            onChange={(e) => edit((d) => { d[`vis_correction_${eye}`] = e.target.value; if (e.target.value !== WITH_CORRECTION) { d[`vis_${eye}_corr`] = ""; d[`vis_${eye}_result`] = ""; } })}>
                            {VIS_STATUSES.map((s) => <option key={s}>{s}</option>)}
                          </select>
                        </td>
                        <td>
                          {f[`vis_correction_${eye}`] === WITH_CORRECTION ? (
                            <span className="dy-corr">
                              <input className="in" style={{ width: 90 }} placeholder="+1,5" value={f[`vis_${eye}_corr`]} disabled={Boolean(readOnly)} onChange={(e) => setField(`vis_${eye}_corr`, e.target.value)} />
                              = <input className="in" style={{ width: 70 }} value={f[`vis_${eye}_result`]} disabled={Boolean(readOnly)} onChange={(e) => setField(`vis_${eye}_result`, e.target.value)} />
                            </span>
                          ) : <span className="muted" style={{ fontSize: 13 }}>только при «с коррекцией»</span>}
                        </td>
                        <td><input className={"in" + (!f[`vgd_${eye}`] ? " need" : "")} style={{ width: 80 }} inputMode="numeric" value={f[`vgd_${eye}`]} disabled={Boolean(readOnly)} onChange={(e) => setField(`vgd_${eye}`, e.target.value)} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="ex-vitals">
                  <label className="lbl">АД, мм рт. ст.
                    <span className="ex-bp">
                      <input className={"in" + (!f.bp_sys ? " need" : "")} inputMode="numeric" value={f.bp_sys} disabled={Boolean(readOnly)} onChange={(e) => setField("bp_sys", e.target.value)} />/
                      <input className="in" inputMode="numeric" value={f.bp_dia} disabled={Boolean(readOnly)} onChange={(e) => setField("bp_dia", e.target.value)} />
                    </span>
                  </label>
                  <label className="lbl">ЧСС, уд/мин <input className={"in" + (!f.hr ? " need" : "")} inputMode="numeric" value={f.hr} disabled={Boolean(readOnly)} onChange={(e) => setField("hr", e.target.value)} /></label>
                  <label className="lbl">Пульс, уд/мин <input className="in" inputMode="numeric" value={f.pulse} disabled={Boolean(readOnly)} onChange={(e) => setField("pulse", e.target.value)} /></label>
                </div>
              </section>

              <section className="card ex-card">
                <div className="ex-step">
                  <span className="pr-num">{recordId ? 2 : 3}</span><b>Отличия от нормы</b>
                  <div style={{ flex: 1 }} />
                  {opNote && <span className="ex-opnote" role="status">{opNote}</span>}
                  {!readOnly && (
                    <span className="ex-chips">
                      <button type="button" className="chip" onClick={() => localOps("norm-ou")}>OU норма</button>
                      <button type="button" className="chip" onClick={() => localOps("od-os")}>OD → OS</button>
                      <button type="button" className="chip" onClick={() => localOps("os-od")}>OS → OD</button>
                      <button type="button" className="chip" onClick={() => localOps("mirror")} title="Поменять OD и OS местами — для шаблона на другой глаз">OD ⇄ OS</button>
                    </span>
                  )}
                </div>
                {deviations.length === 0 && <p className="muted" style={{ margin: 0 }}>Всё в норме на обоих глазах.</p>}
                {!showAll && deviations.map((dv) => (
                  editingRow === dv.name ? null : (
                    <button key={`${dv.name}-${dv.eye}`} type="button" className="ex-dev" onClick={() => setEditingRow(dv.name)} disabled={Boolean(readOnly)}>
                      <b className="ex-dev-eye">{dv.eye.toUpperCase()}</b>
                      <span className="ex-dev-name">{dv.name}</span>
                      <span className="ex-dev-val">{dv.text}</span>
                      {!readOnly && <span className="ex-edit">изменить</span>}
                    </button>
                  )
                ))}
                {!showAll && editingRow && (
                  <div className="ex-editing">
                    {rowEditor(editingRow)}
                    <button type="button" className="btn small" onClick={() => setEditingRow(null)}>Готово</button>
                  </div>
                )}
                {!showAll && !readOnly && (
                  <label className="ex-inline">+ отличие
                    <select className="in" value="" onChange={(e) => e.target.value && setEditingRow(e.target.value)}>
                      <option value="">выберите структуру…</option>
                      {Object.keys(f.local).map((n) => <option key={n}>{n}</option>)}
                    </select>
                  </label>
                )}
                <button type="button" className="link-btn" onClick={() => { setShowAll(!showAll); setEditingRow(null); }}>
                  {showAll ? "Скрыть полный список" : `Показать все ${Object.keys(f.local).length} структур`}
                </button>
                {showAll && Object.keys(f.local).map((n) => rowEditor(n))}
              </section>

              <section className="card ex-card ex-sections">
                {([
                  ["anamnesis", "Жалобы и анамнез"], ["objective", "Объективный осмотр"], ["diagnosis", "Диагноз"],
                  ["plan", "План обследования"], ["treatment", "Обоснование лечения"],
                ] as [Section, string][]).map(([key, title]) => (
                  <div key={key} className="ex-section">
                    <button type="button" className="ex-section-head" onClick={() => setOpen(open === key ? null : key)} aria-expanded={open === key}>
                      <span className="ex-check" aria-hidden="true">✓</span>
                      <b className="ex-section-title">{title}</b>
                      <span className="ex-section-sum">{summary[key]}</span>
                      <span className="ex-edit">{open === key ? "свернуть" : readOnly ? "показать" : "изменить"}</span>
                    </button>
                    {open === key && (
                      <div className="ex-section-body">
                        {key === "anamnesis" && (
                          <>
                            <label className="lbl">Жалобы
                              <textarea className="ta" rows={2} value={f.complaints} disabled={Boolean(readOnly)} onChange={(e) => setField("complaints", e.target.value)} />
                            </label>
                            {!readOnly && (
                              <span className="ex-chips">
                                {opts.complaintWords.map((w) => (
                                  <button key={w} type="button" className="chip" onClick={() => setField("complaints", `${(f.complaints ?? "").trimEnd()} ${w}`.trim())}>{w}</button>
                                ))}
                              </span>
                            )}
                            <label className="lbl">История настоящего заболевания
                              <textarea className="ta" rows={2} value={f.disease_anamnesis} disabled={Boolean(readOnly)} onChange={(e) => setField("disease_anamnesis", e.target.value)} />
                            </label>
                            <div className="ex-grid3">
                              <label className="lbl">Туберкулёз, кожвен-заболевания <input className="in" value={f.tb} disabled={Boolean(readOnly)} onChange={(e) => setField("tb", e.target.value)} /></label>
                              <label className="lbl">Аллергологический анамнез
                                <select className="in" value={f.allergy_combo} disabled={Boolean(readOnly)} onChange={(e) => setField("allergy_combo", e.target.value)}>
                                  {opts.allergy.map((o) => <option key={o}>{o}</option>)}
                                </select>
                              </label>
                              {f.allergy_combo !== opts.allergy[0] && (
                                <label className="lbl">Аллергены <input className="in" value={f.allergy_text} disabled={Boolean(readOnly)} onChange={(e) => setField("allergy_text", e.target.value)} /></label>
                              )}
                              <label className="lbl">Страховой анамнез
                                <select className="in" value={f.insurance} disabled={Boolean(readOnly)} onChange={(e) => setField("insurance", e.target.value)}>
                                  {[...new Set([...opts.insurance, f.insurance])].map((o) => <option key={o}>{o}</option>)}
                                </select>
                              </label>
                            </div>
                          </>
                        )}
                        {key === "objective" && (
                          <div className="ex-grid3">
                            {Object.entries(opts.objective).map(([k, o]) => (
                              <label key={k} className="lbl">{OBJECTIVE_LABELS[k] ?? k}
                                <select className="in" value={f[k]} disabled={Boolean(readOnly)} onChange={(e) => setField(k, e.target.value)}>
                                  {[...new Set([...o, f[k]])].map((v) => <option key={v}>{v}</option>)}
                                </select>
                              </label>
                            ))}
                          </div>
                        )}
                        {key === "diagnosis" && (
                          <>
                            <div className="seg" role="radiogroup" style={{ alignSelf: "flex-start", minWidth: 300 }}>
                              {opts.diagTypes.map((t) => (
                                <button key={t} type="button" role="radio" aria-checked={f.diag_type === t} className={f.diag_type === t ? "on" : ""} disabled={Boolean(readOnly)} onClick={() => setField("diag_type", t)}>{t}</button>
                              ))}
                            </div>
                            <label className="lbl">Диагноз (из поступления, можно править)
                              <input className="in" list="ex-dx" value={f.diagnosis_free} disabled={Boolean(readOnly)} onChange={(e) => setField("diagnosis_free", e.target.value)} />
                            </label>
                            {(["od", "os", "ou"] as const).map((eye) => (
                              <div key={eye} className="lbl">Ещё диагнозы {eye.toUpperCase()}
                                <span className="ex-chips">
                                  {(f[`selected_diagnoses_${eye}`] ?? []).map((x: string) => (
                                    <button key={x} type="button" className="chip on" disabled={Boolean(readOnly)}
                                      onClick={() => edit((d) => { d[`selected_diagnoses_${eye}`] = d[`selected_diagnoses_${eye}`].filter((y: string) => y !== x); })}>{x} ×</button>
                                  ))}
                                  {!readOnly && (
                                    <input className="in ex-add" list="ex-dx" placeholder="+ из справочника" onKeyDown={(e) => {
                                      const v = (e.target as HTMLInputElement).value.trim();
                                      if (e.key === "Enter" && v) { edit((d) => { d[`selected_diagnoses_${eye}`] = [...(d[`selected_diagnoses_${eye}`] ?? []), v]; }); (e.target as HTMLInputElement).value = ""; }
                                    }} />
                                  )}
                                </span>
                                {(f[`custom_diagnosis_${eye}`] ?? "") && (
                                  <input className="in" value={f[`custom_diagnosis_${eye}`]} disabled={Boolean(readOnly)} onChange={(e) => setField(`custom_diagnosis_${eye}`, e.target.value)} />
                                )}
                              </div>
                            ))}
                            <div className="lbl">Сопутствующие
                              <span className="ex-chips">
                                {(f.selected_comorbid_diagnoses ?? []).map((x: string) => (
                                  <button key={x} type="button" className="chip on" disabled={Boolean(readOnly)}
                                    onClick={() => edit((d) => { d.selected_comorbid_diagnoses = d.selected_comorbid_diagnoses.filter((y: string) => y !== x); })}>{x} ×</button>
                                ))}
                                {!readOnly && (
                                  <input className="in ex-add" list="ex-comorbid" placeholder="+ из справочника" onKeyDown={(e) => {
                                    const v = (e.target as HTMLInputElement).value.trim();
                                    if (e.key === "Enter" && v) { edit((d) => { d.selected_comorbid_diagnoses = [...(d.selected_comorbid_diagnoses ?? []), v]; }); (e.target as HTMLInputElement).value = ""; }
                                  }} />
                                )}
                              </span>
                              <input className="in" placeholder="свой текст" value={f.custom_comorbid_diagnosis} disabled={Boolean(readOnly)} onChange={(e) => setField("custom_comorbid_diagnosis", e.target.value)} />
                            </div>
                            <span className="ex-hint">Из справочника: введите начало и нажмите Enter.</span>
                          </>
                        )}
                        {key === "plan" && (
                          <MultiChips options={dict?.examinations ?? []} value={f.selected_examinations ?? []} disabled={Boolean(readOnly)}
                            onChange={(v) => setField("selected_examinations", v)} />
                        )}
                        {key === "treatment" && (
                          <div className="ex-treat">
                            {Object.entries(opts.treatmentLabels).map(([k, label]) => (
                              <div key={k} className="ex-treat-row">
                                <span className="ex-treat-label">{label}</span>
                                <MultiChips options={dict?.treatment[k] ?? []} value={f.treatment[k]?.selected ?? []} disabled={Boolean(readOnly)}
                                  onChange={(v) => edit((d) => { d.treatment[k] = { ...(d.treatment[k] ?? { note: "" }), selected: v }; })} />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </section>
            </div>

            <aside className="card ex-preview" aria-label="Предпросмотр">
              <b>Так будет на бумаге</b>
              <iframe title="Предпросмотр осмотра" className="ex-frame" sandbox="" srcDoc={`<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><div style="font-family:'Segoe UI',Arial,sans-serif;padding:14px">${preview}</div>`} />
              <span className="muted" style={{ fontSize: 13 }}>Вёрстка как в 2.9. На печати сверху будет «Дата | Первичный осмотр».</span>
            </aside>
          </div>

          <datalist id="ex-dx">{dict?.ophthalmic.map((d) => <option key={d} value={d} />)}</datalist>
          <datalist id="ex-comorbid">{dict?.comorbid.map((d) => <option key={d} value={d} />)}</datalist>

          {!readOnly && (
            <div className="ex-foot">
              <span className="muted" style={{ flex: 1, minWidth: 240 }}>
                {missing.length ? `Не введено: ${missing.join(", ")}` : "Все измерения введены."}
              </span>
              <button type="button" className="btn" onClick={saveAsTemplate}>Сохранить как шаблон…</button>
              <Link to={`/case/${caseId}`} className="btn">Отмена</Link>
              <button type="button" className="btn primary" onClick={save} disabled={saving}>{saving ? "Сохраняем…" : "Сохранить осмотр"}</button>
            </div>
          )}
        </>
      )}
    </main>
  );
}
