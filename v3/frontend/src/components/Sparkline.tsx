const WEEKDAY = new Intl.DateTimeFormat("ru-RU", { weekday: "short" });
const ddmm = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

/** A week behind a summary tile: a thin line with a soft fill, one hover target per day. Look only — no axes. */
export function Sparkline({ values, days, unit, label }: { values: number[]; days: string[]; unit: string; label?: (iso: string) => string }) {
  const W = 100, H = 30, PAD = 3;
  const max = Math.max(1, ...values);
  const x = (i: number) => (values.length > 1 ? (i / (values.length - 1)) * W : W / 2);
  const y = (v: number) => H - PAD - (v / max) * (H - 2 * PAD);
  const line = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      <polygon className="spark-fill" points={`0,${H} ${line} ${W},${H}`} />
      <polyline className="spark-line" points={line} vectorEffect="non-scaling-stroke" />
      {values.map((v, i) => (
        <rect key={i} x={x(i) - W / values.length / 2} y={0} width={W / values.length} height={H} fill="transparent">
          <title>{`${label ? label(days[i]) : `${WEEKDAY.format(new Date(days[i] + "T00:00"))} ${ddmm(days[i])}`}: ${v} ${unit}`}</title>
        </rect>
      ))}
    </svg>
  );
}

/** «↑ 2» / «↓ 3» / «= » against yesterday (or the given value), in text colour: more admissions is neither good nor bad. */
export function Delta({ values, before, against = "к вчера", title }: { values: number[]; before?: number; against?: string; title?: string }) {
  const prev = before ?? values[values.length - 2];
  if (prev === undefined) return null;
  const d = values[values.length - 1] - prev;
  const text = d > 0 ? `↑ ${d}` : d < 0 ? `↓ ${-d}` : "= ";
  return (
    <span className="delta" title={title ?? `вчера ${prev}`}>
      {text}<small>{against}</small>
    </span>
  );
}
