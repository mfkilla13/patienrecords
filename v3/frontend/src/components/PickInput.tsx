import { useEffect, useRef, useState } from "react";

/** What the grid offers. Values are written the way the forms always stored them: a comma, «+»/«-» for lenses. */
export type PickKind = "vis" | "corr" | "vgd" | "bp" | "sys" | "dia" | "rate" | "elasto" | "ro" | "c";

const range = (from: number, to: number, step: number, fmt: (v: number) => string) =>
  Array.from({ length: Math.round((to - from) / step) + 1 }, (_, i) => fmt(from + i * step));
const comma = (v: number, digits: number) => v.toFixed(digits).replace(".", ",");

// Vis on the Sivtsev chart: 0,1–1,0 is the chart itself, 0,01–0,09 low vision (Pole's formula), 1,5 and 2,0 the top
// lines. Below 0,01 (count fingers, hand motion, light perception) is chosen in «Статус», not here.
const VIS_ROWS = [
  range(0.1, 1.0, 0.1, (v) => comma(v, 1)),
  range(0.01, 0.09, 0.01, (v) => comma(v, 2)),
  ["1,5", "2,0"],
];
// Spherical correction, dioptres.
const CORR_ROWS = [
  range(-6, -3.5, 0.5, (v) => comma(v, 1)),
  range(-3, -0.5, 0.5, (v) => comma(v, 1)),
  range(0.5, 3, 0.5, (v) => `+${comma(v, 1)}`),
  range(3.5, 6, 0.5, (v) => `+${comma(v, 1)}`),
];
// IOP by Maklakov (10 g), mm Hg: 18–26 is the norm.
export const VGD_NORM = { low: 18, high: 26 };
const VGD_ROWS = [range(8, 17, 1, String), range(18, 26, 1, String), range(27, 36, 1, String), range(37, 45, 1, String)];

// Blood pressure, mm Hg, step 5: from 140/90 it is raised, from 180/110 very high.
const SYS_ROWS = [range(80, 125, 5, String), range(130, 175, 5, String), range(180, 220, 5, String)];
const DIA_ROWS = [range(40, 85, 5, String), range(90, 130, 5, String)];

// Heart rate and pulse, beats per minute, step 2: 60–90 is the norm.
const RATE_NORM = { low: 60, high: 90 };
const RATE_ROWS = [range(50, 66, 2, String), range(68, 84, 2, String), range(86, 102, 2, String), range(104, 120, 2, String)];

// Elastotonometry (Filatov–Kalfa): four readings with the 5 · 7,5 · 10 · 15 g weights, written «18-19-20-25».
const ELASTO_ROWS = [range(10, 19, 1, String), range(20, 29, 1, String), range(30, 39, 1, String)];
// Nesterov tonography: Ро (true IOP, mm Hg) and С (outflow facility). КБ and F are calculated from them.
const RO_ROWS = [range(8, 17, 1, String), range(18, 26, 1, String), range(27, 36, 1, String), range(37, 45, 1, String)];
const C_ROWS = [range(0.05, 0.14, 0.01, (v) => comma(v, 2)), range(0.15, 0.24, 0.01, (v) => comma(v, 2)),
  range(0.25, 0.34, 0.01, (v) => comma(v, 2)), range(0.35, 0.6, 0.05, (v) => comma(v, 2))];

type Part = "sys" | "dia";
type Section = { rows: string[][]; label?: string; part?: Part };
const SECTIONS: Record<PickKind, Section[]> = {
  vis: [{ rows: VIS_ROWS }],
  corr: [{ rows: CORR_ROWS }],
  vgd: [{ rows: VGD_ROWS }],
  bp: [{ rows: SYS_ROWS, label: "верхнее", part: "sys" }, { rows: DIA_ROWS, label: "нижнее", part: "dia" }],
  sys: [{ rows: SYS_ROWS, part: "sys" }],
  dia: [{ rows: DIA_ROWS, part: "dia" }],
  rate: [{ rows: RATE_ROWS }],
  elasto: [{ rows: ELASTO_ROWS }],
  ro: [{ rows: RO_ROWS }],
  c: [{ rows: C_ROWS }],
};
const BP_HINT = "от 140/90 — повышенное, от 180/110 — очень высокое";
const HINT: Record<PickKind, string> = {
  vis: "ниже 0,01 — в «Статусе»",
  corr: "сильнее ±6,0 — впишите сами",
  vgd: `норма ${VGD_NORM.low}–${VGD_NORM.high} мм рт. ст.`,
  bp: "сначала верхнее, потом нижнее; " + BP_HINT,
  sys: BP_HINT,
  dia: BP_HINT,
  rate: `норма ${RATE_NORM.low}–${RATE_NORM.high} уд/мин; другое — впишите сами`,
  elasto: "четыре числа по порядку грузов: 5 · 7,5 · 10 · 15 г",
  ro: "мм рт. ст.; десятые — впишите сами",
  c: "мм³/мин на мм рт. ст.",
};

