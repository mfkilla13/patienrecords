import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, Stats, StatsPoint } from "../api";
import { fullDate, plural, todayIso } from "../format";
import "./stats.css";

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function presets(): { key: string; label: string; from: string; to: string }[] {
  const t = new Date();
  const y = t.getFullYear();
  const back = (months: number) => iso(new Date(y, t.getMonth() - months + 1, 1));
  return [
    { key: "month", label: "Этот месяц", from: back(1), to: todayIso() },
    { key: "3m", label: "3 месяца", from: back(3), to: todayIso() },
    { key: "year", label: "Этот год", from: `${y}-01-01`, to: todayIso() },
    { key: "12m", label: "12 месяцев", from: back(12), to: todayIso() },
    { key: "all", label: "Всё время", from: "", to: "" },
  ];
}

const GROUP_WORD = { day: "по дням", month: "по месяцам", year: "по годам" } as const;
const num = (v: number) => String(v).replace(".", ",");

function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** Columns over time, one series: thin bars from one baseline, the peak labeled, the rest on hover. */
function Columns({ data, unit, format = num, empty }: {
  data: StatsPoint[]; unit: (v: number) => string; format?: (v: number) => string; empty: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const H = 190, top = 22, bottom = 26, left = 30;
  const values = data.map((d) => d.value ?? 0);
  const max = Math.max(...values, 0);
  if (!data.length || max === 0) return <p className="muted sx-empty">{empty}</p>;

  const step = max <= 5 ? 1 : max <= 10 ? 2 : max <= 25 ? 5 : max <= 50 ? 10 : Math.ceil(max / 5 / 10) * 10;
  const yMax = Math.ceil(max / step) * step;
  const ticks = Array.from({ length: yMax / step + 1 }, (_, i) => i * step);
  const plotW = Math.max(0, width - left - 4);
  const band = data.length ? plotW / data.length : 0;
  const barW = Math.max(2, Math.min(24, band - 2));
  const y = (v: number) => top + (H - top - bottom) * (1 - v / yMax);
  const every = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(plotW / 46))));
  const peak = values.indexOf(max);
  const r = Math.min(4, barW / 2);
  const tip = hover != null ? data[hover] : null;

  return (
    <div ref={ref} className="sx-plot" onMouseLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={H} role="img" aria-label={`Наибольшее значение ${format(max)}, ${data[peak].label}`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={width} y1={y(t)} y2={y(t)} className="sx-gridline" />
              <text x={left - 6} y={y(t) + 4} className="sx-tick" textAnchor="end">{t}</text>
            </g>
          ))}
          {data.map((d, i) => {
            const v = d.value;
            const cx = left + band * i + band / 2;
            const h = v ? y(0) - y(v) : 0;
            return (
              <g key={d.key}>
                {v != null && v > 0 && (
                  <path className={"sx-bar" + (hover === i ? " on" : "")}
                    d={`M${cx - barW / 2},${y(0)} v${-(h - r)} q0,${-r} ${r},${-r} h${barW - 2 * r} q${r},0 ${r},${r} v${h - r} z`} />
                )}
                {i === peak && <text x={cx} y={y(max) - 6} className="sx-val" textAnchor="middle">{format(max)}</text>}
                {i % every === 0 && <text x={cx} y={H - 8} className="sx-tick" textAnchor="middle">{d.label}</text>}
                <rect x={left + band * i} y={top - 10} width={band} height={H - top - bottom + 10} fill="transparent"
                  onMouseEnter={() => setHover(i)} />
              </g>
            );
          })}
        </svg>
      )}
      {tip && hover != null && (
        <div className="sx-tip" style={{ left: Math.min(Math.max(left + band * hover + band / 2, 70), width - 70), top: 0 }}>
          <b>{tip.label}</b>
          <span>{tip.value == null ? "нет выписанных" : unit(tip.value)}</span>
          {tip.n != null && tip.n > 0 && <span className="muted">по {tip.n} {plural(tip.n, "выписке", "выпискам", "выпискам")}</span>}
        </div>
      )}
    </div>
  );
}

/** A ranked share list: label, a thin bar, the count and the share. */
function Ranked({ data, empty, of }: { data: { label: string; value: number }[]; empty: string; of?: number }) {
  const total = of ?? data.reduce((a, b) => a + b.value, 0);
  const max = Math.max(...data.map((d) => d.value), 0);
  if (!total) return <p className="muted sx-empty">{empty}</p>;
  return (
    <ul className="sx-ranked">
      {data.map((d) => (
        <li key={d.label} title={`${d.label}: ${d.value} из ${total}`}>
          <span className="sx-rlabel">{d.label}</span>
          <span className="sx-rtrack"><span className="sx-rbar" style={{ width: `${(d.value / max) * 100}%` }} /></span>
          <span className="sx-rval"><b>{d.value}</b> <span className="muted">{Math.round((d.value / total) * 100)}%</span></span>
        </li>
      ))}
    </ul>
  );
}

