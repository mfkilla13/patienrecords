import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Prescription, PrescriptionList } from "../api";
import { shortDate, todayIso } from "../format";
import "./diary.css";
import "./exam.css";
import "./studies.css";

const CAT_SHORT: Record<string, [string, string]> = {
  stol: ["режим", "tone-neutral"], exam: ["обсл.", "tone-blue"], drugs: ["преп.", "tone-green"], lfk: ["ЛФК", "tone-violet"],
};

interface Draft { category: string; names: string[]; own: string; method: string; freq: string; from: string; to: string }
const empty = (category: string): Draft => ({ category, names: [], own: "", method: "", freq: "", from: todayIso(), to: "" });

export function PrescriptionsPage() {
  const { caseId = "" } = useParams();
  const [list, setList] = useState<PrescriptionList | null>(null);
  const [onlyActive, setOnlyActive] = useState(false);
  const [d, setD] = useState<Draft>(empty("drugs"));
  const [editing, setEditing] = useState<Prescription | null>(null);
  const [editTemplates, setEditTemplates] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = () => api.prescriptions(caseId).then(setList, (e: Error) => setError(e.message));
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [caseId]);

  const flash = (t: string) => { setNote(t); window.setTimeout(() => setNote(null), 2600); };
  const run = async (fn: () => Promise<unknown>, done: string) => {
    setError(null);
    try {
      await fn();
      await load();
      flash(done);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!list) return <main className="page sd"><p className="muted">{error ?? "Загружаем назначения…"}</p></main>;

  const ro = list.locked;
  const plain = list.plain.includes(editing?.category ?? d.category);
  const names = [...d.names, ...(d.own.trim() && !editing ? [d.own.trim()] : [])];
  const templates = list.templates[d.category] ?? [];
  const shown = list.items.filter((x) => !onlyActive || x.active);

  const toggle = (name: string) => setD({ ...d, names: d.names.includes(name) ? d.names.filter((x) => x !== name) : [...d.names, name] });

  const saveTemplates = (next: string[]) =>
    run(() => api.savePrescriptionTemplates({ ...list.templates, [d.category]: next }), "Шаблоны сохранены");

  const add = () => run(async () => {
    await api.addPrescriptions(caseId, { category: d.category, names, method: d.method, freq: d.freq, date_from: d.from || null, date_to: d.to || null });
    setD({ ...empty(d.category), method: d.method, freq: d.freq, from: d.from });
  }, `Добавлено: ${names.join(", ")}`);

  const saveEdit = () => editing && run(async () => {
    await api.updatePrescription(editing.id, { name: d.own.trim() || editing.name, method: d.method, freq: d.freq, date_from: d.from || null, date_to: d.to || null });
    setEditing(null);
    setD(empty(editing.category));
  }, "Назначение изменено");

  const startEdit = (x: Prescription) => {
    setEditing(x);
    setD({ category: x.category, names: [], own: x.name, method: x.method, freq: x.freq, from: x.dateFrom ?? "", to: x.dateTo ?? "" });
  };

  const choiceRow = (label: string, options: string[], value: string, set: (v: string) => void) => (
    <div className="lbl">{label}
      <span className="ex-chips">
        {options.map((o) => (
          <button key={o} type="button" className={"chip" + (value === o ? " on" : "")} aria-pressed={value === o} onClick={() => set(value === o ? "" : o)}>{o}</button>
        ))}
        <input className="in ex-add" placeholder="своё" value={options.includes(value) ? "" : value} onChange={(e) => set(e.target.value)} />
      </span>
    </div>
  );

  return (
    <main className="page sd">
      <div className="dy-top">
        <Link to={`/case/${caseId}`} className="round-btn white" aria-label="Назад к истории">
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <h1 style={{ flex: 1 }}>Лист назначений</h1>
        <Link to={`/case/${caseId}/studies`} className="btn">Исследования</Link>
      </div>
      {ro && <div className="dy-banner">История в архиве — назначения можно только посмотреть.</div>}
      {note && <div className="dy-banner" role="status">✓ {note}</div>}
      {error && <div className="dy-banner dy-error" role="alert">{error}</div>}

      <div className="sd-body">
        <section className="card rx-list" aria-label="Лист назначений">
          <div className="rx-head">
            <b style={{ fontSize: 18 }}>Назначено</b>
            <span className="pill sm tone-neutral">{list.items.length}</span>
            <span style={{ flex: 1 }} />
            <span className="ex-chips">
              <button type="button" className={"chip" + (onlyActive ? " on" : "")} onClick={() => setOnlyActive(true)}>Действующие</button>
              <button type="button" className={"chip" + (!onlyActive ? " on" : "")} onClick={() => setOnlyActive(false)}>Все</button>
            </span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="rx-table">
              <thead><tr><th>Назначение</th><th>Способ</th><th>Кратность</th><th>Назначено</th><th>Отменено</th><th></th></tr></thead>
              <tbody>
                {shown.map((x) => (
                  <tr key={x.id} className={(x.active ? "" : "off") + (editing?.id === x.id ? " on" : "")}>
                    <td>
                      <span className="rx-name">
                        <span className={"pill sm " + (CAT_SHORT[x.category]?.[1] ?? "tone-neutral")}>{CAT_SHORT[x.category]?.[0] ?? "—"}</span>
                        <b>{x.name}</b>
                      </span>
                    </td>
                    <td>{x.method || "—"}</td>
                    <td>{x.freq || "—"}</td>
                    <td className="num">{shortDate(x.dateFrom)}</td>
                    <td className="num">{x.dateTo ? shortDate(x.dateTo) : "—"}</td>
                    <td className="rx-acts">
                      {!ro && (
                        <>
                          {x.active && <button type="button" className="link-btn" onClick={() => run(() => api.cancelPrescription(x.id), `Отменено: ${x.name}`)}>отменить</button>}
                          <button type="button" className="link-btn" onClick={() => startEdit(x)}>изменить</button>
                          <button type="button" className="link-btn rx-del" aria-label={`Удалить ${x.name}`}
                            onClick={() => window.confirm(`Удалить «${x.name}» из листа? (Отмена назначения — кнопка «отменить».)`) && run(() => api.deletePrescription(x.id), "Удалено")}>×</button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {shown.length === 0 && <p className="muted" style={{ padding: "0 10px" }}>{onlyActive ? "Действующих назначений нет." : "Назначений пока нет."}</p>}
        </section>

        {!ro && (
          <aside className="card sd-form" aria-label={editing ? "Изменить назначение" : "Добавить назначение"}>
            <div className="sd-form-head">
              <b>{editing ? "Изменить назначение" : "Добавить назначение"}</b>
              {editing && <button type="button" className="link-btn" onClick={() => { setEditing(null); setD(empty(d.category)); }}>+ новое</button>}
            </div>
            {!editing && (
              <div className="seg" role="tablist">
                {Object.entries(list.categories).map(([k, label]) => (
                  <button key={k} type="button" role="tab" aria-selected={d.category === k} className={d.category === k ? "on" : ""}
                    onClick={() => { setD({ ...empty(k), from: d.from }); setEditTemplates(false); }}>{label}</button>
                ))}
              </div>
            )}
            <input className="in" placeholder={editing ? "Назначение" : "Своё назначение (или выберите ниже)"} value={d.own}
              onChange={(e) => setD({ ...d, own: e.target.value })}
              onKeyDown={(e) => { if (e.key === "Enter" && d.own.trim() && !editing) { e.preventDefault(); setD((x) => ({ ...x, own: "", names: x.names.includes(d.own.trim()) ? x.names : [...x.names, d.own.trim()] })); } }} />
            {!editing && (
              <div className="lbl">
                <span className="sd-row" style={{ justifyContent: "space-between" }}>
                  Шаблоны — можно выбрать несколько
                  <button type="button" className="link-btn" style={{ fontSize: 13 }} onClick={() => setEditTemplates(!editTemplates)}>{editTemplates ? "готово" : "изменить шаблоны"}</button>
                </span>
                <span className="ex-chips">
                  {templates.map((t) => editTemplates ? (
                    <button key={t} type="button" className="chip" onClick={() => saveTemplates(templates.filter((x) => x !== t))} aria-label={`Убрать шаблон ${t}`}>{t} ×</button>
                  ) : (
                    <button key={t} type="button" className={"chip" + (d.names.includes(t) ? " on" : "")} aria-pressed={d.names.includes(t)} onClick={() => toggle(t)}>{d.names.includes(t) ? "✓ " : ""}{t}</button>
                  ))}
                  {d.names.filter((n) => !templates.includes(n)).map((n) => (
                    <button key={n} type="button" className="chip on" onClick={() => toggle(n)}>✓ {n}</button>
                  ))}
                  {d.own.trim() && !templates.includes(d.own.trim()) && (
                    <button type="button" className="chip ex-plus-text" onClick={() => saveTemplates([...templates, d.own.trim()])}>+ «{d.own.trim()}» в шаблоны</button>
                  )}
                </span>
              </div>
            )}
            {!plain && choiceRow("Способ", list.methods, d.method, (v) => setD({ ...d, method: v }))}
            {!plain && choiceRow("Кратность", list.freqs, d.freq, (v) => setD({ ...d, freq: v }))}
            <div className="sd-row">
              <label className="lbl" style={{ flex: 1 }}>Назначено <input className="in" type="date" value={d.from} onChange={(e) => setD({ ...d, from: e.target.value })} /></label>
              <label className="lbl" style={{ flex: 1 }}>Отменено <input className="in" type="date" value={d.to} onChange={(e) => setD({ ...d, to: e.target.value })} /></label>
            </div>
            <div className="sd-actions">
              <span className="muted sd-hint">{!editing && names.length ? `Будет добавлено: ${names.length}` : ""}</span>
              {editing ? (
                <button type="button" className="btn primary" onClick={saveEdit}>Сохранить</button>
              ) : (
                <button type="button" className="btn primary" disabled={!names.length} onClick={add}>Добавить в лист</button>
              )}
            </div>
          </aside>
        )}
      </div>
    </main>
  );
}