function tone(kind: PickKind, part: Part | undefined, v: string): string {
  const n = Number(v);
  if (kind === "vgd") return n > VGD_NORM.high ? " high" : n >= VGD_NORM.low ? " norm" : "";
  if (kind === "ro") return n > VGD_NORM.high ? " high" : "";
  if (kind === "rate") return n < RATE_NORM.low || n > RATE_NORM.high ? " high" : " norm";
  if (part === "sys") return n >= 180 ? " crit" : n >= 140 ? " high" : "";
  if (part === "dia") return n >= 110 ? " crit" : n >= 90 ? " high" : "";
  return "";
}

/** «135/80» -> ["135", "80"]; anything typed by hand that is not a pair stays as the first part. */
function splitBp(value: string): [string, string] {
  const [sys = "", dia = ""] = value.split("/").map((x) => x.trim());
  return [sys, dia];
}

type Props = Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  kind: PickKind;
  value: string;
  onChange: (v: string) => void;
  wrapClassName?: string;
};

/** An input that opens a grid of usual values on click: one click fills it in. Typing still works. */
export function PickInput({ kind, value, onChange, wrapClassName, disabled, onFocus, onBlur, ...rest }: Props) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  const [sys, dia] = splitBp(value);
  const series = value.split("-").map((x) => x.trim()).filter(Boolean);
  const chosen = (part: Part | undefined, v: string) =>
    kind === "bp" ? (part === "sys" ? sys : dia) === v : kind === "elasto" ? false : v === value;

  const pick = (part: Part | undefined, v: string) => {
    if (kind === "elasto") {
      // Four readings in a row: each click adds the next one; after the fourth a click starts over.
      const next = series.length >= 4 ? [v] : [...series, v];
      onChange(next.join("-"));
      if (next.length === 4) setOpen(false);
      return;
    }
    if (kind !== "bp") {
      onChange(v === value ? "" : v);      // a second click on the chosen value clears it
      setOpen(false);
      return;
    }
    // Both halves in one field: the upper first (the grid stays open), then the lower closes it.
    const next = part === "sys" ? [v === sys ? "" : v, dia] : [sys, v === dia ? "" : v];
    onChange(next[0] || next[1] ? `${next[0]}/${next[1]}` : "");
    if (part === "dia" && next[0] && next[1]) setOpen(false);
  };

  return (
    <span ref={wrap} className={"pk" + (wrapClassName ? ` ${wrapClassName}` : "")}>
      <input
        {...rest}
        value={value}
        disabled={disabled}
        autoComplete="off"
        onChange={(e) => onChange(e.target.value)}
        onFocus={(e) => { if (!disabled) setOpen(true); onFocus?.(e); }}
        onClick={() => { if (!disabled) setOpen(true); }}
        onBlur={(e) => { if (!wrap.current?.contains(e.relatedTarget as Node)) setOpen(false); onBlur?.(e); }}
        onKeyDown={(e) => { if (e.key === "Escape" || e.key === "Enter") setOpen(false); rest.onKeyDown?.(e); }}
      />
      {open && (
        <span className={`pk-pop pk-${kind}`} role="listbox" aria-label="Выбрать значение">
          {SECTIONS[kind].map((sec, k) => (
            <span key={k} className="pk-sec">
              {sec.label && <span className="pk-label">{sec.label}</span>}
              {sec.rows.map((row, i) => (
                <span key={i} className="pk-row">
                  {row.map((v) => (
                    <button key={v} type="button" role="option" aria-selected={chosen(sec.part, v)} tabIndex={-1}
                      className={"pk-v" + tone(kind, sec.part, v) + (chosen(sec.part, v) ? " on" : "")}
                      onMouseDown={(e) => e.preventDefault()} onClick={() => pick(sec.part, v)}>{v}</button>
                  ))}
                </span>
              ))}
            </span>
          ))}
          <span className="pk-hint">
            {kind === "elasto" && series.length < 4 ? `${["5", "7,5", "10", "15"][series.length]} г — ` : ""}{HINT[kind]}
          </span>
        </span>
      )}
    </span>
  );
}
