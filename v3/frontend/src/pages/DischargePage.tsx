import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, DiaryData, DischargeDraft, DischargeForm } from "../api";
import { MultiChips } from "../components/MultiChips";
import { VisionFractions } from "../components/VisionFractions";
import { toVision, VIS_STATUSES, WITH_CORRECTION } from "../diary";
import { fullDate, plural, shortDate } from "../format";
import "./exam.css";
import "./diary.css";
import "./discharge.css";

type Eye = "od" | "os";
const STEPS = ["Общие данные", "Диагноз", "Статус при выписке", "Лечение", "Эпикриз", "Рекомендации", "Печать"] as const;
const PRINT_STEP = STEPS.length - 1;

const visionOf = (f: Partial<DischargeForm> | null) => (f ? toVision(f as unknown as DiaryData) : null);

function stayDays(admitted: string | null, discharge: string): number | null {
  if (!admitted || !/^\d{4}-\d{2}-\d{2}/.test(discharge)) return null;
  const a = new Date(admitted.slice(0, 10) + "T00:00").getTime();
  const d = new Date(discharge.slice(0, 10) + "T00:00").getTime();
  return Math.round((d - a) / 86400000) + 1;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function cellText(cell: Record<string, any> | undefined, eye: Eye, anterior: boolean): string {
  if (!cell) return "";
  if (anterior) {
    return [cell[`${eye}_depth`] && `глубина ${cell[`${eye}_depth`]}`, cell[`${eye}_fluid`] && `влага ${cell[`${eye}_fluid`]}`].filter(Boolean).join(", ");
  }
  const s = (cell[`${eye}_selected`] ?? []).join("; ");
  const note = (cell[`${eye}_note`] ?? "").trim();
  return note ? `${s}${s ? " " : ""}(прим.: ${note})` : s;
}

export function DischargePage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DischargeDraft | null>(null);
  const [form, setForm] = useState<DischargeForm | null>(null);
  const [step, setStep] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editingRow, setEditingRow] = useState<string | null>(null);
  const [showAllRows, setShowAllRows] = useState(false);
  const [pickStudies, setPickStudies] = useState<string[] | null>(null);
  const [pages, setPages] = useState(0);
  const [stamp, setStamp] = useState(0);
  const [printers, setPrinters] = useState<{ list: string[]; chosen: string }>({ list: [], chosen: "" });
  const [copies, setCopies] = useState(1);
  const [note, setNote] = useState<string | null>(null);
  const epicrisisRef = useRef<HTMLTextAreaElement>(null);
  const cursor = useRef<number | null>(null);   // where the doctor last left the cursor in the epicrisis

  const load = () =>
    api.discharge(caseId).then((d) => {
      setDraft(d);
      setForm(d.form);
      setDirty(false);
      return d;
    });

  useEffect(() => {
    load().then((d) => { if (d.saved) setStep(PRINT_STEP); }, (e: Error) => setError(e.message));
    api.printers().then((p) => setPrinters({ list: p.printers, chosen: p.default ?? p.printers[0] ?? "" }), () => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const archived = draft?.case.status === "archived";

  // The print step shows the saved discharge, so it needs a fresh page count after each save.
  useEffect(() => {
    if (step !== PRINT_STEP || !draft?.saved) return;
    api.dischargePages(caseId).then((r) => setPages(r.pages), (e: Error) => setError(e.message));
  }, [step, draft?.saved, stamp, caseId]);

  const set = <K extends keyof DischargeForm>(k: K, v: DischargeForm[K]) => {
    if (archived) return;
    setForm((f) => (f ? { ...f, [k]: v } : f));
    setDirty(true);
  };
  const editLocal = (fn: (local: DischargeForm["discharge_local"]) => void) => {
    if (!form || archived) return;
    const local = structuredClone(form.discharge_local);
    fn(local);
    set("discharge_local", local);
  };

  const days = form && draft ? stayDays(draft.case.admittedAt, form.discharge_date) : null;
  const admissionVision = visionOf(draft?.sources.admissionVision ?? null);
  const dischargeVision = visionOf(form);

  const localRows = useMemo(() => {
    if (!form || !draft) return [];
    const names = Object.keys(draft.options.local);
    return names.map((name) => {
      const anterior = name === draft.options.anteriorRow;
      const cell = form.discharge_local[name];
      return { name, od: cellText(cell, "od", anterior), os: cellText(cell, "os", anterior) };
    });
  }, [form, draft]);

  /** «OD: Роговица - прозрачная, ...» — the line 2.9 inserted for one eye. */
  const localLine = (eye: Eye) => {
    const parts = localRows.filter((r) => r[eye]).map((r) => `${r.name} - ${r[eye]}`);
    return parts.length ? `${eye.toUpperCase()}: ${parts.join(", ")}` : "";
  };

  /** Insert at the cursor of the epicrisis (2.9 always appended at the end). */
  const insert = (text: string, ownLine = true) => {
    if (!form || !text) return;
    const ta = epicrisisRef.current;
    const value = form.epicrisis;
    const at = Math.min(cursor.current ?? value.length, value.length);
    const before = value.slice(0, at);
    const after = value.slice(at);
    const lead = ownLine && before && !before.endsWith("\n") ? "\n" : "";
    const next = before + lead + text + after;
    set("epicrisis", next);
    requestAnimationFrame(() => {
      if (!ta) return;
      ta.focus();
      const pos = (before + lead + text).length;
      ta.setSelectionRange(pos, pos);
      cursor.current = pos;
    });
  };

  const flash = (text: string) => {
    setNote(text);
    window.setTimeout(() => setNote(null), 3000);
  };

  const save = async (then?: () => void) => {
    if (!form) return;
    setError(null);
    if (days != null && days <= 0) {
      setError("Дата выписки не может быть раньше даты поступления.");
      setStep(0);
      return;
    }
    setSaving(true);
    try {
      await api.saveDischarge(caseId, form);
      await load();
      setStamp((s) => s + 1);
      then?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const goTo = (i: number) => {
    if (i === PRINT_STEP && (dirty || !draft?.saved) && !archived) {
      save(() => setStep(PRINT_STEP));
      return;
    }
    setStep(i);
  };

  const print = async () => {
    setError(null);
    try {
      await api.printDischarge(caseId, printers.chosen, copies);
      flash(`Отправлено на «${printers.chosen}»${copies > 1 ? ` — ${copies} экз.` : ""}`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const toArchive = async () => {
    if (!window.confirm(`Перенести историю № ${draft?.case.number} в архив?`)) return;
    try {
      await api.archive(caseId);
      navigate("/");
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const unarchive = async () => {
    try {
      await api.unarchive(caseId);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (error && !draft) return <main className="page ds"><div className="card" style={{ padding: 24 }}>Не удалось открыть выписку: {error}</div></main>;
  if (!draft || !form) return <main className="page ds"><p className="muted">Загружаем выписку…</p></main>;

  const c = draft.case;
  const src = draft.sources;
  const opts = draft.options;
  const ro = archived;

  const rowEditor = (name: string) => {
    const cell = form.discharge_local[name] ?? {};
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
                    <select className="in" value={cell[`${eye}_${k}`] ?? ""}
                      onChange={(e) => editLocal((l) => { l[name] = { ...(l[name] ?? {}), [`${eye}_${k}`]: e.target.value }; })}>
                      <option value="">—</option>
                      {opts.anterior[k].map((o) => <option key={o}>{o}</option>)}
                    </select>
                  </label>
                ))}
              </span>
            ) : (
              <span className="ex-eyebody">
                <MultiChips options={opts.local[name] ?? []} value={cell[`${eye}_selected`] ?? []}
                  onChange={(v) => editLocal((l) => { l[name] = { ...(l[name] ?? {}), [`${eye}_selected`]: v }; })} />
                <input className="in ex-note" placeholder="примечание" value={cell[`${eye}_note`] ?? ""}
                  onChange={(e) => editLocal((l) => { l[name] = { ...(l[name] ?? {}), [`${eye}_note`]: e.target.value }; })} />
              </span>
            )}
          </div>
        ))}
      </div>
    );
  };

  const filledRows = localRows.filter((r) => r.od || r.os);
  const shownRows = showAllRows ? localRows : filledRows;

  const visTable = (
    <table className="dy-vis">
      <thead><tr><th style={{ width: 44 }}></th><th>Vis</th><th>Статус</th><th>Коррекция = результат</th><th>ВГД</th></tr></thead>
      <tbody>
        {(["od", "os"] as Eye[]).map((eye) => (
          <tr key={eye}>
            <td className="dy-eye">{eye.toUpperCase()}</td>
            <td><input className="in" style={{ width: 90 }} inputMode="decimal" value={form[`vis_${eye}`]} disabled={ro} onChange={(e) => set(`vis_${eye}`, e.target.value)} /></td>
            <td>
              <select className="in" style={{ width: 190 }} value={form[`vis_correction_${eye}`] || "пусто"} disabled={ro}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm((f) => f && { ...f, [`vis_correction_${eye}`]: v, ...(v !== WITH_CORRECTION ? { [`vis_${eye}_corr`]: "", [`vis_${eye}_result`]: "" } : {}) });
                  setDirty(true);
                }}>
                {VIS_STATUSES.map((s) => <option key={s}>{s}</option>)}
              </select>
            </td>
            <td>
              {form[`vis_correction_${eye}`] === WITH_CORRECTION ? (
                <span className="dy-corr">
                  <input className="in" style={{ width: 90 }} placeholder="+1,5" value={form[`vis_${eye}_corr`]} disabled={ro} onChange={(e) => set(`vis_${eye}_corr`, e.target.value)} />
                  = <input className="in" style={{ width: 70 }} value={form[`vis_${eye}_result`]} disabled={ro} onChange={(e) => set(`vis_${eye}_result`, e.target.value)} />
                </span>
              ) : <span className="muted" style={{ fontSize: 13 }}>только при «с коррекцией»</span>}
            </td>
            <td><input className="in" style={{ width: 80 }} inputMode="numeric" value={form[`vgd_${eye}`]} disabled={ro} onChange={(e) => set(`vgd_${eye}`, e.target.value)} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const small = (k: keyof DischargeForm, label?: string, width = 76) => (
    <label className="ex-inline">{label}
      <input className="in" style={{ width }} value={form[k] as string} disabled={ro} onChange={(e) => set(k, e.target.value as never)} />
    </label>
  );

  const body = [
    // 0 — Общие данные
    <>
      <div className="ds-row">
        <label className="lbl">Дата выписки
          <input className="in" type="date" value={form.discharge_date} disabled={ro} onChange={(e) => set("discharge_date", e.target.value)} />
        </label>
        <label className="lbl">Время
          <input className="in" style={{ width: 100 }} value={form.discharge_time} placeholder="ЧЧ:ММ" disabled={ro} onChange={(e) => set("discharge_time", e.target.value)} />
        </label>
        <div className="ds-fact">
          <span className="muted">Поступление</span>
          <b>{fullDate(c.admittedAt)}</b>
        </div>
        <div className={"ds-fact" + (days != null && days <= 0 ? " bad" : "")}>
          <span className="muted">Койко-дней</span>
          <b>{days ?? "—"}</b>
        </div>
      </div>
      <label className="lbl">Куда направляется выписка («В …»)
        <input className="in" value={form.destination} disabled={ro} placeholder="например: поликлинику по месту жительства" onChange={(e) => set("destination", e.target.value)} />
      </label>
      {!ro && src.recentDestinations.length > 0 && (
        <span className="ex-chips">
          {src.recentDestinations.map((d) => (
            <button key={d} type="button" className={"chip" + (form.destination === d ? " on" : "")} onClick={() => set("destination", d)}>{d}</button>
          ))}
        </span>
      )}
      <label className="lbl">Место работы и род занятий
        <input className="in" value={form.workplace} disabled={ro} onChange={(e) => set("workplace", e.target.value)} />
      </label>
      <div className="lbl">Исход
        <span className="ex-chips">
          {[...new Set([...opts.outcomes, form.outcome].filter(Boolean))].map((o) => (
            <button key={o} type="button" className={"chip" + (form.outcome === o ? " on" : "")} aria-pressed={form.outcome === o} disabled={ro} onClick={() => set("outcome", o)}>{o}</button>
          ))}
        </span>
        {(form.outcome === "другое" || !opts.outcomes.includes(form.outcome)) && (
          <input className="in" placeholder="свой исход" value={form.outcome === "другое" ? "" : form.outcome} disabled={ro} onChange={(e) => set("outcome", e.target.value || "другое")} />
        )}
      </div>
    </>,
    // 1 — Диагноз
    <>
      <label className="lbl">Полный диагноз (основное заболевание, сопутствующее осложнение)
        <textarea className="ta" rows={4} value={form.final_diagnosis} disabled={ro} onChange={(e) => set("final_diagnosis", e.target.value)} />
      </label>
      {!ro && (
        <span className="ex-chips">
          <span className="muted ds-insert-label">Взять:</span>
          {c.dxClinical && <button type="button" className="chip" onClick={() => set("final_diagnosis", c.dxClinical)}>клинический: {c.dxClinical}</button>}
          {c.dxAdmission && c.dxAdmission !== c.dxClinical && <button type="button" className="chip" onClick={() => set("final_diagnosis", c.dxAdmission)}>при поступлении: {c.dxAdmission}</button>}
          {c.dxComorbid && (
            <button type="button" className="chip" disabled={form.final_diagnosis.includes(c.dxComorbid)}
              onClick={() => set("final_diagnosis", `${form.final_diagnosis.trim()}${form.final_diagnosis.trim() ? "\n" : ""}${c.dxComorbid}`)}>
              + сопутствующий: {c.dxComorbid}
            </button>
          )}
        </span>
      )}
    </>,
    // 2 — Статус при выписке
    <>
      <div className="ds-sub">
        <b>Vis и ВГД при выписке</b>
        {src.dischargeVisionFrom && <span className="src-pill">из дневника {shortDate(src.dischargeVisionFrom)}</span>}
      </div>
      {visTable}
      <div className="ds-extra">
        <div className="ds-extra-row">
          <b>ВГД max / min</b>
          {(["od", "os"] as Eye[]).map((e) => (
            <span key={e} className="ds-pair">{e.toUpperCase()} {small(`vgd_${e}_max`, "max", 64)} {small(`vgd_${e}_min`, "min", 64)}</span>
          ))}
          <span className="muted">мм рт. ст.</span>
        </div>
        <div className="ds-extra-row">
          <b>Эластотонометрия</b>
          {(["od", "os"] as Eye[]).map((e) => <span key={e} className="ds-pair">{small(`elasto_${e}`, e.toUpperCase(), 110)}</span>)}
        </div>
        <div className="ds-extra-row">
          <b>Тонография по Нестерову</b>
          {(["od", "os"] as Eye[]).map((e) => (
            <span key={e} className="ds-pair">{e.toUpperCase()}
              {small(`tono_${e}_ro`, "Ро", 56)}{small(`tono_${e}_c`, "С", 56)}{small(`tono_${e}_kb`, "КБ", 56)}{small(`tono_${e}_f`, "F", 56)}
            </span>
          ))}
        </div>
        <span className="muted" style={{ fontSize: 13 }}>Эти три строки печатаются, только если заполнены.</span>
      </div>
    </>,
    // 3 — Лечение
    <>
      <label className="lbl">Лечение (печатается в эпикризе)
        <textarea className="ta" rows={4} value={form.treatment_summary} disabled={ro} placeholder="Препараты через запятую" onChange={(e) => set("treatment_summary", e.target.value)} />
      </label>
      <span className="muted" style={{ fontSize: 13 }}>Собрано из обоснования лечения в первичном осмотре и дневниках — только названия, без повторов.</span>
    </>,
    // 4 — Эпикриз
    <>
      <div className="ds-sub">
        <b>Местный статус при выписке</b>
        {src.localFrom && <span className="src-pill">из: {src.localFrom}</span>}
        <span className="muted" style={{ fontSize: 13 }}>поправьте то, что изменилось, и вставьте в эпикриз кнопками ниже</span>
      </div>
      <table className="ds-local">
        <thead><tr><th></th><th>OD</th><th>OS</th><th></th></tr></thead>
        <tbody>
          {shownRows.map((r) => (
            editingRow === r.name ? (
              <tr key={r.name}><td colSpan={4}>{rowEditor(r.name)}<button type="button" className="btn small" onClick={() => setEditingRow(null)}>Готово</button></td></tr>
            ) : (
              <tr key={r.name}>
                <th scope="row">{r.name}</th>
                <td>{r.od || <span className="muted">—</span>}</td>
                <td>{r.os || <span className="muted">—</span>}</td>
                <td>{!ro && <button type="button" className="link-btn" onClick={() => setEditingRow(r.name)}>изменить</button>}</td>
              </tr>
            )
          ))}
        </tbody>
      </table>
      {filledRows.length < localRows.length && (
        <button type="button" className="link-btn" style={{ alignSelf: "flex-start" }} onClick={() => setShowAllRows(!showAllRows)}>
          {showAllRows ? "Показать только заполненные" : `Показать все ${localRows.length} структур`}
        </button>
      )}

      <div className="lbl">Текст эпикриза
        {!ro && (
          <span className="ex-chips ds-inserts">
            <span className="muted ds-insert-label">Вставить:</span>
            <button type="button" className="chip" disabled={!src.complaints} title={src.complaints ? "" : "В первичном осмотре нет жалоб"}
              onClick={() => insert(`Со слов пациента жалобы ${src.complaints}`, false)}>Жалобы из осмотра</button>
            <button type="button" className="chip" disabled={!src.studies.length} title={src.studies.length ? "" : "Исследований нет"}
              onClick={() => setPickStudies(src.studies.map((s) => s.id))}>Исследования…</button>
            <button type="button" className="chip" disabled={!localLine("od")} onClick={() => insert(localLine("od"))}>Статус OD</button>
            <button type="button" className="chip" disabled={!localLine("os")} onClick={() => insert(localLine("os"))}>Статус OS</button>
            <button type="button" className="chip" onClick={() => insert("OU: ")}>OU:</button>
            {src.lastDiary && (
              <button type="button" className="chip" onClick={() => insert((["od", "os", "ou"] as const).filter((e) => src.lastDiary![e]).map((e) => `${e.toUpperCase()}: ${src.lastDiary![e]}`).join("\n"))}>
                Из дневника {shortDate(src.lastDiary.date)}
              </button>
            )}
          </span>
        )}
        {pickStudies && (
          <div className="ds-pick">
            {src.studies.map((s) => (
              <label key={s.id} className="ds-pick-row">
                <input type="checkbox" checked={pickStudies.includes(s.id)}
                  onChange={(e) => setPickStudies(e.target.checked ? [...pickStudies, s.id] : pickStudies.filter((x) => x !== s.id))} />
                {s.line}
              </label>
            ))}
            <span className="ds-row">
              <button type="button" className="btn small primary" disabled={!pickStudies.length}
                onClick={() => { insert("Диагностические исследования:\n" + src.studies.filter((s) => pickStudies.includes(s.id)).map((s) => s.line).join("\n")); setPickStudies(null); }}>
                Вставить {pickStudies.length} {plural(pickStudies.length, "исследование", "исследования", "исследований")}
              </button>
              <button type="button" className="btn small" onClick={() => setPickStudies(null)}>Отмена</button>
            </span>
          </div>
        )}
        <textarea ref={epicrisisRef} className="ta" rows={9} value={form.epicrisis} disabled={ro}
          onSelect={(e) => { cursor.current = e.currentTarget.selectionStart; }}
          onChange={(e) => set("epicrisis", e.target.value)} />
        <span className="muted ds-hint">На печати перед текстом будет «Находился(лась) на стационарном лечении…» и Vis/ВГД при поступлении, после — лечение и Vis/ВГД при выписке.</span>
      </div>
    </>,
    // 5 — Рекомендации
    <>
      <label className="lbl">Лечебные и трудовые рекомендации
        <textarea className="ta" rows={7} value={form.recommendations} disabled={ro} onChange={(e) => set("recommendations", e.target.value)} />
      </label>
      {!ro && src.recentRecommendations.length > 0 && (
        <div className="ds-recent">
          <span className="muted ds-insert-label">Как в прошлых выписках:</span>
          {src.recentRecommendations.map((r) => (
            <button key={r.text} type="button" className="ds-recent-item" onClick={() => set("recommendations", form.recommendations.trim() ? `${form.recommendations.trim()}\n${r.text}` : r.text)}>
              <span className="ds-recent-dx muted">{r.dx || "без диагноза"}</span>
              <span className="ds-recent-text">{r.text}</span>
            </button>
          ))}
        </div>
      )}
    </>,
    // 6 — Печать
    <>
      {!draft.saved ? (
        <p className="muted">Сначала сохраните выписку.</p>
      ) : (
        <div className="ds-print">
          <div className="ds-pages">
            {Array.from({ length: pages }, (_, i) => (
              <a key={`${i}-${stamp}`} href={api.dischargePdfUrl(caseId)} target="_blank" rel="noreferrer" className="ds-page" title="Открыть PDF">
                <img src={api.dischargePageUrl(caseId, i + 1, stamp)} alt={`Выписка, страница ${i + 1}`} />
              </a>
            ))}
          </div>
          <div className="ds-print-side">
            <label className="lbl">Принтер
              <select className="in" value={printers.chosen} onChange={(e) => setPrinters({ ...printers, chosen: e.target.value })}>
                {printers.list.length === 0 && <option value="">принтеры не найдены</option>}
                {printers.list.map((p) => <option key={p}>{p}</option>)}
              </select>
            </label>
            <label className="lbl">Экземпляров
              <span className="ds-row">
                {[1, 2, 3].map((n) => (
                  <button key={n} type="button" className={"chip" + (copies === n ? " on" : "")} onClick={() => setCopies(n)}>{n}</button>
                ))}
              </span>
            </label>
            <button type="button" className="btn primary" disabled={!printers.chosen || dirty} onClick={print}>Напечатать выписку</button>
            <a className="btn" href={api.dischargePdfUrl(caseId)} target="_blank" rel="noreferrer">Открыть PDF</a>
            {dirty && <span className="muted">Есть несохранённые правки — сохраните, чтобы напечатать новую версию.</span>}
            <hr className="ds-hr" />
            {archived ? (
              <button type="button" className="btn" onClick={unarchive}>Вернуть из архива</button>
            ) : (
              <>
                <button type="button" className="btn" onClick={toArchive} disabled={dirty}>Перенести в архив</button>
                <span className="muted" style={{ fontSize: 13 }}>История уйдёт из списка отделения. Вернуть можно из архива.</span>
              </>
            )}
          </div>
        </div>
      )}
    </>,
  ];

  return (
    <main className="page ds">
      <div className="dy-top">
        <Link to={`/case/${caseId}`} className="round-btn white" aria-label="Назад к истории">
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <div style={{ flex: "1 1 300px" }}>
          <h1>Выписка</h1>
          <div className="muted">{c.patient} · история № {c.number}{c.medCard && ` · мед. карта ${c.medCard}`}</div>
        </div>
        {draft.saved && !archived && <span className="pill tone-green">Выписка сохранена{dirty ? " · есть правки" : ""}</span>}
        {archived && <span className="pill tone-neutral">В архиве</span>}
      </div>

      {archived && (
        <div className="dy-banner">История в архиве — выписку можно только посмотреть и напечатать.
          <button type="button" className="btn small" onClick={unarchive}>Вернуть из архива</button>
        </div>
      )}
      {error && <div className="dy-banner dy-error" role="alert">{error}</div>}
      {note && <div className="dy-banner" role="status">✓ {note}</div>}

      <ol className="ds-steps" aria-label="Шаги выписки">
        {STEPS.map((title, i) => {
          const state = i === step ? "now" : i < step || (draft.saved && !dirty) ? "done" : "todo";
          return (
            <li key={title}>
              <button type="button" className={`ds-step ${state}`} aria-current={i === step ? "step" : undefined} onClick={() => goTo(i)}>
                <span className="ds-dot">{state === "done" ? "✓" : i + 1}</span>{title}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="ds-body">
        <section className="card ds-card">
          <h2>{STEPS[step]}</h2>
          {body[step]}
          <div className="ds-nav">
            {step > 0 && <button type="button" className="btn" onClick={() => setStep(step - 1)}>← {STEPS[step - 1]}</button>}
            <div style={{ flex: 1 }} />
            {!ro && step < PRINT_STEP && (
              <button type="button" className="btn" onClick={() => save()} disabled={saving}>{saving ? "Сохраняем…" : "Сохранить"}</button>
            )}
            {step < PRINT_STEP - 1 && <button type="button" className="btn primary" onClick={() => setStep(step + 1)}>{STEPS[step + 1]} →</button>}
            {step === PRINT_STEP - 1 && !ro && (
              <button type="button" className="btn primary" onClick={() => goTo(PRINT_STEP)} disabled={saving}>Сохранить и к печати →</button>
            )}
          </div>
        </section>

        <aside className="card ds-aside" aria-label="Собрано автоматически">
          <b style={{ fontSize: 17 }}>Собрано автоматически</b>
          <div className="ds-tiles">
            <div className="ds-tile"><span>Койко-дней</span><b>{days ?? "—"}</b></div>
            <div className="ds-tile green"><span>Исход</span><b>{form.outcome || "—"}</b></div>
          </div>
          <div className="ds-src">
            <div className="ds-src-head"><span className="muted">При поступлении</span><span className="src-pill">первичный осмотр</span></div>
            {admissionVision ? <VisionFractions v={admissionVision} /> : <span className="muted">в осмотре нет Vis/ВГД</span>}
          </div>
          <div className="ds-src">
            <div className="ds-src-head"><span className="muted">При выписке</span><span className="src-pill">шаг «Статус при выписке»</span></div>
            {dischargeVision ? <VisionFractions v={dischargeVision} accent /> : <span className="muted">не введено</span>}
          </div>
          <div className="ds-src">
            <div className="ds-src-head"><span className="muted">Лечение</span><span className="src-pill">осмотр + дневники</span></div>
            <span className="ds-treat">{form.treatment_summary || <span className="muted">не указано</span>}</span>
          </div>
          <div className="ds-sigs">
            <span className="muted">Подписи на печати</span>
            <label><input type="checkbox" checked={form.sig_dep_chief} disabled={ro} onChange={(e) => set("sig_dep_chief", e.target.checked)} />Зам. главного врача</label>
            <label><input type="checkbox" checked={form.sig_chief} disabled={ro} onChange={(e) => set("sig_chief", e.target.checked)} />Главный врач</label>
            <label className="muted"><input type="checkbox" checked disabled />Зав. отделением — всегда</label>
          </div>
        </aside>
      </div>
    </main>
  );
}
