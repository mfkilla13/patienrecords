import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, DeptReport, ReportPeriod, ReportRow } from "../api";
import { plural } from "../format";
import "./stats.css";
import "./report.css";

/** Numbers as the department's reports write them: «-» for nothing, a comma for decimals. */
const n = (v: number | null | undefined) =>
  v == null || v === 0 ? "-" : Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100).replace(".", ",");

function Nested({ title, first, cur, prev, years }: {
  title: string; first: string; cur: ReportRow[]; prev: ReportRow[] | null; years: [string, string];
}) {
  const byLabel = new Map((prev ?? []).map((r) => [r.label, r]));
  const sum = (rows: ReportRow[]) => [rows.reduce((a, r) => a + r.count, 0), rows.reduce((a, r) => a + r.bedDays, 0)];
  const [cn, cbd] = sum(cur);
  const [pn, pbd] = prev ? sum(prev) : [0, 0];
  const pair = (p: string, c: string) => <><td className="rp-prev">{prev ? p : ""}</td><td>{c}</td></>;
  return (
    <section className="card rp-card" aria-label={title}>
      <h2>{title}</h2>
      <div className="rp-scroll">
        <table className="rp-table">
          <thead>
            <tr>
              <th rowSpan={2} className="rp-first">{first}</th>
              <th colSpan={2}>Количество</th><th colSpan={2}>Удельный вес</th><th colSpan={2}>Проведено к-дней</th>
              <th colSpan={2}>Среднее пребывание</th>
            </tr>
            <tr>{[0, 1, 2, 3].flatMap((i) => [<th key={`p${i}`} className="rp-prev">{years[0]}</th>, <th key={`c${i}`}>{years[1]}</th>])}</tr>
          </thead>
          <tbody>
            {cur.map((r) => {
              const p = byLabel.get(r.label);
              return (
                <tr key={r.label} className={r.count ? "" : "rp-zero"}>
                  <td className="rp-first">{r.label}</td>
                  {pair(n(p?.count), n(r.count))}{pair(n(p?.share), n(r.share))}
                  {pair(n(p?.bedDays), n(r.bedDays))}{pair(n(p?.avgStay), n(r.avgStay))}
                </tr>
              );
            })}
            <tr className="rp-total">
              <td className="rp-first">Итого:</td>
              {pair(n(pn), n(cn))}{pair(pn ? "100" : "-", cn ? "100" : "-")}{pair(n(pbd), n(cbd))}
              {pair(n(pn ? pbd / pn : null), n(cn ? cbd / cn : null))}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MainTable({ cur, prev, years }: { cur: ReportPeriod; prev: ReportPeriod | null; years: [string, string] }) {
  const m = cur.main, pm = prev?.main;
  const s = cur.surgery, ps = prev?.surgery;
  const ch = (p: ReportPeriod | null | undefined, label: string) => p?.channels.find((c) => c.label === label)?.count;
  const rows: [string, number | null | undefined, number | null | undefined, boolean?][] = [
    ["Количество сметных коек", pm?.beds, m.beds],
    ["Пролечено больных", pm?.treated, m.treated],
    ["из них сельских", pm?.rural, m.rural, true],
    ["из них иногородних", pm?.nonresident, m.nonresident, true],
    ["из них иностранных граждан", pm?.foreign, m.foreign, true],
    ["из них подростки (15–17 лет)", pm?.teens, m.teens, true],
    ["из них дети (до 15 лет)", pm?.children, m.children, true],
    ["Поступило больных", pm?.admitted, m.admitted],
    ["Выписано больных", pm?.discharged, m.discharged],
    ["Проведено койко-дней", pm?.bedDays, m.bedDays],
    ["Средняя длительность пребывания на койке", pm?.avgStay, m.avgStay],
    ["Средний оборот койки", pm?.turnover, m.turnover],
    ["Среднее число дней работы койки", pm?.bedWork, m.bedWork],
    ["Среднее время простоя койки", pm?.bedIdle, m.bedIdle],
    ["Процент госпитализации сельских жителей", pm?.ruralPercent, m.ruralPercent],
    ["Процент выполнения плана койко-дней", pm?.planPercent, m.planPercent],
    ["Госпитализированы экстренно", pm?.emergency, m.emergency],
    ...cur.channels.filter((c) => c.kind === "emergency").map((c) => [c.label, ch(prev, c.label), c.count, true] as [string, number | undefined, number, boolean]),
    ["Госпитализированы планово", pm?.planned, m.planned],
    ...cur.channels.filter((c) => c.kind === "planned").map((c) => [c.label, ch(prev, c.label), c.count, true] as [string, number | undefined, number, boolean]),
    ["Прооперировано больных", ps && ps.operatedUrgent + ps.operatedPlanned, s.operatedUrgent + s.operatedPlanned],
    ["в срочном порядке", ps?.operatedUrgent, s.operatedUrgent, true],
    ["в плановом порядке", ps?.operatedPlanned, s.operatedPlanned, true],
    ["Количество операций", ps?.operations, s.operations],
    ["в срочном порядке", ps?.urgent, s.urgent, true],
    ["в плановом порядке", ps?.planned, s.planned, true],
    ["Осложнения после экстренных операций", ps?.complicationsUrgent, s.complicationsUrgent],
    ["Осложнения после плановых операций", ps?.complicationsPlanned, s.complicationsPlanned],
    ["Умерло всего", pm?.died, m.died],
  ];
  return (
    <section className="card rp-card" aria-label="Основные показатели">
      <h2>Основные показатели работы отделения</h2>
      <table className="rp-table rp-main">
        <thead><tr><th className="rp-first">Показатель</th><th className="rp-prev">{years[0]}</th><th>{years[1]}</th></tr></thead>
        <tbody>
          {rows.map(([label, p, c, sub], i) => (
            <tr key={i}>
              <td className={"rp-first" + (sub ? " rp-sub" : "")}>{label}</td>
              <td className="rp-prev">{prev ? n(p) : ""}</td>
              <td><b>{n(c)}</b></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function ReportPage() {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<DeptReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const [stamp, setStamp] = useState(0);

  useEffect(() => {
    setError(null);
    api.report(from, to).then((d) => {
      setData(d);
      if (!from || !to) setParams({ from: d.current.from, to: d.current.to }, { replace: true });
    }, (e: Error) => setError(e.message));
  }, [from, to, stamp]);

  const choose = async (caseId: string, group: string) => {
    try {
      await api.setReportGroup(caseId, group);
      setStamp((s) => s + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const cur = data?.current;
  const prev = data?.previous.hasData ? data.previous : null;
  const years: [string, string] = data ? [data.previous.to.slice(0, 4), data.current.to.slice(0, 4)] : ["", ""];
  const auto = cur?.autoGroups ?? [];

  return (
    <main className="page sx">
      <div className="sx-top">
        <h1>Отчёт отделения</h1>
        <div style={{ flex: 1 }} />
        {data && (
          <a className="btn primary" href={api.reportDocxUrl(data.current.from, data.current.to)} download>
            Скачать Word
          </a>
        )}
      </div>

      <div className="rp-periods">
        {data?.periods.map((p) => (
          <button key={p.key} type="button" className={"chip" + (p.from === from && p.to === to ? " on" : "")}
            onClick={() => setParams({ from: p.from, to: p.to }, { replace: true })}>{p.label}</button>
        ))}
        <span className="sx-range">
          <input className="in" type="date" aria-label="С" value={from} onChange={(e) => setParams({ from: e.target.value, to }, { replace: true })} />
          <span className="muted">—</span>
          <input className="in" type="date" aria-label="По" value={to} onChange={(e) => setParams({ from, to: e.target.value }, { replace: true })} />
        </span>
      </div>

      {error && <div className="card sx-msg" role="alert">{error}</div>}
      {data && cur && (
        <>
          <p className="muted sx-note">
            За {data.title.replace(/\.$/, "")}. Столбец {years[0]} — тот же период год назад
            {prev ? "." : ": в программе за него данных нет, впишите его в Word вручную."}
            {" "}Койко-дни считаются как в выписке. Число коек и план — в <Link to="/dictionaries">настройках</Link>,
            сёла для «сельских жителей» — в справочнике <Link to="/dictionaries?s=addresses">«Адреса»</Link>.
          </p>

          {auto.length > 0 && (
            <details className="card rp-card rp-check" aria-label="Проверить группы">
              <summary><h2>Проверьте группы: {auto.length} {plural(auto.length, "история", "истории", "историй")}</h2></summary>
              <span className="muted">
                Для этих историй группа «Структуры пролеченных» не выбрана при выписке — программа подобрала её по диагнозу.
                Поправьте, если пациент лежал по другому поводу; выбранная группа сохранится в истории.
              </span>
              <div className="rp-scroll">
                <table className="rp-table rp-auto">
                  <thead><tr><th>№</th><th className="rp-first">Пациент и диагноз</th><th>Группа</th></tr></thead>
                  <tbody>
                    {auto.map((a) => (
                      <tr key={a.caseId}>
                        <td><Link to={`/case/${a.caseId}`}>{a.number}</Link></td>
                        <td className="rp-first"><b>{a.patient}</b><br /><span className="muted">{a.dx || "диагноз не указан"}</span></td>
                        <td>
                          <select className="in" value={a.group} onChange={(e) => choose(a.caseId, e.target.value)}>
                            {data.groups.map((g) => <option key={g}>{g}</option>)}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}

          <div className="rp-grid">
            <MainTable cur={cur} prev={prev} years={years} />
            <section className="card rp-card" aria-label="Исходы">
              <h2>Из выписанных больных</h2>
              {cur.outcomes.length === 0 ? <p className="muted">За период никого не выписали.</p> : (
                <table className="rp-table rp-main">
                  <tbody>{cur.outcomes.map((o) => <tr key={o.label}><td className="rp-first">{o.label}</td><td><b>{o.count}</b></td></tr>)}</tbody>
                </table>
              )}
              {cur.main.channelUnknown > 0 && (
                <p className="muted rp-warn">
                  У {cur.main.channelUnknown} {plural(cur.main.channelUnknown, "поступившего", "поступивших", "поступивших")} не указано, как поступил
                  (экстренно или планово) — для них строки госпитализации не заполнятся. Поле — в окне поступления.
                </p>
              )}
              {cur.surgery.urgencyUnknown > 0 && (
                <p className="muted rp-warn">
                  У {cur.surgery.urgencyUnknown} {plural(cur.surgery.urgencyUnknown, "операции", "операций", "операций")} не отмечено «срочно» или «планово» — поле в протоколе операции.
                </p>
              )}
            </section>
          </div>

          <Nested title="Структура пролеченных больных" first="Наименование" cur={cur.structure} prev={prev?.structure ?? null} years={years} />
          <Nested title="Операции" first="Наименование" cur={cur.operations} prev={prev?.operations ?? null} years={years} />
        </>
      )}
    </main>
  );
}
