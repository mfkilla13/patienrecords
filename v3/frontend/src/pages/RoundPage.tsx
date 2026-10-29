import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, DiaryData, RoundRow } from "../api";
import { copyFrom, emptyDiary, hasMeasurements, TREATMENT_PRESETS, WITH_CORRECTION, fillYesterday, Measurement, stillYesterday, yesterdayQuestion } from "../diary";
import { initials, longToday, plural, shortDate, todayIso } from "../format";
import { PickInput, PickKind } from "../components/PickInput";
import "./round.css";

type RowState = {
  form: DiaryData;
  recordId: string | null;
  saved: boolean;
  editing: boolean;
  printed: boolean;
  saving: boolean;
  error: string | null;
  yest: Measurement[];          // measurements filled in from the previous diary (see fillYesterday)
};

const AVATAR_TONES = ["tone-green", "tone-blue", "tone-brown", "tone-violet"];

function initialState(row: RoundRow, day: string): RowState {
  if (row.today) {
    return {
      form: { ...emptyDiary(day), ...row.today.data },
      recordId: row.today.recordId,
      saved: true,
      editing: false,
      printed: Boolean(row.today.printedAt),
      saving: false,
      error: null,
      yest: [],
    };
  }
  if (!row.previous) return { form: emptyDiary(day), recordId: null, saved: false, editing: true, printed: false, saving: false, error: null, yest: [] };
  const { form, keys } = fillYesterday(copyFrom(row.previous.data, day), row.previous.data);
  return { form, recordId: null, saved: false, editing: true, printed: false, saving: false, error: null, yest: keys };
}

const sameText = (a: DiaryData, b: DiaryData) =>
  (["od_text", "os_text", "ou_text"] as const).every((k) => (a[k] ?? "").trim() === (b[k] ?? "").trim());

/** Two stacked inputs, OD over OS — the way the doctor writes a fraction. */
function FracInput(props: {
  label: string;
  kind: PickKind;
  od: string;
  os: string;
  phOd: string;
  phOs: string;
  onChange: (eye: "od" | "os", v: string) => void;
  disabled: boolean;
  need: boolean;
  asis?: { od: boolean; os: boolean };     // still as yesterday
}) {
  return (
    <span className={"rd-frac" + (props.need ? " need" : "")}>
      <PickInput kind={props.kind} wrapClassName="rd-frac-od" className={props.asis?.od ? "asis" : undefined} aria-label={`${props.label} OD`} value={props.od} placeholder={props.phOd}
        inputMode="decimal" onChange={(v) => props.onChange("od", v)} disabled={props.disabled} />
      <PickInput kind={props.kind} wrapClassName="rd-frac-os" className={props.asis?.os ? "asis" : undefined} aria-label={`${props.label} OS`} value={props.os} placeholder={props.phOs}
        inputMode="decimal" onChange={(v) => props.onChange("os", v)} disabled={props.disabled} />
    </span>
  );
}