function Chart({ title, sub, table, children }: {
  title: string; sub: string; table: [string, string][]; children: React.ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="card sx-card" aria-label={title}>
      <div className="sx-head">
        <div>
          <h2>{title}</h2>
          <span className="muted">{sub}</span>
        </div>
        <button type="button" className="link-btn" onClick={() => setAsTable((v) => !v)}>{asTable ? "графиком" : "таблицей"}</button>
      </div>
      {asTable ? (
        <div className="sx-table-wrap">
          <table className="bk-table">
            <tbody>{table.map(([a, b], i) => <tr key={i}><td>{a}</td><td><b>{b}</b></td></tr>)}</tbody>
          </table>
        </div>
      ) : children}
    </section>
  );
}

export function StatsPage() {
  const [params, setParams] = useSearchParams();
  const list = presets();
  const preset = params.get("p") ?? (params.get("from") || params.get("to") ? "custom" : "12m");
  const chosen = list.find((p) => p.key === preset);
  const from = chosen ? chosen.from : params.get("from") ?? "";
  const to = chosen ? chosen.to : params.get("to") ?? "";
  const [data, setData] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    api.stats(from, to).then(setData, (e: Error) => setError(e.message));
  }, [from, to]);

  const setCustom = (k: "from" | "to", v: string) => {
    setParams({ from: k === "from" ? v : from, to: k === "to" ? v : to }, { replace: true });
  };

  const g = data ? GROUP_WORD[data.group] : "";
  // 10,8 дня: a fractional number takes the genitive singular.
  const days = (v: number) => `${num(v)} ${Number.isInteger(v) ? plural(v, "день", "дня", "дней") : "дня"}`;
  const people = (v: number) => `${v} ${plural(v, "человек", "человека", "человек")}`;
  const nonEmpty = (pts: StatsPoint[], fmt: (v: number) => string) =>
    pts.filter((p) => p.value).map((p) => [p.label, fmt(p.value!)] as [string, string]);

  return (
    <main className="page sx">
      <div className="sx-top">
        <h1>Статистика</h1>
        <div style={{ flex: 1 }} />
        <div className="seg" role="radiogroup" aria-label="Период">
          {list.map((p) => (
            <button key={p.key} type="button" role="radio" aria-checked={preset === p.key} className={preset === p.key ? "on" : ""}
              onClick={() => setParams({ p: p.key }, { replace: true })}>{p.label}</button>
          ))}
        </div>
        <span className="sx-range">
          <input className="in" type="date" aria-label="С" value={from || data?.from || ""} max={to || todayIso()} onChange={(e) => setCustom("from", e.target.value)} />
          <span className="muted">—</span>
          <input className="in" type="date" aria-label="По" value={to || data?.to || ""} max={todayIso()} onChange={(e) => setCustom("to", e.target.value)} />
        </span>
      </div>

      {error && <div className="card sx-msg" role="alert">{error}</div>}
      {data && (
        <>
          <div className="sx-tiles">
            <div className="card sx-tile"><span>Поступило</span><b>{data.totals.admitted}</b></div>
            <div className="card sx-tile"><span>Выписано</span><b>{data.totals.discharged}</b></div>
            <div className="card sx-tile"><span>Средний койко-день</span><b>{data.totals.avgStay != null ? num(data.totals.avgStay) : "—"}</b></div>
            <div className="card sx-tile"><span>Сейчас в отделении</span><b>{data.totals.inDepartment}</b></div>
          </div>
          <p className="muted sx-note">
            {fullDate(data.from)} — {fullDate(data.to)}. Поступления считаются по дате поступления, выписки, койко-дни и исходы — по дате выписки.
          </p>

          <div className="sx-grid">
            <Chart title="Госпитализации" sub={`поступившие ${g}`} table={nonEmpty(data.admissions, people)}>
              <Columns data={data.admissions} unit={people} empty="За этот период никто не поступал." />
            </Chart>
            <Chart title="Выписки" sub={`выписанные ${g}`} table={nonEmpty(data.discharges, people)}>
              <Columns data={data.discharges} unit={people} empty="За этот период никого не выписали." />
            </Chart>
            <Chart title="Средняя длительность лечения" sub={`койко-дней ${g}, по выписанным`} table={nonEmpty(data.avgStay, days)}>
              <Columns data={data.avgStay} unit={days} empty="За этот период никого не выписали." />
            </Chart>
            <Chart title="Исходы" sub="у выписанных за период" table={data.outcomes.map((d) => [d.label, String(d.value)])}>
              <Ranked data={data.outcomes} empty="За этот период никого не выписали." />
            </Chart>
            <Chart title="Диагнозы" sub="у поступивших за период, по группам, как в архиве" table={data.diagnoses.map((d) => [d.label, String(d.value)])}>
              <Ranked data={data.diagnoses} of={data.totals.admitted} empty="За этот период никто не поступал." />
            </Chart>
          </div>
        </>
      )}
    </main>
  );
}
