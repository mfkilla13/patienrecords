import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, CaseCard, DiaryData, DiaryDraft } from "../api";
import { VisionFractions } from "../components/VisionFractions";
import {
  basisLines, COPIED_FIELDS, copyFrom, emptyDiary, GENERAL_STATES, hasMeasurements, toVision,
  TREATMENT_PRESETS, VIS_STATUSES, WITH_CORRECTION,
} from "../diary";
import { fullDate, shortDate, todayIso } from "../format";
import { PickInput, PickKind } from "../components/PickInput";
import "./diary.css";

type Field = keyof Omit<DiaryData, "basis">;

/** Ends the text with a period unless it already has punctuation. */
const sentence = (s: string) => (/[.!?]$/.test(s.trim()) ? s.trim() : `${s.trim()}.`);

export function DiaryPage() {
  const { caseId = "", recordId } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(recordId);

  const [card, setCard] = useState<CaseCard | null>(null);
  const [draft, setDraft] = useState<DiaryDraft | null>(null);
  const [form, setForm] = useState<DiaryData>(() => emptyDiary(todayIso()));
  const [copied, setCopied] = useState<{ date: string; values: Partial<DiaryData> } | null>(null);
  const [locked, setLocked] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.caseCard(caseId).then(setCard, (e: Error) => setError(e.message));
    if (recordId) {
      api.diary(recordId).then(
        (d) => {
          setForm({ ...emptyDiary(d.data.date), ...d.data });
          if (d.printedAt) setLocked(`Дневник напечатан ${shortDate(d.printedAt)} — изменить его нельзя, чтобы он не разошёлся с бумагой.`);
        },
        (e: Error) => setError(e.message),
      );
    }
  }, [caseId, recordId]);

  useEffect(() => {
    api.diaryDraft(caseId, form.date).then(setDraft, () => setDraft(null));
  }, [caseId, form.date]);

  const set = (k: Field, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const setStatus = (eye: "od" | "os", v: string) =>
    setForm((f) => ({
      ...f,
      [`vis_correction_${eye}`]: v,
      ...(v === WITH_CORRECTION ? {} : { [`vis_${eye}_corr`]: "", [`vis_${eye}_result`]: "" }),
    }));

  const copyPrevious = () => {
    if (!draft?.previous) return;
    const next = copyFrom(draft.previous.data, form.date);
    next.time = form.time;
    setForm(next);
    setCopied({ date: draft.previous.date, values: Object.fromEntries(COPIED_FIELDS.map((k) => [k, next[k]])) });
  };

  /** After a copy, fields the doctor has changed are highlighted. */
  const changed = (k: Field) => copied !== null && k in copied.values && copied.values[k] !== form[k];
  const prev = draft?.previous?.data;
  // Previous values are shown as grey placeholders; narrow Vis/ВГД fields get the bare value.
  const hint = (k: Field) => (prev && prev[k] ? (k.startsWith("vis_") || k.startsWith("vgd_") ? prev[k] : `вчера ${prev[k]}`) : "");
  const vision = useMemo(() => toVision(form), [form]);
  const basis = basisLines(form.basis);
  const active = card?.status === "active";
  const readOnly = Boolean(locked) || (card !== null && !active);

  const save = async () => {
    setError(null);
    if (!hasMeasurements(form) && !window.confirm("Vis и ВГД не введены. Сохранить дневник без них?")) return;
    setSaving(true);
    try {
      if (recordId) await api.updateDiary(recordId, form);
      else await api.createDiary(caseId, form);
      navigate(`/case/${caseId}`);
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  };

  const input = (k: Field, extra?: { placeholder?: string; width?: number; inputMode?: "decimal" | "numeric"; pick?: PickKind }) => extra?.pick ? (
    <PickInput
      kind={extra.pick}
      className={"in" + (changed(k) ? " changed" : "")}
      value={form[k]}
      onChange={(v) => set(k, v)}
      placeholder={extra.placeholder}
      inputMode={extra.inputMode}
      style={extra.width ? { width: extra.width } : undefined}
      disabled={readOnly}
    />
  ) : (
    <input
      className={"in" + (changed(k) ? " changed" : "")}
      value={form[k]}
      onChange={(e) => set(k, e.target.value)}
      placeholder={extra?.placeholder}
      inputMode={extra?.inputMode}
      style={extra?.width ? { width: extra.width } : undefined}
      disabled={readOnly}
    />
  );

  const p = card?.patient;
  const todayExists = !editing && draft?.today;

  return (
    <main className="page dy">
      <div className="dy-top">
        <Link to={`/case/${caseId}`} className="round-btn white" aria-label="Назад к истории">
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <div style={{ flex: "1 1 300px" }}>
          <h1>{editing ? "Дневник — правка" : "Дневник"}</h1>
          <div className="muted">
            {p ? [p.surname, p.name, p.patronymic].filter(Boolean).join(" ") : "…"}
            {card && ` · история № ${card.number}`}
            {card?.day != null && ` · день ${card.day}`}
          </div>
        </div>
        <Link to={`/case/${caseId}`} className="btn">Отмена</Link>
        <button type="button" className="btn primary" onClick={save} disabled={saving || readOnly}>
          {saving ? "Сохраняем…" : "Сохранить дневник"}
        </button>
      </div>

      {error && <div className="dy-banner dy-error" role="alert">{error}</div>}
      {locked && <div className="dy-banner">{locked}</div>}
      {card && !active && <div className="dy-banner">История выписана — дневники только для чтения.</div>}
      {todayExists && (
        <div className="dy-banner">
          <span style={{ flex: 1 }}>Дневник за {fullDate(form.date)} уже есть.</span>
          <Link to={`/case/${caseId}/diary/${draft!.today!.recordId}`} className="btn white small">Открыть его</Link>
        </div>
      )}
      {!readOnly && !editing && draft?.previous && !copied && (
        <div className="dy-banner dy-copy">
          <span style={{ flex: 1 }}>
            Есть дневник от <b>{shortDate(draft.previous.date)}</b>. Скопировать текст, лечение и статусы зрения?
            Vis, ВГД, АД и пульс не копируются — их нужно ввести заново.
          </span>
          <button type="button" className="btn white small" onClick={copyPrevious}>
            Скопировать вчерашний
          </button>
        </div>
      )}
      {copied && (
        <div className="dy-banner dy-copy">
          <span style={{ flex: 1 }}>
            <b>Заполнено по дневнику от {shortDate(copied.date)}.</b> Изменённые поля подсвечены, измерения введите заново.
          </span>
          <button type="button" className="btn white small" onClick={() => { setForm(emptyDiary(form.date)); setCopied(null); }}>
            Очистить форму
          </button>
        </div>
      )}

      <div className="dy-body">
        <div className="dy-form">
          <section className="card dy-card dy-grid5">
            <label className="lbl">Дата
              <input className="in" type="date" value={form.date} onChange={(e) => set("date", e.target.value)} disabled={readOnly || editing} />
            </label>
            <label className="lbl">Время {input("time", { placeholder: "сейчас" })}</label>
            <label className="lbl">АД, мм рт. ст. {input("bp", { placeholder: hint("bp"), pick: "bp" })}</label>
            <label className="lbl">ЧСС, уд/мин {input("hr", { placeholder: hint("hr"), inputMode: "numeric", pick: "rate" })}</label>
            <label className="lbl">Пульс, уд/мин {input("pulse", { placeholder: hint("pulse"), inputMode: "numeric", pick: "rate" })}</label>
            <div className="lbl" style={{ gridColumn: "span 3" }}>Общее состояние
              <span className={"seg" + (changed("general_state") ? " changed" : "")} role="radiogroup">
                {GENERAL_STATES.map((s) => (
                  <button key={s} type="button" role="radio" aria-checked={form.general_state === s}
                    className={form.general_state === s ? "on" : ""} onClick={() => set("general_state", s)} disabled={readOnly}>
                    {s}
                  </button>
                ))}
              </span>
            </div>
            <label className="lbl" style={{ gridColumn: "span 2" }}>Жалобы
              {input("complaints", { placeholder: "если пусто — в печать не попадёт" })}
            </label>
          </section>

          <section className="card dy-card">
            <h2>Офтальмологический статус</h2>
            <table className="dy-vis">
              <thead>
                <tr><th style={{ width: 44 }}></th><th>Vis</th><th>Статус</th><th>Коррекция = результат</th><th>ВГД</th></tr>
              </thead>
              <tbody>
                {(["od", "os"] as const).map((eye) => {
                  const corrected = form[`vis_correction_${eye}`] === WITH_CORRECTION;
                  return (
                    <tr key={eye}>
                      <td className="dy-eye">{eye.toUpperCase()}</td>
                      <td>{input(`vis_${eye}`, { width: 90, placeholder: hint(`vis_${eye}`), inputMode: "decimal", pick: "vis" })}</td>
                      <td>
                        <select className="in" style={{ width: 200 }} value={form[`vis_correction_${eye}`]}
                          onChange={(e) => setStatus(eye, e.target.value)} disabled={readOnly}>
                          {VIS_STATUSES.map((s) => <option key={s}>{s}</option>)}
                        </select>
                      </td>
                      <td>
                        {corrected ? (
                          <span className="dy-corr">
                            {input(`vis_${eye}_corr`, { width: 100, placeholder: "+2,0", pick: "corr" })} = {input(`vis_${eye}_result`, { width: 80, pick: "vis" })}
                          </span>
                        ) : (
                          <span className="muted" style={{ fontSize: 14 }}>только при «с коррекцией»</span>
                        )}
                      </td>
                      <td>{input(`vgd_${eye}`, { width: 80, placeholder: hint(`vgd_${eye}`), inputMode: "numeric", pick: "vgd" })}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <label className="lbl">OD {input("od_text")}</label>
            <label className="lbl">OS {input("os_text")}</label>
            <label className="lbl">OU {input("ou_text", { placeholder: "при необходимости" })}</label>
          </section>

          <section className="card dy-card">
            <div className="dy-row">
              <h2 style={{ marginRight: 8 }}>Лечение</h2>
              {TREATMENT_PRESETS.map((t) => (
                <button key={t} type="button" className={"chip" + (form.treatment.replace(/\.$/, "") === t ? " on" : "")}
                  onClick={() => set("treatment", t)} disabled={readOnly}>
                  {t}
                </button>
              ))}
            </div>
            <textarea className={"ta" + (changed("treatment") ? " changed" : "")} rows={2} value={form.treatment}
              onChange={(e) => set("treatment", e.target.value)} disabled={readOnly} />
            {basis.length > 0 && (
              <div className="dy-basis">
                <span className="muted">Обоснование лечения (из прошлого дневника):</span>
                {basis.map((b) => <span key={b}>{b}</span>)}
              </div>
            )}
            <label className="lbl">Для выписки <span className="muted" style={{ fontWeight: 400 }}>заметка попадёт в выписку</span>
              <textarea className="ta" rows={2} value={form.discharge_note} onChange={(e) => set("discharge_note", e.target.value)}
                placeholder="например: швы сняты" disabled={readOnly} />
            </label>
          </section>
        </div>

        <aside className="card dy-preview" aria-label="Предпросмотр">
          <b>Так будет на бумаге</b>
          <div className="dy-paper-wrap">
            <div className="dy-paper">
              <div>
                <b>{fullDate(form.date)}</b>
                {form.bp && <div>АД {form.bp} мм рт. ст.</div>}
                {form.hr && <div>ЧСС {form.hr} уд/мин</div>}
                {form.pulse && <div>Пульс {form.pulse} уд/мин</div>}
              </div>
              <div>
                {sentence(`Общее состояние ${form.general_state}`)}
                {form.complaints && ` ${sentence(`Жалобы ${form.complaints}`)}`}
                {vision && <div className="dy-paper-vis"><VisionFractions v={vision} /></div>}
                {form.od_text && <div>OD: {form.od_text}</div>}
                {form.os_text && <div>OS: {form.os_text}</div>}
                {form.ou_text && <div>OU: {form.ou_text}</div>}
                {(form.treatment || basis.length > 0) && <div>Лечение {[form.treatment, ...basis].filter(Boolean).join(" ")}</div>}
                {form.discharge_note && <div>{form.discharge_note}</div>}
                <div className="dy-sign">Подпись ________</div>
              </div>
            </div>
          </div>
          <span className="muted" style={{ fontSize: 14 }}>После сохранения запись попадёт в «Печать новых».</span>
        </aside>
      </div>
    </main>
  );
}
