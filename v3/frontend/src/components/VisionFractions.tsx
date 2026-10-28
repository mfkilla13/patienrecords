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

/**
 * Vis and ВГД written the way ophthalmologists do:
 * Vis OD/OS = 0,3/0,01  n.k./…  +2,0 D/… = 0,5/…    ВГД OD/OS = 18/23 мм рт. ст.
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
          <Frac top="OD" bottom="OS" />
          =
          <span style={valueStyle}>
            <Frac top={od.vis || "—"} bottom={os.vis || "—"} strong />
          </span>
          {hasStatus && <Frac top={od.status} bottom={os.status} />}
          {hasCorr && (
            <>
              <Frac top={od.corr} bottom={os.corr} />
              =
              <Frac top={od.result} bottom={os.result} strong />
            </>
          )}
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
