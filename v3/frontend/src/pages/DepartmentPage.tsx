import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Department, DepartmentPatient, Stage } from "../api";
import { initials, plural, shortDate } from "../format";
import "./department.css";

type Filter = "all" | "noDiary" | "unprinted" | "discharged";

const STAGES: Record<Stage, { label: string; tone: string }> = {
  exam: { label: "Обследование", tone: "tone-neutral" },
  post_op: { label: "После операции", tone: "tone-blue" },
  discharged: { label: "Выписан", tone: "tone-green" },
};

const AVATAR_TONES = ["tone-green", "tone-blue", "tone-brown", "tone-violet"];

const FILTERS: { key: Filter; label: string; tone: string }[] = [
  { key: "all", label: "Все в отделении", tone: "tone-dark" },
  { key: "noDiary", label: "Нет дневника за сегодня", tone: "tone-green" },
  { key: "unprinted", label: "Записи ждут печати", tone: "tone-amber" },
  { key: "discharged", label: "Выписаны, ждут архива", tone: "tone-blue" },
];

function matches(p: DepartmentPatient, filter: Filter, query: string): boolean {
  if (filter === "noDiary" && (p.diaryToday || p.stage === "discharged")) return false;
  if (filter === "unprinted" && !p.unprinted) return false;
  if (filter === "discharged" && p.stage !== "discharged") return false;
  if (!query) return true;
  const haystack = `${p.number} ${p.surname} ${p.name} ${p.patronymic} ${p.diagnosis}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .every((word) => haystack.includes(word));
}

export function DepartmentPage() {
  const [data, setData] = useState<Department | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.department().then(setData, (e: Error) => setError(e.message));
  }, []);

  const rows = useMemo(
    () => (data ? data.patients.filter((p) => matches(p, filter, query.trim())) : []),
    [data, filter, query],
  );

  if (error) {
    return (
      <main className="page dep">
        <div className="card dep-message">Не удалось загрузить отделение: {error}</div>
      </main>
    );
  }

  return (
    <main className="page dep">
      <div className="dep-head">
        <h1>Отделение</h1>
        {data && (
          <span className="count-badge">
            {data.counts.all} {plural(data.counts.all, "пациент", "пациента", "пациентов")}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <Link to="/round" className="btn white">
          Обход
          {data && data.counts.noDiary > 0 && (
            <span className="pill sm tone-green">{data.counts.noDiary} без дневника</span>
          )}
        </Link>
        <Link to="/admission" className="btn primary">
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Новое поступление
        </Link>
      </div>

      <div className="dep-tiles" role="group" aria-label="Быстрые фильтры">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={"dep-tile" + (filter === f.key ? " on" : "")}
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
          >
            <span className={"dep-tile-num " + f.tone}>{data ? data.counts[f.key] : "…"}</span>
            <span>{f.label}</span>
          </button>
        ))}
      </div>

      <section className="card dep-table-card" aria-label="Пациенты в отделении">
        <div className="dep-toolbar">
          <label className="search" style={{ flex: "1 1 320px", maxWidth: 460 }}>
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="muted">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
            <span className="sr-only">Поиск</span>
            <input
              type="search"
              placeholder="Фамилия, № истории или диагноз"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div style={{ flex: 1 }} />
          <span className="muted">
            Сортировка: <b style={{ color: "var(--text)", fontWeight: 600 }}>по номеру истории</b>
          </span>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="dep-table">
            <thead>
              <tr>
                <th style={{ width: 64, paddingLeft: 24 }}>№</th>
                <th>Пациент</th>
                <th>Диагноз</th>
                <th style={{ width: 96 }}>Поступил</th>
                <th style={{ width: 60, textAlign: "right" }}>День</th>
                <th style={{ width: 170 }}>Этап</th>
                <th style={{ width: 150 }}>Дневник сегодня</th>
                <th style={{ width: 130, paddingRight: 24 }}>Печать</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p, i) => (
                <tr key={p.caseId} onClick={() => navigate(`/case/${p.caseId}`)}>
                  <td className="num" style={{ paddingLeft: 24 }}>{p.number}</td>
                  <td>
                    <Link to={`/case/${p.caseId}`} className="dep-patient" onClick={(e) => e.stopPropagation()}>
                      <span className={"avatar " + AVATAR_TONES[i % AVATAR_TONES.length]} aria-hidden="true">
                        {initials(p.surname, p.name)}
                      </span>
                      <span className="dep-patient-text">
                        <span className="dep-name">{[p.surname, p.name, p.patronymic].filter(Boolean).join(" ")}</span>
                        <span className="muted" style={{ fontSize: 13 }}>
                          {p.age != null ? `${p.age} ${plural(p.age, "год", "года", "лет")}` : "возраст не указан"}
                        </span>
                      </span>
                    </Link>
                  </td>
                  <td>
                    <span className="dep-dx" title={p.diagnosis}>
                      {p.eye && <span className="pill sm tone-tint">{p.eye}</span>}
                      <span className="dep-dx-text">{p.diagnosis || <span className="muted">не указан</span>}</span>
                    </span>
                  </td>
                  <td className="num muted-num">{shortDate(p.admittedAt)}</td>
                  <td className="num" style={{ textAlign: "right", fontWeight: 600 }}>{p.day ?? "—"}</td>
                  <td>
                    <span className={"pill " + STAGES[p.stage].tone}>{STAGES[p.stage].label}</span>
                  </td>
                  <td>
                    {p.stage === "discharged" ? (
                      <button type="button" className="btn small" onClick={(e) => {
                        e.stopPropagation();
                        if (!window.confirm(`Перенести историю № ${p.number} (${p.surname}) в архив?`)) return;
                        api.archive(p.caseId).then(() => api.department().then(setData), (err: Error) => window.alert(err.message));
                      }}>
                        В архив
                      </button>
                    ) : p.diaryToday ? (
                      <span className="dep-done">
                        <span className="dep-check" aria-hidden="true">✓</span>Написан
                      </span>
                    ) : (
                      <Link to={`/case/${p.caseId}/diary`} className="btn primary small" onClick={(e) => e.stopPropagation()}>
                        Написать
                      </Link>
                    )}
                  </td>
                  <td style={{ paddingRight: 24 }}>
                    {p.unprinted > 0 ? (
                      <span className="pill tone-amber">
                        {p.unprinted} {plural(p.unprinted, "запись", "записи", "записей")}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && rows.length === 0 && (
            <p className="dep-empty muted">{query ? "Никого не нашли по этому запросу." : "В этом списке никого нет."}</p>
          )}
          {!data && <p className="dep-empty muted">Загружаем…</p>}
        </div>
      </section>
    </main>
  );
}
