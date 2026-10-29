import { useLayoutEffect, useRef, useState } from "react";
import { plural } from "../format";

export interface DayPoint { date: string; inDepartment: number; admitted: number }

const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
const ru = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;
const people = (n: number) => `${n} ${plural(n, "человек", "человека", "человек")}`;

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

/** How many lay in the department each day: an area under a 2px line, with the number of beds as a reference. */
export function Occupancy({ days, beds }: { days: DayPoint[]; beds: number | null }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  if (days.length < 2) return <p className="muted sx-empty">Слишком короткий период.</p>;
  const H = 210, top = 18, bottom = 26, left = 30, right = 8;
  const max = Math.max(...days.map((d) => d.inDepartment), beds ?? 0, 1);
  const step = max <= 10 ? 2 : max <= 30 ? 5 : 10;
  const yMax = Math.ceil((max + 1) / step) * step;
  const plotW = Math.max(10, width - left - right);
  const x = (i: number) => left + (plotW * i) / (days.length - 1);
  const y = (v: number) => top + (H - top - bottom) * (1 - v / yMax);
  const line = days.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.inDepartment).toFixed(1)}`).join("");
  const area = `${line}L${x(days.length - 1).toFixed(1)},${y(0)}L${x(0).toFixed(1)},${y(0)}Z`;
  const ticks = Array.from({ length: yMax / step + 1 }, (_, i) => i * step);

  // X labels: the first of each month for a long period, otherwise every few days.
  const firsts = days.map((d, i) => ({ d, i })).filter(({ d }) => d.date.endsWith("-01"));
  const marks = firsts.length >= 2
    ? firsts.map(({ d, i }) => ({ i, label: MONTHS[Number(d.date.slice(5, 7)) - 1] + (d.date.slice(5, 7) === "01" ? ` ${d.date.slice(2, 4)}` : "") }))
    : days.map((d, i) => ({ i, label: `${d.date.slice(8, 10)}.${d.date.slice(5, 7)}` }));
  const every = Math.max(1, Math.ceil(marks.length / Math.max(2, Math.floor(plotW / 52))));
  const peak = days.reduce((b, d, i) => (d.inDepartment > days[b].inDepartment ? i : b), 0);
  const tip = hover != null ? days[hover] : null;

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left) / r.width) * (days.length - 1));
    setHover(Math.min(days.length - 1, Math.max(0, i)));
  };

  return (
    <div ref={ref} className="sx-plot" onMouseLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={H} role="img" aria-label={`Больше всего — ${people(days[peak].inDepartment)}, ${ru(days[peak].date)}`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} className="sx-gridline" />
              <text x={left - 6} y={y(t) + 4} className="sx-tick" textAnchor="end">{t}</text>
            </g>
          ))}
          {beds != null && beds > 0 && (
            <g>
              <line x1={left} x2={width - right} y1={y(beds)} y2={y(beds)} className="sx-beds" />
              <text x={width - right} y={y(beds) - 5} className="sx-tick" textAnchor="end">{beds} {plural(beds, "койка", "койки", "коек")}</text>
            </g>
          )}
          <path d={area} className="sx-area" />
          <path d={line} className="sx-line" />
          {marks.filter((_, k) => k % every === 0).map((m) => (
            <text key={m.i} x={x(m.i)} y={H - 8} className="sx-tick" textAnchor="middle">{m.label}</text>
          ))}
          {tip && hover != null && (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={top - 6} y2={y(0)} className="sx-cross" />
              <circle cx={x(hover)} cy={y(tip.inDepartment)} r={4.5} className="sx-dot" />
            </g>
          )}
          <rect x={left} y={top - 10} width={plotW} height={H - top - bottom + 10} fill="transparent" onMouseMove={onMove} />
        </svg>
      )}
      {tip && hover != null && (
        <div className="sx-tip" style={{ left: Math.min(Math.max(x(hover), 80), width - 80), top: 0 }}>
          <b>{ru(tip.date)}</b>
          <span>в отделении {people(tip.inDepartment)}</span>
          {beds ? <span className="muted">занято {Math.round((tip.inDepartment / beds) * 100)}% коек</span> : null}
          {tip.admitted > 0 && <span className="muted">поступило {tip.admitted}</span>}
        </div>
      )}
    </div>
  );
}

const SHADES = ["var(--hm-0)", "var(--hm-1)", "var(--hm-2)", "var(--hm-3)", "var(--hm-4)"];
const weekday = (iso: string) => (new Date(iso + "T00:00").getDay() + 6) % 7;     // Monday = 0

/** Admissions by day as a calendar: a column per week, a row per weekday, darker — more admissions. */
export function AdmissionsCalendar({ days }: { days: DayPoint[] }) {
  const [tip, setTip] = useState<{ d: DayPoint; x: number; y: number } | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  if (!days.length) return null;
  const max = Math.max(...days.map((d) => d.admitted), 1);
  const shade = (n: number) => (n === 0 ? SHADES[0] : SHADES[Math.min(4, Math.max(1, Math.ceil((n / max) * 4)))]);
  // Each month is its own block of week columns, set apart by a gap: a new column starts on Monday and on the 1st.
  const C = 14, G = 3, L = 24, T = 18, MG = 12;
  let col = -1, block = -1;
  const cells = days.map((d, i) => {
    const firstOfMonth = i === 0 || d.date.endsWith("-01");
    if (firstOfMonth) block += 1;
    if (firstOfMonth || weekday(d.date) === 0) col += 1;
    return { d, row: weekday(d.date), x: L + col * (C + G) + block * MG, first: firstOfMonth };
  });
  const width = cells[cells.length - 1].x + C + 2;
  const months = cells.filter((c) => c.first).map((c) => ({ x: c.x, label: MONTHS[Number(c.d.date.slice(5, 7)) - 1] }));
  const byWeekday = WEEKDAYS.map((w, k) => ({ w, n: days.filter((d) => weekday(d.date) === k).reduce((a, d) => a + d.admitted, 0) }));
  const top = byWeekday.reduce((a, b) => (b.n > a.n ? b : a));

  return (
    <div ref={wrap} className="sx-cal-wrap" onMouseLeave={() => setTip(null)}>
      <div className="sx-cal-scroll">
        <svg width={width} height={T + 7 * (C + G)} role="img" aria-label={`Календарь поступлений; чаще всего поступают в ${top.w}`}>
          {months.map((m, k) => (months[k + 1] && months[k + 1].x - m.x < 2 * (C + G) ? null
            : <text key={`${m.x}-${m.label}`} x={m.x} y={11} className="sx-tick">{m.label}</text>))}
          {[0, 2, 4].map((r) => <text key={r} x={0} y={T + r * (C + G) + 11} className="sx-tick">{WEEKDAYS[r]}</text>)}
          {cells.map(({ d, x, row }) => (
            <rect key={d.date} x={x} y={T + row * (C + G)} width={C} height={C} rx={3}
              fill={shade(d.admitted)} className="sx-cell"
              onMouseEnter={(e) => {
                const box = wrap.current?.getBoundingClientRect();
                const r = e.currentTarget.getBoundingClientRect();
                if (box) setTip({ d, x: r.left - box.left + C / 2, y: r.top - box.top });
              }} />
          ))}
        </svg>
      </div>
      <div className="sx-cal-legend">
        <span className="muted">меньше</span>
        {SHADES.map((s) => <span key={s} className="sx-cal-key" style={{ background: s }} />)}
        <span className="muted">больше</span>
        {top.n > 0 && <span className="muted sx-cal-note">чаще всего поступают в {top.w}: {people(top.n)} за период</span>}
      </div>
      {tip && (
        <div className="sx-tip" style={{ left: tip.x, top: tip.y }}>
          <b>{ru(tip.d.date)}, {WEEKDAYS[weekday(tip.d.date)]}</b>
          <span>{tip.d.admitted ? `поступило ${people(tip.d.admitted)}` : "никто не поступал"}</span>
        </div>
      )}
    </div>
  );
}
