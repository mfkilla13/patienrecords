import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, CaseCard, RecordView, Step } from "../api";
import { VisionFractions } from "../components/VisionFractions";
import { fullDate, initials, plural, recordDate, shortDate } from "../format";
import "./case.css";

type Tab = "records" | "studies" | "prescriptions" | "passport";
type KindFilter = "all" | RecordView["kind"];

const KIND_FILTERS: { key: KindFilter; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "diary", label: "Дневники" },
  { key: "primary_exam", label: "Первичный осмотр" },
  { key: "operation_protocol", label: "Протоколы" },
  { key: "discharge_summary", label: "Выписка" },
];

const PRINTABLE = new Set(["primary_exam", "diary", "operation_protocol"]);

function StepPill({ step, index }: { step: Step; index: number }) {
  const sub = step.key === "admission" ? fullDate(step.sub) : /^\d{4}-\d{2}-\d{2}/.test(step.sub) ? shortDate(step.sub) : step.sub;
  return (
    <li className={"step step-" + step.state}>
      <span className="step-dot">{step.state === "done" ? "✓" : index + 1}</span>
      <span className="step-text">
        <span className="step-title">{step.title}</span>
        <span className="step-sub">{sub}</span>
      </span>
    </li>
  );
}

// Old printouts are shown inside a sandboxed frame (no scripts) with a policy that blocks any loads.
const LEGACY_CSP = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">`;

function LegacyHtml({ recordId }: { recordId: string }) {
  const [open, setOpen] = useState(false);
  const [html, setHtml] = useState<string | null>(null);

  const toggle = () => {
    setOpen(!open);
    if (html === null) {
      fetch(api.legacyHtmlUrl(recordId))
        .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
        .then((text) => setHtml(LEGACY_CSP + text))
        .catch(() => setHtml(LEGACY_CSP + "<p>Не удалось загрузить запись.</p>"));
    }
  };

  return (
    <div className="legacy">
      <button type="button" className="link-btn" onClick={toggle} aria-expanded={open}>
        {open ? "Скрыть" : "Показать как было напечатано в 2.9"}
      </button>
      {open && html !== null && (
        <iframe title="Запись из старой версии" className="legacy-frame" sandbox="" srcDoc={html} />
      )}
    </div>
  );
}

