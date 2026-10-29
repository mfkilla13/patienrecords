import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Checks } from "../api";
import { plural } from "../format";
import "./checks.css";

/** «Проверка данных»: likely typos, grouped, each with a link to where it is fixed. */
export function ChecksPage() {
  const [data, setData] = useState<Checks | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.checks().then(setData, (e: Error) => setError(e.message));
  }, []);

  const confirm = async (check: string, item: string, fio: string) => {
    if (!window.confirm(`${fio}: оставить как есть и больше не показывать?`)) return;
    setBusy(`${check}:${item}`);
    try {
      setData(await api.confirmCheck(check, item));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (error) return <main className="page ck"><div className="card" style={{ padding: 24 }}>Не удалось проверить данные: {error}</div></main>;
  if (!data) return <main className="page ck"><p className="muted">Проверяем данные…</p></main>;

  const found = data.groups.filter((g) => g.items.length);
  return (
    <main className="page ck">
      <div className="ck-head">
        <Link to="/" className="round-btn white" aria-label="Назад к отделению">
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <div>
          <h1>Проверка данных</h1>
          <div className="muted">
            {data.total
              ? `${data.total} ${plural(data.total, "неточность", "неточности", "неточностей")} — исправьте или отметьте «Это верно»`
              : "Неточностей не найдено"}
            {data.confirmed > 0 && ` · отмечено «Это верно»: ${data.confirmed}`}
          </div>
        </div>
      </div>

      {found.length === 0 && (
        <div className="card ck-clean">
          <span className="ck-ok" aria-hidden="true">✓</span>
          Всё чисто: даты рождения, даты записей, выписки и диагнозы в порядке.
        </div>
      )}

      {found.map((g) => (
        <section key={g.key} className="card ck-group" aria-label={g.title}>
          <div className="ck-group-head">
            <h2>{g.title} <span className="pill sm tone-amber">{g.items.length}</span></h2>
            <span className="muted">{g.hint}</span>
          </div>
          <ul className="ck-list">
            {g.items.map((it) => (
              <li key={it.item}>
                <span className="ck-num">№ {it.number}</span>
                <Link to={`/case/${it.caseId}`} className="ck-fio">{it.fio}</Link>
                <span className="ck-detail">{it.detail}</span>
                <span className="ck-act">
                  <Link to={it.link} className="btn small primary">{g.fix}</Link>
                  <button type="button" className="btn small" disabled={busy === `${g.key}:${it.item}`}
                    onClick={() => confirm(g.key, it.item, it.fio)}>Это верно</button>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </main>
  );
}
