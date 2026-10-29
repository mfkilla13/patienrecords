import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Study, StudyField, StudyIn, StudyList } from "../api";
import { fullDate, shortDate, todayIso } from "../format";
import "./diary.css";
import "./exam.css";
import "./studies.css";

const FREE = "Свободная форма";
const SHORT: Record<string, string> = { "Флюорография (ФГ)": "Флюорография", "Сахар крови": "Сахар крови" };

const num = (v: string) => (/^\s*\d+([.,]\d+)?\s*$/.test(v) ? parseFloat(v.replace(",", ".")) : null);

/** Outside the reference range — a hint for the doctor, never printed. */
function outOfRange(f: StudyField, value: string): boolean {
  let v = num(value);
  if (!f.range || v == null) return false;
  if (f.key === "gravity" && v < 2) v *= 1000;
  return v < f.range[0] || v > f.range[1];
}

const blank = (type: string, date: string, name = ""): StudyIn => ({ date, type, fields: {}, name, text: "" });

export function StudiesPage() {
  const { caseId = "" } = useParams();
  const [list, setList] = useState<StudyList | null>(null);
  const [form, setForm] = useState<StudyIn>(blank("ОАК", todayIso()));
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () => api.studies(caseId).then((l) => { setList(l); return l; });

  /** The next planned study that has no result yet, so a batch of analyses is typed in one go. */
  const nextFromPlan = (l: StudyList, date: string): StudyIn => {
    const wait = l.plan.find((p) => !p.done);
    if (!wait) return blank(form.type, date);
    return wait.type ? blank(wait.type, date) : l.types.includes(wait.name) ? blank(wait.name, date) : blank(FREE, date, wait.name);
  };

  useEffect(() => {
    load().then((l) => setForm(nextFromPlan(l, todayIso())), (e: Error) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const flash = (t: string) => { setNote(t); window.setTimeout(() => setNote(null), 2600); };

  const open = (s: Study) => {
    setEditing(s.id);
    setForm({ date: s.date ?? "", type: s.type, fields: { ...s.fields }, name: s.name, text: s.text });
    setError(s.unparsedDate && !s.date ? `В старой базе дата записана с ошибкой: «${s.unparsedDate}». Укажите правильную.` : null);
  };

  const reset = (l: StudyList | null = list) => {
    setEditing(null);
    setError(null);
    if (l) setForm(nextFromPlan(l, form.date || todayIso()));
  };

  const save = async () => {
    setError(null);
    if (!form.date) { setError("Укажите дату исследования."); return; }
    setSaving(true);
    try {
      await api.saveStudy(caseId, form, editing);
      const l = await load();
      flash(editing ? "Исследование изменено" : `${form.type === FREE ? form.name || "Исследование" : form.type} сохранено`);
      reset(l);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!editing || !window.confirm("Удалить это исследование?")) return;
    try {
      await api.deleteStudy(editing);
      reset(await load());
      flash("Исследование удалено");
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!list) return <main className="page sd"><p className="muted">{error ?? "Загружаем исследования…"}</p></main>;

  const ro = list.locked;
  const fields = list.forms[form.type] ?? [];
  const setField = (k: string, v: string) => setForm((f) => ({ ...f, fields: { ...f.fields, [k]: v } }));
  const planDone = list.plan.filter((p) => p.done).length;

  return (
    <main className="page sd">
      <div className="dy-top">
        <Link to={`/case/${caseId}`} className="round-btn white" aria-label="Назад к истории">
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <h1 style={{ flex: 1 }}>Исследования</h1>
        <Link to={`/case/${caseId}/prescriptions`} className="btn">Лист назначений</Link>
      </div>
      {ro && <div className="dy-banner">История в архиве — исследования можно только посмотреть.</div>}
      {note && <div className="dy-banner" role="status">✓ {note}</div>}

      <div className="sd-body">
        <section className="sd-list" aria-label="Исследования пациента">
          {list.plan.length > 0 && (
            <div className={"sd-plan" + (planDone === list.plan.length ? " done" : "")}>
              <b>План из первичного осмотра: {planDone} из {list.plan.length} готово</b>
              <span className="sd-plan-items">
                {list.plan.map((p) => (
                  <button key={p.name} type="button" className={"sd-plan-item" + (p.done ? "" : " wait")} disabled={p.done || ro}
                    onClick={() => { setEditing(null); setForm(p.type ? blank(p.type, form.date) : list.types.includes(p.name) ? blank(p.name, form.date) : blank(FREE, form.date, p.name)); }}>
                    {p.done ? `✓ ${p.name}` : `ждём: ${p.name}`}
                  </button>
                ))}
              </span>
            </div>
          )}
          {list.studies.map((s) => (
            <button key={s.id} type="button" className={"sd-item" + (editing === s.id ? " on" : "")} onClick={() => open(s)}>
              <span className="sd-item-head">
                <span className="sd-date">{s.date ? shortDate(s.date) : "без даты"}</span>
                <b>{SHORT[s.name] ?? s.name}</b>
                <span style={{ flex: 1 }} />
                {s.flags.length > 0 ? <span className="pill sm tone-amber">{s.flags.join(" · ")}</span> : null}
              </span>
              <span className="sd-result">{s.result || <span className="muted">без результата</span>}</span>
              {s.unparsedDate && !s.date && <span className="sd-warn">Дата в старой базе с ошибкой: «{s.unparsedDate}» — откройте и исправьте</span>}
            </button>
          ))}
          {list.studies.length === 0 && <p className="muted">Исследований пока нет.</p>}
        </section>

        {!ro && (
          <aside className="card sd-form" aria-label={editing ? "Изменить исследование" : "Новое исследование"}>
            <div className="sd-form-head">
              <b>{editing ? "Изменить исследование" : "Новое исследование"}</b>
              {editing && <button type="button" className="link-btn" onClick={() => reset()}>+ новое</button>}
            </div>
            <div className="lbl">Вид
              <span className="ex-chips">
                {list.types.map((t) => (
                  <button key={t} type="button" className={"chip" + (form.type === t ? " on" : "")} aria-pressed={form.type === t}
                    onClick={() => setForm((f) => ({ ...f, type: t, fields: t === f.type ? f.fields : {} }))}>{SHORT[t] ?? t}</button>
                ))}
              </span>
            </div>
            <div className="sd-row">
              <label className="lbl" style={{ width: 190 }}>Дата
                <input className="in" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
              </label>
              {form.date && <span className="muted" style={{ alignSelf: "flex-end", paddingBottom: 12 }}>{fullDate(form.date)}</span>}
            </div>

            {form.type === FREE ? (
              <>
                <label className="lbl">Название
                  <input className="in" list="sd-names" value={form.name} placeholder="например: Суточное ВГД" onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </label>
                <label className="lbl">Результаты
                  <textarea className="ta" rows={5} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
                </label>
                <datalist id="sd-names">{list.plan.filter((p) => !p.type).map((p) => <option key={p.name} value={p.name} />)}</datalist>
              </>
            ) : (
              <div className="sd-grid">
                {fields.map((f) => {
                  const v = form.fields[f.key] ?? "";
                  const wide = f.kind === "text" || f.kind.startsWith("choice:");
                  return (
                    <label key={f.key} className={"lbl" + (wide ? " sd-wide" : "")}>
                      <span>{f.label}{f.unit && `, ${f.unit}`} {f.range && <span className="sd-ref">{String(f.range[0]).replace(".", ",")}–{String(f.range[1]).replace(".", ",")}</span>}</span>
                      {f.kind === "text" ? (
                        <textarea className="ta" rows={f.key === "results" ? 5 : 2} value={v} onChange={(e) => setField(f.key, e.target.value)} />
                      ) : f.kind.startsWith("choice:") ? (
                        <span className="ex-chips">
                          {f.kind.slice(7).split("|").map((o) => (
                            <button key={o} type="button" className={"chip" + (v === o ? " on" : "")} aria-pressed={v === o} onClick={() => setField(f.key, v === o ? "" : o)}>{o}</button>
                          ))}
                          <input className="in ex-add" placeholder="или своё" value={f.kind.slice(7).split("|").includes(v) ? "" : v} onChange={(e) => setField(f.key, e.target.value)} />
                        </span>
                      ) : (
                        <input className={"in" + (outOfRange(f, v) ? " changed" : "")} inputMode={f.range ? "decimal" : undefined} value={v}
                          onChange={(e) => setField(f.key, e.target.value)} />
                      )}
                    </label>
                  );
                })}
              </div>
            )}

            {error && <div className="dy-banner dy-error" role="alert">{error}</div>}
            <div className="sd-actions">
              <span className="muted sd-hint">{fields.some((f) => f.range) && form.type !== FREE ? "Значения вне нормы подсвечиваются — это подсказка, на печать не идёт." : ""}</span>
              {editing && <button type="button" className="btn" onClick={remove}>Удалить</button>}
              <button type="button" className="btn primary" onClick={save} disabled={saving}>{saving ? "Сохраняем…" : "Сохранить"}</button>
            </div>
          </aside>
        )}
      </div>
    </main>
  );
}
