import { useEffect, useState } from "react";
import { api } from "../api";

/** Printing a separate A4 document (лист назначений): page previews, the printer, copies. */
export function DocPrintDialog({ title, pageCount, pageUrl, pdfUrl, print, onClose }: {
  title: string;
  pageCount: () => Promise<number>;
  pageUrl: (page: number, stamp: number) => string;
  pdfUrl: string;
  print: (printer: string, copies: number) => Promise<unknown>;
  onClose: () => void;
}) {
  const [pages, setPages] = useState(0);
  const [stamp] = useState(() => Date.now());
  const [printers, setPrinters] = useState<{ list: string[]; chosen: string }>({ list: [], chosen: "" });
  const [copies, setCopies] = useState(1);
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    pageCount().then(setPages, (e: Error) => setStatus({ kind: "error", text: e.message }));
    api.printers().then((p) => setPrinters({ list: p.printers, chosen: p.default ?? p.printers[0] ?? "" }), () => undefined);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  const send = async () => {
    setBusy(true);
    setStatus(null);
    try {
      await print(printers.chosen, copies);
      setStatus({ kind: "ok", text: `Отправлено на «${printers.chosen}»${copies > 1 ? ` — ${copies} экз.` : ""}` });
    } catch (e) {
      setStatus({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pr-overlay" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="pr-dialog dp-dialog">
        <div className="dp-head">
          <h2>{title}</h2>
          <button type="button" className="btn" onClick={onClose}>Закрыть</button>
        </div>
        <div className="ds-print">
          <div className="ds-pages">
            {pages === 0 && !status && <p className="muted">Готовим лист…</p>}
            {Array.from({ length: pages }, (_, i) => (
              <a key={i} href={pdfUrl} target="_blank" rel="noreferrer" className="ds-page" title="Открыть PDF">
                <img src={pageUrl(i + 1, stamp)} alt={`${title}, страница ${i + 1}`} />
              </a>
            ))}
          </div>
          <div className="ds-print-side">
            <label className="lbl">Принтер
              <select className="in" value={printers.chosen} onChange={(e) => setPrinters({ ...printers, chosen: e.target.value })}>
                {printers.list.length === 0 && <option value="">принтеры не найдены</option>}
                {printers.list.map((p) => <option key={p}>{p}</option>)}
              </select>
            </label>
            <label className="lbl">Экземпляров
              <span className="ds-row">
                {[1, 2, 3].map((n) => (
                  <button key={n} type="button" className={"chip" + (copies === n ? " on" : "")} onClick={() => setCopies(n)}>{n}</button>
                ))}
              </span>
            </label>
            <button type="button" className="btn primary" disabled={!printers.chosen || busy || pages === 0} onClick={send}>
              {busy ? "Отправляем…" : "Напечатать"}
            </button>
            <a className="btn" href={pdfUrl} target="_blank" rel="noreferrer">Открыть PDF</a>
            {status && <span className={"st-status " + status.kind} role="status">{status.text}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
