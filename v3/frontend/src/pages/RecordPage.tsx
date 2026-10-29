import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, CaseCard, RecordOptions, SimpleKind, SimpleRecordIn } from "../api";
import { fullDate, todayIso } from "../format";
import "./diary.css";
import "./record.css";

function Header({ card, title, children }: { card: CaseCard | null; title: string; children?: React.ReactNode }) {
  const p = card?.patient;
  return (
    <div className="dy-top">
      <Link to={card ? `/case/${card.caseId}` : "/"} className="round-btn white" aria-label="Назад к истории">
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
      </Link>
      <div style={{ flex: "1 1 300px" }}>
        <h1>{title}</h1>
        <div className="muted">
          {p ? [p.surname, p.name, p.patronymic].filter(Boolean).join(" ") : "…"}
          {card && ` · история № ${card.number}`}
          {card?.day != null && ` · день ${card.day}`}
        </div>
      </div>
      {children}
    </div>
  );
}

/** «Новая запись»: what kind of record to add to the case. */
export function NewRecordPage() {
  const { caseId = "" } = useParams();
  const [card, setCard] = useState<CaseCard | null>(null);
  const [opts, setOpts] = useState<RecordOptions | null>(null);
  useEffect(() => {
    api.caseCard(caseId).then(setCard, () => undefined);
    api.recordOptions().then(setOpts, () => undefined);
  }, [caseId]);

  const hasExam = card?.records.some((r) => r.kind === "primary_exam");
  const base = `/case/${caseId}`;
  const tiles: { to: string; title: string; sub: string; main?: boolean }[] = [
    { to: `${base}/diary`, title: "Дневник", sub: "Vis, ВГД, АД, статус, лечение", main: true },
    { to: `${base}/record/new/operation_protocol`, title: "Протокол операции", sub: "из шаблона или своим текстом", main: true },
    ...(hasExam ? [] : [{ to: `${base}/exam`, title: "Первичный осмотр", sub: "ещё не заполнен", main: true }]),
    ...(opts?.textTitles ?? []).map((t) => ({ to: `${base}/record/new/other?title=${encodeURIComponent(t)}`, title: t, sub: "текстом" })),
    { to: `${base}/record/new/other`, title: "Другая запись", sub: "своё название и текст" },
    { to: `${base}/discharge`, title: "Выписка", sub: "выписной эпикриз" },
  ];
  const archived = card?.status === "archived";

  return (
    <main className="page dy">
      <Header card={card} title="Новая запись" />
      {archived && <div className="dy-banner">История в архиве — сначала верните её из архива.</div>}
      <div className="nr-tiles">
        {tiles.map((t) => (
          <Link key={t.to} to={archived ? base : t.to} className={"card nr-tile" + (t.main ? " main" : "")} aria-disabled={archived}>
            <b>{t.title}</b>
            <span className="muted">{t.sub}</span>
          </Link>
        ))}
      </div>
    </main>
  );
}

const EMPTY: SimpleRecordIn = { date: todayIso(), time: "", title: "", text: "" };