function RecordCard({ r, caseId, active }: { r: RecordView; caseId: string; active: boolean }) {
  const { day, time } = recordDate(r.recordedAt);
  const [showLocal, setShowLocal] = useState(false);
  return (
    <article className="rec">
      <div className="rec-head">
        <span className="rec-date">{day}</span>
        <span className="rec-kind">
          {r.kindLabel}
          {time && `, ${time}`}
        </span>
        <div style={{ flex: 1 }} />
        {PRINTABLE.has(r.kind) &&
          (r.printedAt ? (
            <span className="pill tone-neutral rec-badge">напечатано {shortDate(r.printedAt)}</span>
          ) : (
            <span className="pill tone-amber rec-badge">не напечатано</span>
          ))}
        {active && r.editable && (
          <Link to={r.kind === "primary_exam" ? `/case/${caseId}/exam` : `/case/${caseId}/diary/${r.id}`} className="rec-edit">Изменить</Link>
        )}
      </div>
      {r.title && r.kind === "operation_protocol" && <div className="rec-title">{r.title}</div>}
      {r.sections
        .filter((s) => !(r.kind === "operation_protocol" && s.label === "Операция"))
        .map((s, i) => (
          <p className="rec-line" key={i}>
            {s.label && <span className="rec-label">{s.label}: </span>}
            {s.text}
          </p>
        ))}
      {r.vision && (
        <div className="rec-vision">
          <VisionFractions v={r.vision} />
        </div>
      )}
      {r.local.length > 0 && (
        <div>
          <button type="button" className="link-btn" onClick={() => setShowLocal(!showLocal)} aria-expanded={showLocal}>
            {showLocal ? "Скрыть местный статус" : `Местный статус · ${r.local.length} ${plural(r.local.length, "строка", "строки", "строк")}`}
          </button>
          {showLocal && (
            <table className="local">
              <thead>
                <tr>
                  <th style={{ width: 170 }}></th>
                  <th>OD</th>
                  <th>OS</th>
                </tr>
              </thead>
              <tbody>
                {r.local.map((row) => (
                  <tr key={row.name}>
                    <td className="local-name">{row.name}</td>
                    <td>{row.od || <span className="muted">—</span>}</td>
                    <td>{row.os || <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      {r.hasLegacyHtml && (
        <>
          <p className="rec-line muted">Запись из старой версии без разбивки по полям.</p>
          <LegacyHtml recordId={r.id} />
        </>
      )}
    </article>
  );
}

export function CasePage() {
  const { caseId = "" } = useParams();
  const [card, setCard] = useState<CaseCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("records");
  const [kind, setKind] = useState<KindFilter>("all");

  useEffect(() => {
    setCard(null);
    api.caseCard(caseId).then(setCard, (e: Error) => setError(e.message));
  }, [caseId]);

  const records = useMemo(
    () => (card ? card.records.filter((r) => kind === "all" || r.kind === kind) : []),
    [card, kind],
  );

  if (error) {
    return (
      <main className="page cs">
        <div className="card" style={{ padding: 24 }}>Не удалось открыть историю: {error}</div>
      </main>
    );
  }
  if (!card) {
    return (
      <main className="page cs">
        <p className="muted">Загружаем историю…</p>
      </main>
    );
  }

  const p = card.patient;
  const fio = [p.surname, p.name, p.patronymic].filter(Boolean).join(" ");
  const active = card.status === "active";
  const counts: Record<Tab, number | string> = {
    records: card.records.length,
    studies: card.studies.length,
    prescriptions: card.prescriptions.length,
    passport: "",
  };
  const kindCount = (k: KindFilter) => (k === "all" ? card.records.length : card.records.filter((r) => r.kind === k).length);

  return (
    <main className="page cs">
      <section className="card cs-head">
        <div className="cs-top">
          <Link to="/" className="round-btn" aria-label="Назад к отделению">
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </Link>
          <div className="avatar tone-green cs-avatar" aria-hidden="true">{initials(p.surname, p.name)}</div>
          <div className="cs-who">
            <h1>{fio}</h1>
            <div className="muted">
              История № {card.number}
              {card.medCard && ` · мед. карта ${card.medCard}`}
              {p.age != null && ` · ${p.age} ${plural(p.age, "год", "года", "лет")}`}
              {card.admittedAt && ` · поступил(а) ${fullDate(card.admittedAt)}`}
              {card.day != null && (
                <>
                  {" · "}
                  <b style={{ color: "var(--text)" }}>{active ? `день ${card.day}` : `${card.day} койко-дн.`}</b>
                </>
              )}
            </div>
          </div>
          <div className="cs-actions">
            {active ? (
              <>
                {!card.records.some((r) => r.kind === "primary_exam") && (
                  <Link to={`/case/${card.caseId}/exam`} className="btn">Первичный осмотр</Link>
                )}
                <Link to={`/case/${card.caseId}/discharge`} className="btn">Выписать</Link>
                <Link to={`/case/${card.caseId}/new`} className="btn">Новая запись</Link>
                <Link to={`/case/${card.caseId}/print`} className="btn">
                  Печать {card.unprinted > 0 && <span className="pill sm" style={{ background: "var(--amber-strong)", color: "var(--amber-text)" }}>{card.unprinted}</span>}
                </Link>
                <Link to={`/case/${card.caseId}/diary`} className="btn primary">Дневник за сегодня</Link>
              </>
            ) : (
              <span className={"pill " + (card.status === "archived" ? "tone-neutral" : "tone-green")}>
                {card.status === "archived" ? "В архиве" : "Выписан(а)"} {card.dischargedAt && fullDate(card.dischargedAt)}
                {card.outcome && ` · ${card.outcome}`}
              </span>
            )}
          </div>
        </div>

        <div className="cs-chips">
          <span className="cs-chip">
            <span className="muted">Диагноз:</span> <b>{card.diagnosis.main || "не указан"}</b>
          </span>
          {card.diagnosis.comorbid && (
            <span className="cs-chip">
              <span className="muted">Сопутствующий:</span> <b>{card.diagnosis.comorbid}</b>
            </span>
          )}
          {card.latestVision && (
            <span className="cs-chip cs-chip-vision">
              <span className="muted" style={{ fontSize: 13 }}>на {shortDate(card.latestVision.at)}</span>
              <VisionFractions v={card.latestVision.eyes} accent />
            </span>
          )}
        </div>

        <ol className="steps" aria-label="Ход лечения">
          {card.steps.map((s, i) => (
            <StepPill key={s.key} step={s} index={i} />
          ))}
        </ol>
      </section>

      <div className="cs-body">
        <nav className="cs-nav" aria-label="Разделы истории">
          {(
            [
              ["records", "Дневники и записи"],
              ["studies", "Исследования"],
              ["prescriptions", "Назначения"],
              ["passport", "Паспортная часть"],
            ] as [Tab, string][]
          ).map(([key, label]) => (
            <button key={key} type="button" className={"cs-nav-item" + (tab === key ? " on" : "")} aria-current={tab === key ? "page" : undefined} onClick={() => setTab(key)}>
              <span style={{ flex: 1 }}>{label}</span>
              <span className="muted" style={{ fontSize: 13 }}>{counts[key]}</span>
            </button>
          ))}
        </nav>

        <section className="cs-main">
          {tab === "records" && (
            <>
              <div className="cs-main-head">
                <h2>Дневники и записи</h2>
                <div style={{ flex: 1 }} />
                <span className="muted">Сначала новые</span>
              </div>
              <div className="cs-filters" role="group" aria-label="Тип записи">
                {KIND_FILTERS.filter((f) => f.key === "all" || kindCount(f.key) > 0).map((f) => (
                  <button key={f.key} type="button" className={"chip" + (kind === f.key ? " on" : "")} aria-pressed={kind === f.key} onClick={() => setKind(f.key)}>
                    {f.label} <span className="chip-n">{kindCount(f.key)}</span>
                  </button>
                ))}
              </div>
              {active && card.unprinted > 0 && (
                <div className="cs-banner">
                  <span style={{ flex: 1 }}>
                    <b>
                      {card.unprinted} {plural(card.unprinted, "запись", "записи", "записей")} ещё не на бумаге.
                    </b>{" "}
                    Они допечатаются ниже предыдущих.
                  </span>
                  <Link to={`/case/${card.caseId}/print`} className="btn white small">Допечатать</Link>
                </div>
              )}
              {records.map((r) => (
                <RecordCard key={r.id} r={r} caseId={card.caseId} active={active} />
              ))}
              {records.length === 0 && <p className="muted">Записей нет.</p>}
            </>
          )}

          {tab === "studies" && (
            <>
              <div className="cs-main-head"><h2>Исследования</h2></div>
              {card.studies.map((s) => (
                <article className="rec" key={s.id}>
                  <div className="rec-head">
                    <span className="rec-date">{s.date ? shortDate(s.date) : "без даты"}</span>
                    <b>{s.kind}</b>
                  </div>
                  <p className="rec-line">{s.summary || <span className="muted">без результата</span>}</p>
                  {s.unparsedDate && (
                    <p className="rec-line" style={{ color: "var(--amber-text)" }}>
                      Дата в старой базе записана с ошибкой: «{s.unparsedDate}». Её нужно исправить.
                    </p>
                  )}
                </article>
              ))}
              {card.studies.length === 0 && <p className="muted">Исследований нет.</p>}
            </>
          )}

          {tab === "prescriptions" && (
            <>
              <div className="cs-main-head"><h2>Назначения</h2></div>
              {card.prescriptions.length === 0 ? (
                <p className="muted">Назначений нет. В старой версии лист назначений не заполнялся.</p>
              ) : (
                card.prescriptions.map((x) => (
                  <article className="rec" key={x.id}>
                    <b>{x.name}</b>
                    <span className="muted">{[x.method, x.freq, x.date_from && `с ${shortDate(x.date_from)}`, x.date_to && `по ${shortDate(x.date_to)}`].filter(Boolean).join(" · ")}</span>
                  </article>
                ))
              )}
            </>
          )}

          {tab === "passport" && (
            <>
              <div className="cs-main-head"><h2>Паспортная часть</h2></div>
              <article className="rec">
                <dl className="kv">
                  <dt>Ф. И. О.</dt><dd>{fio}</dd>
                  <dt>Дата рождения</dt><dd>{fullDate(p.dob)}</dd>
                  <dt>Адрес</dt><dd>{p.address || "—"}</dd>
                  <dt>№ истории</dt><dd>{card.number}</dd>
                  <dt>№ мед. карты</dt><dd>{card.medCard || "—"}</dd>
                  <dt>Поступление</dt><dd>{fullDate(card.admittedAt)} {card.admittedAt?.slice(11, 16)}</dd>
                  <dt>Диагноз при поступлении</dt><dd>{card.diagnosis.admission || "—"}</dd>
                  <dt>Клинический диагноз</dt><dd>{card.diagnosis.clinical || "—"}</dd>
                  <dt>Заключительный диагноз</dt><dd>{card.diagnosis.final || "—"}</dd>
                  <dt>Выписка</dt><dd>{fullDate(card.dischargedAt)} {card.outcome && `· ${card.outcome}`}</dd>
                </dl>
              </article>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
