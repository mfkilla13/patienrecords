/**
 * Страховой анамнез: status, disability group (Roman, as written in records) and «по зрению», put together
 * into the line 2.9 wrote: «Гражданин ПМР (пенсионер, не работает, инв. II гр. по зрению)».
 * A line typed by hand in 2.9 that does not fit this shape is kept as it is until something is chosen.
 */
type Parts = { status: string; disability: string; vision: boolean };

const CITIZEN = "Гражданин ПМР";

export function composeInsurance(p: Parts, noCitizen: string): string {
  const dis = !p.disability ? "" : p.disability === "детства"
    ? `инвалид детства${p.vision ? " по зрению" : ""}` : `инв. ${p.disability} гр.${p.vision ? " по зрению" : ""}`;
  if (p.status === noCitizen) return dis ? noCitizen.replace(")", `, ${dis})`) : noCitizen;
  return `${CITIZEN} (${[p.status, dis].filter(Boolean).join(", ")})`;
}

export function parseInsurance(text: string, statuses: string[], noCitizen: string): Parts | null {
  const t = (text || "").trim();
  let status = "", rest = "";
  if (t.startsWith(noCitizen.replace(")", ""))) {
    status = noCitizen;
    rest = t.slice(noCitizen.length - 1).replace(/^,\s*/, "").replace(/\)$/, "");
  } else {
    const m = t.match(/^Гражданин ПМР \((.*)\)$/);
    if (!m) return null;
    status = statuses.find((s) => m[1] === s || m[1].startsWith(`${s}, `)) ?? "";
    if (!status) return null;
    rest = m[1].slice(status.length).replace(/^,\s*/, "");
  }
  if (!rest) return { status, disability: "", vision: false };
  const d = rest.match(/^(?:инв\. (I{1,3}) гр\.|инвалид (детства))( по зрению)?$/);
  return d ? { status, disability: d[1] ?? d[2], vision: Boolean(d[3]) } : null;
}

export function InsurancePicker({ value, onChange, statuses, noCitizen, disability, disabled }: {
  value: string; onChange: (v: string) => void; statuses: string[]; noCitizen: string; disability: string[]; disabled?: boolean;
}) {
  const parsed = parseInsurance(value, statuses, noCitizen);
  const p: Parts = parsed ?? { status: "", disability: "", vision: false };
  const set = (next: Partial<Parts>) => {
    const merged = { ...p, ...next };
    onChange(composeInsurance({ ...merged, status: merged.status || statuses[0] }, noCitizen));
  };
  return (
    <span className="ex-insurance">
      <select className="in" value={parsed ? p.status : ""} disabled={disabled} aria-label="Статус"
        onChange={(e) => set({ status: e.target.value })}>
        {!parsed && <option value="">{value ? `как записано: ${value}` : "не выбрано"}</option>}
        {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        <option value={noCitizen}>без гражданства ПМР (платная основа)</option>
      </select>
      <select className="in" value={p.disability} disabled={disabled} aria-label="Инвалидность"
        onChange={(e) => set({ disability: e.target.value, vision: e.target.value ? p.vision : false })}>
        <option value="">инвалидности нет</option>
        {disability.map((d) => <option key={d} value={d}>{d === "детства" ? "инвалид детства" : `инв. ${d} гр.`}</option>)}
      </select>
      <label className="ex-inline">
        <input type="checkbox" checked={p.vision} disabled={disabled || !p.disability} onChange={(e) => set({ vision: e.target.checked })} />
        по зрению
      </label>
      <span className="muted ex-insurance-text">{value || "—"}</span>
    </span>
  );
}
