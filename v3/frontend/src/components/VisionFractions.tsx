import { Vision } from "../api";

/** One OD-over-OS fraction cell. */
function Frac({ top, bottom, strong }: { top: string; bottom: string; strong?: boolean }) {
  return (
    <span className="frac" style={strong ? { fontWeight: 700 } : undefined}>
      <span>{top || " "}</span>
      <span>{bottom || " "}</span>
    </span>
  );
}

/** «0,8 с коррекцией −1,5 D = 1,0», «0,1 n.k.» — one eye written out, as on the printed sheet. */
function eyeText(e: Vision["od"]): string {
  const parts = [e.vis, e.status].filter(Boolean);
  if (e.corr || e.result) parts.push("с коррекцией" + (e.corr ? ` ${e.corr}` : "") + (e.result ? ` = ${e.result}` : ""));
  return parts.join(" ") || "—";
}

/**
 * Vis and ВГД written the way ophthalmologists do: Vis OD/OS = 0,3/0,6   ВГД OD/OS = 18/23 мм рт. ст.
 * With a correction or a status Vis goes per eye in two lines (a fraction with blank halves reads as nonsense).
 */
export function VisionFractions({ v, accent }: { v: Vision; accent?: boolean }) {
  const { od, os } = v;
  const hasVis = od.vis || os.vis;
  const hasStatus = od.status || os.status;
  const hasCorr = od.corr || os.corr || od.result || os.result;
  const hasIop = od.iop || os.iop;
  const valueStyle = accent ? { color: "var(--accent-hover)" } : undefined;

  return (
    <span className="vision">
      {hasVis && (
        <span className="vision-item">
          <b>Vis</b>
          {hasStatus || hasCorr ? (
            <span className="vision-eyes" style={valueStyle}>
              <span>OD = {eyeText(od)}</span>
              <span>OS = {eyeText(os)}</span>
            </span>
          ) : <>
          <Frac top="OD" bottom="OS" />
          =
          <span style={valueStyle}>
            <Frac top={od.vis || "—"} bottom={os.vis || "—"} strong />
          </span>
          </>}
        </span>
      )}
      {hasIop && (
        <span className="vision-item">
          <b>ВГД</b>
          <Frac top="OD" bottom="OS" />
          =
          <span style={valueStyle}>
            <Frac top={od.iop || "—"} bottom={os.iop || "—"} strong />
          </span>
          <span className="muted" style={{ fontSize: 13 }}>мм рт. ст.</span>
        </span>
      )}
    </span>
  );
}
