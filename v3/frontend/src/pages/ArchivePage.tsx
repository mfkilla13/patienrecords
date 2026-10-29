import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ArchiveResult } from "../api";
import { fullDate, plural, shortDate } from "../format";
import "./department.css";
import "./archive.css";

const OUTCOME_TONES: Record<string, string> = {
  "улучшение": "tone-green", "без перемен": "tone-neutral", "ухудшение": "tone-amber", "перевод": "tone-blue",
};

export function ArchivePage() {
  const navigate = useNavigate();
  // Filters live in the address, so coming back from an opened history keeps them.
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const period = params.get("period") ?? "all";
  const dx = params.get("dx") ?? "";
  const outcome = params.get("outcome") ?? "";
  const page = Number(params.get("page") ?? "1") || 1;
  const [query, setQuery] = useState(q);
  const [data, setData] = useState<ArchiveResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries({ page: "1", ...patch })) {
      if (v && !(k === "period" && v === "all") && !(k === "page" && v === "1")) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };

  // Typing searches after a short pause, not on every letter.
  useEffect(() => {
    const t = window.setTimeout(() => { if (query !== q) set({ q: query }); }, 300);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  useEffect(() => {
    api.archiveList({ q, period, dx, outcome, page }).then(setData, (e: Error) => setError(e.message));
  }, [q, period, dx, outcome, page]);

  const filtered = Boolean(q || dx || outcome || period !== "all");
  const periodLabel = data?.periods.find((p) => p.value === period)?.label ?? "";

  return (
    <main className="page dep">
      <div className="dep-head">
        <h1>Архив</h1>
        {data && <span className="count-badge">{data.total} {plural(data.total, "закрытая история", "закрытые истории", "закрытых историй")}</span>}
      </div>

      <section className="card ar-filters" aria-label="Фильтры">
        <label className="lbl ar-q">Поиск
          <span className="search">
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="muted">
              <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
            </svg>
            <input type="search" placeholder="Фамилия, № истории, дата рождения, диагноз" value={query} onChange={(e) => setQuery(e.target.value)} />
          </span>
        </label>
        <label className="lbl ar-sel">Выписаны
          <select className="in ar-pill" value={period} onChange={(e) => set({ period: e.target.value })}>
            {(data?.periods ?? [{ value: "all", label: "За всё время" }]).map((p) => (
              <option key={p.value} value={p.value}>{p.value.length === 4 ? p.label : p.value === "all" ? p.label : `   ${p.label}`}</option>
            ))}
          </select>
        </label>
        <label className="lbl ar-sel">Диагноз
          <select className="in ar-pill" value={dx} onChange={(e) => set({ dx: e.target.value })}>
            <option value="">Все диагнозы</option>
            {data?.dxGroups.map((g) => <option key={g.value} value={g.value}>{g.value} ({g.count})</option>)}
          </select>
        </label>
        <label className="lbl ar-sel">Исход
          <select className="in ar-pill" value={outcome} onChange={(e) => set({ outcome: e.target.value })}>
            <option value="">Любой</option>
            {data?.outcomes.map((o) => <option key={o.value} value={o.value}>{o.value} ({o.count})</option>)}
          </select>
        </label>
        {filtered && (
          <button type="button" className="link-btn ar-reset" onClick={() => { setQuery(""); setParams(new URLSearchParams(), { replace: true }); }}>Сбросить</button>
        )}
      </section>

      {error && <div className="card" style={{ padding: 24 }}>Не удалось открыть архив: {error}</div>}

      <section className="card dep-table-card" aria-label="Результаты">
        <div className="ar-head">
          <b>Найдено {data?.found ?? "…"}</b>
          {periodLabel && period !== "all" && <span className="muted">· {periodLabel.toLowerCase()}</span>}
          <div style={{ flex: 1 }} />
          <a className="btn small" href={api.archiveCsvUrl({ q, period, dx, outcome })} download>Выгрузить в Excel</a>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="dep-table ar-table">
            <thead>
              <tr>
                <th style={{ width: 70, paddingLeft: 24 }}>№</th>
                <th>Пациент</th>
                <th>Диагноз</th>
                <th style={{ width: 150 }}>Даты</th>
                <th style={{ width: 70, textAlign: "right" }}>Дней</th>
                <th style={{ width: 170, paddingRight: 24 }}>Исход</th>
              </tr>
            </thead>
            <tbody>
              {data?.rows.map((r) => (
                <tr key={r.caseId} onClick={() => navigate(`/case/${r.caseId}`)}>
                  <td className="num" style={{ paddingLeft: 24 }}>{r.number}</td>
                  <td>
                    <Link to={`/case/${r.caseId}`} className="ar-name" onClick={(e) => e.stopPropagation()}>{r.patient}</Link>
                    {r.dob && <span className="muted ar-dob">{fullDate(r.dob)}</span>}
                  </td>
                  <td>
                    <span className="dep-dx">
                      {r.eye && <span className="pill sm tone-tint">{r.eye}</span>}
                      <span className="dep-dx-text">{r.dx || <span className="muted">не указан</span>}</span>
                    </span>
                  </td>
                  <td className="num muted-num">{shortDate(r.admittedAt)} – {shortDate(r.dischargedAt)}</td>
                  <td className="num" style={{ textAlign: "right", fontWeight: 600 }}>{r.days ?? "—"}</td>
                  <td style={{ paddingRight: 24 }}>
                    {r.outcome ? <span className={"pill " + (OUTCOME_TONES[r.outcome] ?? "tone-neutral")}>{r.outcome}</span> : <span className="muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && data.rows.length === 0 && (
          <p className="dep-empty muted">{data.total === 0 ? "В архиве пока нет историй." : "Ничего не найдено — измените поиск или фильтры."}</p>
        )}
        {data && data.pages > 1 && (
          <nav className="ar-pages" aria-label="Страницы">
            <span className="muted" style={{ marginRight: "auto" }}>
              {(data.page - 1) * data.size + 1}–{Math.min(data.page * data.size, data.found)} из {data.found}
            </span>
            <button type="button" className="ar-pg" aria-label="Предыдущая страница" disabled={data.page <= 1} onClick={() => set({ page: String(data.page - 1) })}>‹</button>
            {Array.from({ length: data.pages }, (_, i) => i + 1)
              .filter((n) => n === 1 || n === data.pages || Math.abs(n - data.page) <= 2)
              .map((n, i, arr) => (
                <span key={n} style={{ display: "contents" }}>
                  {i > 0 && n - arr[i - 1] > 1 && <span className="muted">…</span>}
                  <button type="button" className={"ar-pg" + (n === data.page ? " on" : "")} aria-current={n === data.page ? "page" : undefined}
                    onClick={() => set({ page: String(n) })}>{n}</button>
                </span>
              ))}
            <button type="button" className="ar-pg" aria-label="Следующая страница" disabled={data.page >= data.pages} onClick={() => set({ page: String(data.page + 1) })}>›</button>
          </nav>
        )}
      </section>
    </main>
  );
}