/** The operation protocol or a plain text record: new (/record/new/:kind) or changed (/record/:recordId). */
export function RecordPage() {
  const { caseId = "", recordId, kind: kindParam } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [card, setCard] = useState<CaseCard | null>(null);
  const [opts, setOpts] = useState<RecordOptions | null>(null);
  const [kind, setKind] = useState<SimpleKind>(kindParam === "operation_protocol" ? "operation_protocol" : "other");
  const [form, setForm] = useState<SimpleRecordIn>({ ...EMPTY, title: params.get("title") ?? "" });
  const [locked, setLocked] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const isProtocol = kind === "operation_protocol";

  useEffect(() => {
    api.caseCard(caseId).then(setCard, (e: Error) => setError(e.message));
    api.recordOptions().then((o) => {
      setOpts(o);
      if (!recordId) setForm((f) => (f.time ? f : { ...f, time: o.now }));
    }, () => undefined);
    if (recordId) {
      api.record(recordId).then((r) => {
        setKind(r.kind);
        setForm({ date: r.date, time: r.time, title: r.title, text: r.text });
        if (!r.editable) setLocked(r.printedAt ? `Запись напечатана ${fullDate(r.printedAt)} — её нельзя менять.` : "Запись из 2.9 без полей — её нельзя менять.");
      }, (e: Error) => setError(e.message));
    }
  }, [caseId, recordId]);

  useEffect(() => {
    if (card && card.status === "archived") setLocked("История в архиве — сначала верните её из архива.");
  }, [card]);

  const set = (k: keyof SimpleRecordIn, v: string) => {
    setForm((f) => ({ ...f, [k]: v }));
    setError(null);
    setNote(null);
  };
  const readOnly = !!locked;

  const useTemplate = (name: string, description: string) => {
    if (form.text.trim() && form.text.trim() !== description.trim()
        && !window.confirm("Заменить описание операции текстом шаблона?")) return;
    setForm((f) => ({ ...f, title: name, text: description }));
    setNote(null);
    textRef.current?.focus();
  };

  const saveTemplate = async () => {
    if (!form.title.trim()) return setError("Чтобы сохранить шаблон, напишите название операции.");
    const exists = opts?.templates.some((t) => t.name.toLowerCase() === form.title.trim().toLowerCase());
    if (exists && !window.confirm(`Шаблон «${form.title.trim()}» уже есть. Заменить его описание этим текстом?`)) return;
    try {
      const templates = await api.saveOperationTemplate({ name: form.title, description: form.text });
      setOpts((o) => (o ? { ...o, templates } : o));
      setNote("Шаблон сохранён — он появится в списке для следующих операций.");
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const dropTemplate = async (name: string) => {
    if (!window.confirm(`Убрать шаблон «${name}»?`)) return;
    const templates = await api.deleteOperationTemplate(name);
    setOpts((o) => (o ? { ...o, templates } : o));
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.saveRecord(caseId, kind, form, recordId ?? null);
      navigate(`/case/${caseId}`);
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!recordId || !window.confirm("Удалить эту запись?")) return;
    try {
      await api.deleteRecord(recordId);
      navigate(`/case/${caseId}`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const title = isProtocol ? "Протокол операции" : form.title.trim() || "Запись";

  return (
    <main className="page dy">
      <Header card={card} title={recordId ? `${title} — правка` : title}>
        {recordId && !readOnly && <button type="button" className="btn" onClick={remove}>Удалить</button>}
        <Link to={`/case/${caseId}`} className="btn">Отмена</Link>
        <button type="button" className="btn primary" onClick={save} disabled={saving || readOnly}>
          {saving ? "Сохраняем…" : "Сохранить"}
        </button>
      </Header>

      {error && <div className="dy-banner dy-error" role="alert">{error}</div>}
      {locked && <div className="dy-banner">{locked}</div>}

      <div className="dy-body">
        <section className="card dy-card dy-form" aria-label={title}>
          <div className="dy-row">
            <label className="lbl">Дата
              <input className="in" type="date" value={form.date} max={todayIso()} disabled={readOnly}
                onChange={(e) => set("date", e.target.value)} style={{ width: 170 }} />
            </label>
            <label className="lbl">Время
              <input className="in" type="time" value={form.time} disabled={readOnly}
                onChange={(e) => set("time", e.target.value)} style={{ width: 120 }} />
            </label>
          </div>

          {isProtocol ? (
            <label className="lbl">Название операции
              <input className="in" value={form.title} disabled={readOnly} maxLength={300}
                placeholder="например: Факоэмульсификация катаракты с имплантацией ИОЛ OD"
                onChange={(e) => set("title", e.target.value)} />
            </label>
          ) : (
            <label className="lbl">Что это за запись
              <input className="in" value={form.title} disabled={readOnly} maxLength={300} list="nr-titles"
                placeholder="например: Консилиум" onChange={(e) => set("title", e.target.value)} />
              <datalist id="nr-titles">{opts?.textTitles.map((t) => <option key={t} value={t} />)}</datalist>
            </label>
          )}

          <label className="lbl">{isProtocol ? "Ход операции" : "Текст"}
            <textarea ref={textRef} className="ta nr-text" rows={14} value={form.text} disabled={readOnly} maxLength={20000}
              onChange={(e) => set("text", e.target.value)}
              placeholder={isProtocol ? "На листе будет только этот текст, без названия поля." : ""} />
          </label>
          <span className="st-help">
            {isProtocol
              ? "На листе: «Протокол операции», название жирным, текст и подписи хирурга и операционной сестры."
              : "На листе: название записи, текст и подпись. Печатается вместе с дневниками."}
          </span>
          {note && <span className="st-status ok" role="status">{note}</span>}
        </section>

        {isProtocol && (
          <aside className="card dy-card nr-templates" aria-label="Шаблоны операций">
            <h2>Шаблоны операций</h2>
            <span className="st-help">Нажмите — название и ход операции подставятся, дальше их можно поправить.</span>
            {(opts?.templates ?? []).map((t) => (
              <div key={t.name} className="nr-tpl">
                <button type="button" className="nr-tpl-use" disabled={readOnly} onClick={() => useTemplate(t.name, t.description)}>
                  <b>{t.name}</b>
                  <span className="muted">{t.description.slice(0, 110)}{t.description.length > 110 ? "…" : ""}</span>
                </button>
                <button type="button" className="dc-icon del" aria-label={`Убрать шаблон ${t.name}`} onClick={() => dropTemplate(t.name)}>×</button>
              </div>
            ))}
            {opts && opts.templates.length === 0 && <span className="muted">Шаблонов пока нет.</span>}
            <button type="button" className="btn" disabled={readOnly || !form.title.trim()} onClick={saveTemplate}>
              Сохранить эту операцию как шаблон
            </button>
          </aside>
        )}
      </div>
    </main>
  );
}