export function RoundPage() {
  const day = todayIso();
  const [rows, setRows] = useState<RoundRow[] | null>(null);
  const [state, setState] = useState<Record<string, RowState>>({});
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "left" | "postOp">("all");

  useEffect(() => {
    api.round(day).then(
      (r) => {
        setRows(r.rows);
        setState(Object.fromEntries(r.rows.map((row) => [row.caseId, initialState(row, day)])));
      },
      (e: Error) => setError(e.message),
    );
  }, [day]);

  const patch = (caseId: string, p: Partial<RowState>) => setState((s) => ({ ...s, [caseId]: { ...s[caseId], ...p } }));
  const setField = (caseId: string, k: keyof DiaryData, v: string) =>
    setState((s) => ({ ...s, [caseId]: { ...s[caseId], form: { ...s[caseId].form, [k]: v } } }));

  const save = async (row: RoundRow) => {
    const st = state[row.caseId];
    if (!hasMeasurements(st.form) && !window.confirm(`${row.surname}: Vis и ВГД не введены. Сохранить дневник без них?`)) return;
    const asis = stillYesterday(st.form, row.previous?.data, st.yest);
    if (asis.length && !window.confirm(yesterdayQuestion(asis, `${row.surname}: `))) return;
    patch(row.caseId, { saving: true, error: null });
    try {
      const res = st.recordId ? await api.updateDiary(st.recordId, st.form) : await api.createDiary(row.caseId, st.form);
      patch(row.caseId, { recordId: res.id, saved: true, editing: false, saving: false });
    } catch (e) {
      patch(row.caseId, { saving: false, error: (e as Error).message });
    }
  };

  if (error) return <main className="page rd"><div className="card" style={{ padding: 24 }}>Не удалось загрузить обход: {error}</div></main>;
  if (!rows) return <main className="page rd"><p className="muted">Загружаем обход…</p></main>;

  const done = rows.filter((r) => state[r.caseId]?.saved).length;
  const visible = rows.filter((r) =>
    filter === "left" ? !state[r.caseId]?.saved : filter === "postOp" ? r.postOp : true);
  const staleCount = rows.filter((r) => r.previousUnchanged && r.previous && sameText(state[r.caseId].form, r.previous.data)).length;

  return (
    <main className="page rd">
      <div className="rd-head">
        <Link to="/" className="round-btn white" aria-label="Назад к отделению">
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <h1>Обход · {longToday(day).split(", ")[1]}</h1>
        <div className="rd-progress" aria-label={`Готово ${done} из ${rows.length}`}>
          <span className="rd-bar"><span style={{ width: `${rows.length ? (done / rows.length) * 100 : 0}%` }} /></span>
          <b>{done} из {rows.length}</b>
        </div>
        <div style={{ flex: 1 }} />
        {([["all", `Все ${rows.length}`], ["left", `Осталось ${rows.length - done}`], ["postOp", `После операции ${rows.filter((r) => r.postOp).length}`]] as const).map(([k, label]) => (
          <button key={k} type="button" className={"chip" + (filter === k ? " on" : "")} aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}</button>
        ))}
      </div>

      <div className="rd-note">
        Текст и цифры подставлены из последнего дневника. <b>Vis, ВГД и АД подсвечены, пока вы их не измените</b> — при «Готов»
        программа спросит про неизменённые.
        Подробности (ЧСС, коррекция, жалобы) — в полной форме по ссылке «Открыть полностью».
      </div>

      <div className="rd-list" role="table" aria-label="Дневники за сегодня">
        <div className="rd-row rd-header" role="row">
          <span role="columnheader">Пациент</span><span role="columnheader">Vis OD/OS</span><span role="columnheader">ВГД OD/OS</span>
          <span role="columnheader">АД</span><span role="columnheader">Статус и лечение</span><span role="columnheader"></span>
        </div>
        {visible.map((row, i) => {
          const st = state[row.caseId];
          const f = st.form;
          const ay = stillYesterday(f, row.previous?.data, st.yest);
          const prev = row.previous?.data;
          const locked = st.printed || (st.saved && !st.editing);
          const stale = row.previousUnchanged && prev && sameText(f, prev);
          const status = (["od", "os"] as const).map((e) => {
            const s = f[`vis_correction_${e}`];
            return s && s !== "пусто" && s !== WITH_CORRECTION ? `${e.toUpperCase()} ${s.replace(" (не коррег.)", "")}` : "";
          }).filter(Boolean).join(" · ");
          return (
            <div role="row" key={row.caseId}
              className={"rd-row card" + (st.saved && !st.editing ? " done" : "") + (stale && !st.saved ? " stale" : "")}>
              <span className="rd-who">
                <span className={"avatar " + AVATAR_TONES[i % 4]} aria-hidden="true">{initials(row.surname, row.name)}</span>
                <span className="rd-who-text">
                  <Link to={`/case/${row.caseId}`} className="rd-name">{row.surname} {row.name} {row.patronymic}</Link>
                  <span className="muted rd-dx" title={row.diagnosis}>№ {row.number} · {row.diagnosis || "диагноз не указан"}</span>
                  <span className={"pill sm " + (row.postOp ? "tone-blue" : "tone-neutral")} style={{ alignSelf: "flex-start" }}>{row.dayLabel}</span>
                </span>
              </span>
              <span className="rd-cell">
                <FracInput label="Vis" kind="vis" asis={{ od: ay.includes("vis_od"), os: ay.includes("vis_os") }} od={f.vis_od} os={f.vis_os} phOd={prev?.vis_od ?? ""} phOs={prev?.vis_os ?? ""}
                  onChange={(e, v) => setField(row.caseId, `vis_${e}`, v)} disabled={locked} need={!locked && !f.vis_od && !f.vis_os} />
                {status && <span className="rd-status">{status}</span>}
              </span>
              <FracInput label="ВГД" kind="vgd" asis={{ od: ay.includes("vgd_od"), os: ay.includes("vgd_os") }} od={f.vgd_od} os={f.vgd_os} phOd={prev?.vgd_od ?? ""} phOs={prev?.vgd_os ?? ""}
                onChange={(e, v) => setField(row.caseId, `vgd_${e}`, v)} disabled={locked} need={!locked && !f.vgd_od && !f.vgd_os} />
              <PickInput kind="bp" className={"rd-bp" + (ay.includes("bp") ? " asis" : "")} aria-label="АД" value={f.bp} placeholder={prev?.bp ?? ""} onChange={(v) => setField(row.caseId, "bp", v)} disabled={locked} />
              <span className="rd-text">
                <input className="rd-txt" aria-label="OD" value={f.od_text} placeholder="OD: …" onChange={(e) => setField(row.caseId, "od_text", e.target.value)} disabled={locked} />
                <input className="rd-txt" aria-label="OS" value={f.os_text} placeholder="OS: …" onChange={(e) => setField(row.caseId, "os_text", e.target.value)} disabled={locked} />
                <span className="rd-meta">
                  {TREATMENT_PRESETS.map((t) => (
                    <button key={t} type="button" className={"pill " + (f.treatment.replace(/\.$/, "") === t ? "tone-green" : "tone-neutral")}
                      onClick={() => setField(row.caseId, "treatment", t)} disabled={locked}>{t}</button>
                  ))}
                  <span className="muted">{row.previous ? `из дневника ${shortDate(row.previous.date)}` : "прошлых дневников нет"}</span>
                  {stale && <span className="pill tone-amber">текст не менялся 2 дня — проверьте</span>}
                </span>
              </span>
              <span className="rd-act">
                {st.printed ? (
                  <span className="pill tone-neutral">напечатан</span>
                ) : st.saved && !st.editing ? (
                  <>
                    <span className="rd-done">✓ Готов</span>
                    <button type="button" className="link-btn" onClick={() => patch(row.caseId, { editing: true })}>Изменить</button>
                  </>
                ) : (
                  <button type="button" className="btn primary small" onClick={() => save(row)} disabled={st.saving}>
                    {st.saving ? "…" : st.recordId ? "Сохранить" : "Готов"}
                  </button>
                )}
                <Link to={st.recordId ? `/case/${row.caseId}/diary/${st.recordId}` : `/case/${row.caseId}/diary`} className="rd-full">Открыть полностью</Link>
                {st.error && <span className="rd-err" role="alert">{st.error}</span>}
              </span>
            </div>
          );
        })}
        {visible.length === 0 && <p className="muted" style={{ textAlign: "center" }}>{rows.length ? "В этом списке никого нет." : "В отделении нет активных историй."}</p>}
      </div>

      <div className="rd-bottom">
        <span style={{ flex: 1, paddingLeft: 10 }}>
          Готово <b>{done}</b> · осталось <b>{rows.length - done}</b>
          {staleCount > 0 && <span style={{ color: "var(--amber-strong)" }}> · {staleCount} {plural(staleCount, "дневник", "дневника", "дневников")} без изменений текста — проверьте</span>}
        </span>
        <Link to="/" className="btn primary small">Завершить обход</Link>
      </div>
    </main>
  );
}
