import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, CaseCard, PrintJob, PrintKind, PrintMode, PrintPlan } from "../api";
import { plural, recordDate, shortDate } from "../format";
import "./print.css";

type Stage = "setup" | "printing" | "check" | "notStraight";
type Rec = PrintPlan["records"][number];

/** Why a record cannot be ticked in the chosen kind of print, or null. */
function blocked(r: Rec, kind: PrintKind): string | null {
  if (!r.printable) return r.reason;
  if (kind === "sheet" && r.printedAt && !r.place) return "legacy";
  return null;
}

function defaultSelection(p: PrintPlan, kind: PrintKind): Set<string> {
  return new Set(kind === "sheet" ? p.records.filter((r) => r.printable && !r.printedAt).map((r) => r.id) : []);
}

export function PrintPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  const [card, setCard] = useState<CaseCard | null>(null);
  const [plan, setPlan] = useState<PrintPlan | null>(null);
  const [kind, setKind] = useState<PrintKind>("sheet");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<PrintMode>("new");
  const [manualMm, setManualMm] = useState("20");
  const [job, setJob] = useState<PrintJob | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [printers, setPrinters] = useState<{ list: string[]; chosen: string }>({ list: [], chosen: "" });
  const [stage, setStage] = useState<Stage>("setup");
  const [zoomed, setZoomed] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pendingJob = useRef<string | null>(null);
  // «Есть ли на листе записи от руки после нашей печати?» must be answered before continuing a sheet.
  const [hand, setHand] = useState<"unknown" | "no" | "yes">("unknown");
  const [handMm, setHandMm] = useState("");
  const [handSheet, setHandSheet] = useState<number | null>(null);   // the sheet where the handwriting ends

  useEffect(() => {
    // The same page component is reused for another case: start from a clean state.
    setError(null);
    setPlan(null);
    setJob(null);
    setStage("setup");
    setKind("sheet");
    setHand("unknown");
    setHandMm("");
    setHandSheet(null);
    api.caseCard(caseId).then(setCard, () => undefined);
    api.printPlan(caseId).then((p) => {
      setPlan(p);
      setSelected(defaultSelection(p, "sheet"));
      setMode(p.suggestion.mode);
      setManualMm(String(Math.round(p.suggestion.startMm)));
    }, (e: Error) => setError(e.message));
    api.printers().then((p) => setPrinters({ list: p.printers, chosen: p.default ?? p.printers[0] ?? "" }), () => undefined);
  }, [caseId]);

  const switchKind = (k: PrintKind) => {
    if (!plan || k === kind) return;
    setKind(k);
    setSelected(defaultSelection(plan, k));
    if (k === "copy" && mode === "continue") setMode("new");
  };

  // Re-lay out whenever the selection or position changes; the replaced pending job is cancelled.
  useEffect(() => {
    if (!plan || stage !== "setup") return;
    const ids = plan.records.filter((r) => selected.has(r.id)).map((r) => r.id);
    if (ids.length === 0) {
      setJob(null);
      setJobError(null);
      return;
    }
    const mm = Number(manualMm.replace(",", "."));
    const handwritten = mode === "continue" && hand === "yes" ? Number(handMm.replace(",", ".")) : NaN;
    const timer = window.setTimeout(() => {
      const hwOk = Number.isFinite(handwritten) && handwritten > 0;
      api.createPrintJob(caseId, kind, ids, mode, mode === "manual" ? mm : undefined,
        hwOk ? handwritten : undefined, hwOk && handSheet ? handSheet : undefined).then(
        (j) => {
          if (pendingJob.current) api.cancelPrint(pendingJob.current).catch(() => undefined);
          pendingJob.current = j.jobId;
          setJob(j);
          setJobError(null);
        },
        (e: Error) => {
          setJob(null);
          setJobError(e.message);
        },
      );
    }, 250);
    return () => window.clearTimeout(timer);
  }, [caseId, plan, kind, selected, mode, manualMm, stage, hand, handMm, handSheet]);

  useEffect(() => () => {
    if (pendingJob.current) api.cancelPrint(pendingJob.current).catch(() => undefined);
  }, []);

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const print = async () => {
    if (!job) return;
    setError(null);
    setStage("printing");
    try {
      await api.sendToPrinter(job.jobId, printers.chosen);
      setStage("check");
    } catch (e) {
      setError((e as Error).message);
      setStage("setup");
    }
  };

  const confirm = async () => {
    if (!job) return;
    await api.confirmPrint(job.jobId);
    pendingJob.current = null;
    navigate(`/case/${caseId}`);
  };

  const notStraight = async () => {
    if (job) await api.cancelPrint(job.jobId).catch(() => undefined);
    pendingJob.current = null;
    setJob(null);
    setStage("notStraight");
  };

  const state = plan?.state;
  const continuingNew = kind === "sheet" && mode === "continue" && (plan?.records ?? []).some((r) => selected.has(r.id) && !r.printedAt);
  const handPending = continuingNew && (hand === "unknown" || (hand === "yes" && !(Number(handMm.replace(",", ".")) > 0)));
  const canContinue = kind === "sheet" && state?.source === "v3" && plan?.suggestion.mode === "continue";
  const selectedRecs = plan ? plan.records.filter((r) => selected.has(r.id)) : [];
  const hasNew = kind === "copy" ? selectedRecs.length > 0 : selectedRecs.some((r) => !r.printedAt);
  const fio = card ? [card.patient.surname, card.patient.name, card.patient.patronymic].filter(Boolean).join(" ") : "";
  // The «… мм» mark only where printing continues a sheet; a fresh sheet starts under its heading.
  const startMark = (sheet: number) =>
    job?.newStart && job.newStart.sheet === sheet && !job.pages.find((p) => p.sheet === sheet)?.fresh ? job.newStart.mm : null;

  return (
    <div className="pr-overlay">
      {zoomed !== null && job && (
        <div className="pr-lightbox" role="dialog" aria-label="Лист крупно" onClick={() => setZoomed(null)}>
          <div className="pr-lightbox-sheet">
            <img src={api.printJobPageUrl(job.jobId, zoomed, 200)} alt={`Страница ${zoomed} крупно`} />
            {startMark(job.pages[zoomed - 1].sheet) !== null && (
              <span className="pr-mark" style={{ top: `${(startMark(job.pages[zoomed - 1].sheet)! / 297) * 100}%` }}>
                {startMark(job.pages[zoomed - 1].sheet)!.toFixed(0)} мм
              </span>
            )}
          </div>
          <span className="pr-lightbox-hint">Нажмите в любом месте, чтобы закрыть</span>
        </div>
      )}
      <section role="dialog" aria-modal="true" aria-labelledby="pr-title" className="pr-dialog">
        <div className="pr-head">
          <span className="pr-icon" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9V2h12v7" /><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" /><rect x="6" y="14" width="12" height="8" /></svg>
          </span>
          <div style={{ flex: 1 }}>
            <h1 id="pr-title">Печать дневников</h1>
            <div className="muted">{fio}{card && ` · история № ${card.number}`}</div>
          </div>
          <Link to={`/case/${caseId}`} className="round-btn" aria-label="Закрыть">
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </Link>
        </div>

        {error && <div className="pr-banner pr-error" role="alert">{error}</div>}

        {(stage === "check" || stage === "printing") && job ? (
          <div className="pr-check">
            {stage === "printing" ? (
              <p className="pr-check-title">Отправляем на принтер…</p>
            ) : job.kind === "copy" ? (
              <>
                <p className="pr-check-title">Копия напечатана?</p>
                <p className="muted">Копия ничего не отмечает в истории и не меняет места записей на листах.</p>
                <div className="pr-check-actions">
                  <button type="button" className="btn primary" onClick={confirm}>Готово</button>
                  <button type="button" className="btn" onClick={notStraight}>Напечатать заново</button>
                </div>
              </>
            ) : (
              <>
                <p className="pr-check-title">
                  Проверьте {job.pages.length > 1 ? "листы" : `лист ${job.pages[0].sheet}`}: записи легли ровно на свои места?
                </p>
                <p className="muted">
                  {job.newCount > 0
                    ? `Только после «Да» ${job.newCount} ${plural(job.newCount, "новая запись отметится", "новые записи отметятся", "новых записей отметятся")} напечатанными и получат постоянное место на листе.`
                    : "Перепечатка ничего не меняет в отметках печати."}
                  {job.newEnd && ` Следующая печать начнётся на листе ${job.newEnd.sheet} с ${(job.newEnd.mm + 3).toFixed(0)} мм.`}
                </p>
                <div className="pr-check-actions">
                  <button type="button" className="btn primary" onClick={confirm}>Да, всё ровно</button>
                  <button type="button" className="btn" onClick={notStraight}>Нет, не ровно</button>
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="pr-body">
            <div className="pr-left">
              <div className="seg pr-kind" role="radiogroup" aria-label="Вид печати">
                <button type="button" role="radio" aria-checked={kind === "sheet"} className={kind === "sheet" ? "on" : ""} onClick={() => switchKind("sheet")}>
                  На лист истории
                </button>
                <button type="button" role="radio" aria-checked={kind === "copy"} className={kind === "copy" ? "on" : ""} onClick={() => switchKind("copy")}>
                  Копия подряд
                </button>
              </div>
              <p className="muted pr-kind-hint">
                {kind === "sheet"
                  ? "Новые записи допечатаются под последней. Отмеченные напечатанные — перепечатаются точно на свои места."
                  : "Выбранные записи одна за другой на чистом листе или от отступа. Отметки печати не меняются."}
              </p>

              {stage === "notStraight" && (
                <div className="pr-banner pr-warn">
                  Ничего не отмечено. Поправьте отступ ниже (больше — ниже на листе) и напечатайте снова, или начните новый лист.
                </div>
              )}
              <fieldset className="pr-fs">
                <legend><span className="pr-num">1</span>Что печатать</legend>
                {!plan && <p className="muted">Загружаем записи…</p>}
                {plan?.records.length === 0 && <p className="muted">В истории нет записей для листа дневников.</p>}
                {kind === "sheet" && plan?.records.some((r) => blocked(r, kind) === "legacy") && (
                  <div className="pr-banner">
                    Записи с пометкой «2.9» напечатаны старой версией — их точного места на листе программа не знает.
                    Перепечатать их можно через «Копия подряд».
                  </div>
                )}
                {plan?.records.map((r) => {
                  const { day, time } = recordDate(r.recordedAt);
                  const why = blocked(r, kind);
                  const on = selected.has(r.id);
                  let badge: [string, string] | null = null;
                  if (r.printable && !r.printedAt) badge = ["новая", "tone-amber"];
                  else if (r.printable && r.place) badge = [kind === "sheet" && on ? `перепечатается: лист ${r.place.sheet}, ${r.place.startMm.toFixed(0)} мм` : `лист ${r.place.sheet}, ${r.place.startMm.toFixed(0)} мм`, kind === "sheet" && on ? "tone-blue" : "tone-neutral"];
                  else if (r.printable && r.printedAt) badge = [`2.9 · ${shortDate(r.printedAt)}`, "tone-neutral"];
                  return (
                    <label key={r.id} className={"pr-rec" + (why ? " off" : "") + (on ? " on" : "")}>
                      <input type="checkbox" checked={on} disabled={Boolean(why)} onChange={() => toggle(r.id)} />
                      <span className="pr-rec-text">
                        <b>{day} · {r.kindLabel}{time && `, ${time}`}</b>
                        <span className="muted">{why && why !== "legacy" ? why : r.summary}</span>
                      </span>
                      {badge && <span className={"pill " + badge[1]}>{badge[0]}</span>}
                    </label>
                  );
                })}
              </fieldset>

              {hasNew && (
                <fieldset className="pr-fs">
                  <legend><span className="pr-num">2</span>{kind === "sheet" ? "Куда новые записи" : "Откуда начать"}</legend>
                  {kind === "sheet" && state?.source === "legacy" && state.used_mm > 0 && (
                    <div className="pr-banner">Позиция из версии 2.9 ({Math.round(state.used_mm)} мм) считалась по-другому и не используется. Начните новый лист или укажите отступ линейкой.</div>
                  )}
                  {canContinue && (
                    <label className={"pr-opt" + (mode === "continue" ? " on" : "")}>
                      <input type="radio" name="where" checked={mode === "continue"} onChange={() => setMode("continue")} />
                      <span>
                        <b>Продолжить лист {state!.sheet}</b>
                        <span>
                          {hand === "yes" && Number(handMm.replace(",", ".")) > 0
                            ? <>Ниже записи от руки: {handSheet && handSheet !== state!.sheet ? <>на листе <b>{handSheet}</b>, </> : ""}с <b>{(Number(handMm.replace(",", ".")) + 1.5).toFixed(0)} мм</b> от верхнего края.</>
                            : <>Сразу под последней записью{plan!.lastOnSheet && ` (${plan!.lastOnSheet})`}: с <b>{plan!.suggestion.startMm.toFixed(0)} мм</b> от верхнего края.</>}
                        </span>
                        {mode === "continue" && (
                          <span className={"pr-hand" + (hand === "unknown" ? " ask" : "")} role="group" aria-label="Записи от руки">
                            <span className="pr-hand-q">
                              После нашей печати{plan!.lastOnSheet && ` (запись от ${plan!.lastOnSheet})`} на листе есть записи от руки?
                            </span>
                            <span className="pr-hand-a">
                              <button type="button" className={"chip" + (hand === "no" ? " on" : "")} aria-pressed={hand === "no"}
                                onClick={(e) => { e.preventDefault(); setHand("no"); }}>Нет</button>
                              <button type="button" className={"chip" + (hand === "yes" ? " on" : "")} aria-pressed={hand === "yes"}
                                onClick={(e) => { e.preventDefault(); setHand("yes"); }}>Да, есть</button>
                              {hand === "yes" && (
                                <span className="pr-hand-sheets" role="radiogroup" aria-label="Где кончается запись от руки">
                                  <span className="muted">кончается</span>
                                  {[0, 1, 2].map((k) => {
                                    const s = state!.sheet + k;
                                    const on = (handSheet ?? state!.sheet) === s;
                                    return (
                                      <button key={k} type="button" role="radio" aria-checked={on} className={"chip" + (on ? " on" : "")}
                                        onClick={(e) => { e.preventDefault(); setHandSheet(s); }}>
                                        {k === 0 ? `на этом листе (${s})` : `на листе ${s}`}
                                      </button>
                                    );
                                  })}
                                </span>
                              )}
                              {hand === "yes" && (
                                <span className="pr-mm">
                                  до <input className="in" inputMode="decimal" autoFocus value={handMm} placeholder="мм"
                                    onChange={(e) => setHandMm(e.target.value)} aria-label="Где кончается запись от руки, мм" />
                                  мм от верхнего края{handSheet && handSheet !== state!.sheet ? ` листа ${handSheet}` : ""} — измерьте линейкой
                                </span>
                              )}
                            </span>
                          </span>
                        )}
                      </span>
                    </label>
                  )}
                  <label className={"pr-opt" + (mode === "new" ? " on" : "")}>
                    <input type="radio" name="where" checked={mode === "new"} onChange={() => setMode("new")} />
                    <span><b>{kind === "sheet" ? "Начать новый лист" : "Чистый лист"}</b><span>С шапкой: отделение, пациент и номер листа.</span></span>
                  </label>
                  <label className={"pr-opt" + (mode === "manual" ? " on" : "")}>
                    <input type="radio" name="where" checked={mode === "manual"} onChange={() => setMode("manual")} />
                    <span>
                      <b>Указать отступ сверху</b>
                      <span className="pr-mm">
                        <input className="in" inputMode="decimal" value={manualMm} onFocus={() => setMode("manual")}
                          onChange={(e) => { setMode("manual"); setManualMm(e.target.value); }} aria-label="Отступ сверху, мм" />
                        мм от верхнего края листа
                      </span>
                    </span>
                  </label>
                </fieldset>
              )}
            </div>

            <div className="pr-preview">
              {jobError && <div className="pr-banner pr-error">{jobError}</div>}
              {job ? (
                <>
                  {job.pages.some((p) => p.shade.length > 0) && (
                    <div className="pr-legend">
                      <span><i className="sw sw-old" />уже на бумаге</span>
                      <span><i className="sw sw-new" />напечатается сейчас</span>
                    </div>
                  )}
                  {job.movedToNewSheet && (
                    <div className="pr-banner pr-warn">На листе не хватает места — новые записи начнутся с нового листа {job.newStart?.sheet}.</div>
                  )}
                  {job.pages.map((p, i) => (
                    <div key={`${job.jobId}-${i}`} className="pr-pagebox">
                      <div className="pr-insert">
                        {job.pages.length > 1 && <span className="muted">Страница {i + 1}: </span>}
                        Вставьте <b>{p.insert}</b>
                      </div>
                      <button type="button" className="pr-sheet" onClick={() => setZoomed(i + 1)} aria-label={`Открыть страницу ${i + 1} крупно`}>
                        <img className="pr-page" alt={`Предпросмотр: ${p.insert}`} src={api.printJobPageUrl(job.jobId, i + 1)} />
                        {startMark(p.sheet) !== null && (
                          <span className="pr-mark" style={{ top: `${(startMark(p.sheet)! / 297) * 100}%` }}>{startMark(p.sheet)!.toFixed(0)} мм</span>
                        )}
                      </button>
                    </div>
                  ))}
                  <span className="muted pr-zoom-hint">Нажмите на лист, чтобы рассмотреть крупно</span>
                  <div className="muted pr-sum">
                    {[
                      job.newCount > 0 && `новых: ${job.newCount}`,
                      job.reprintCount > 0 && `на свои места: ${job.reprintCount}`,
                      job.kind === "copy" && `копия: ${job.count}`,
                      job.newEnd && `после печати на листе ${job.newEnd.sheet} останется ${Math.max(job.leftMm, 0).toFixed(0)} мм`,
                    ].filter(Boolean).join(" · ")}
                  </div>
                </>
              ) : (
                !jobError && <p className="muted">Выберите записи — здесь появится лист.</p>
              )}
            </div>
          </div>
        )}

        {stage !== "check" && stage !== "printing" && (
          <div className="pr-foot">
            <label className="pr-printer">
              Принтер
              <select className="in" value={printers.chosen} onChange={(e) => setPrinters({ ...printers, chosen: e.target.value })}>
                {printers.list.length === 0 && <option value="">принтеры не найдены</option>}
                {printers.list.map((p) => <option key={p}>{p}</option>)}
              </select>
            </label>
            <span className="muted pr-foot-note">
              {handPending ? "Ответьте, есть ли на листе записи от руки — тогда можно печатать." : "После печати программа спросит, ровно ли вышло."}
            </span>
            <Link to={`/case/${caseId}`} className="btn">Отмена</Link>
            {job && <a className="btn" href={api.printJobPdfUrl(job.jobId)} target="_blank" rel="noreferrer">Открыть PDF</a>}
            <button type="button" className="btn primary" disabled={!job || !printers.chosen || handPending} onClick={print}
              title={handPending ? "Сначала ответьте, есть ли на листе записи от руки" : undefined}>
              {job ? `Напечатать ${job.count} ${plural(job.count, "запись", "записи", "записей")}` : "Напечатать"}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
