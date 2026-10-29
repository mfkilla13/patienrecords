import { useEffect, useState } from "react";
import { api, BackupList } from "../api";
import { fullDate } from "../format";

const when = (iso: string) => `${fullDate(iso)} ${iso.slice(11, 16)}`;
const size = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1).replace(".", ",")} МБ` : `${Math.max(1, Math.round(n / 1024))} КБ`);

function ageHours(iso: string | null): number | null {
  return iso ? (Date.now() - new Date(iso).getTime()) / 3600000 : null;
}

/** «Резервные копии» in the settings: state, a copy now, the second folder, the list with restore. */
export function BackupsSection() {
  const [list, setList] = useState<BackupList | null>(null);
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const load = () => api.backups().then((l) => { setList(l); setExtra(l.extraDir); return l; }, (e: Error) => setStatus({ kind: "error", text: e.message }));
  useEffect(() => { load(); }, []);

  const run = async (fn: () => Promise<string>) => {
    setBusy(true);
    setStatus(null);
    try {
      const text = await fn();
      await load();
      setStatus({ kind: "ok", text });
    } catch (e) {
      setStatus({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const makeNow = () => run(async () => {
    const r = await api.makeBackup();
    return r.extraError ? `Копия сделана на этом компьютере. ${r.extraError}` : "Копия сделана и проверена.";
  });

  const restore = (name: string, at: string) => {
    if (!window.confirm(`Вернуть базу к состоянию на ${when(at)}?\n\nВсё, что записано после этого времени, пропадёт из программы. Текущее состояние сначала сохранится отдельной копией — к нему можно будет вернуться.`)) return;
    if (!window.confirm("Точно восстановить? Это заменит данные во всей программе.")) return;
    run(async () => {
      const r = await api.restoreBackup(name);
      return `Восстановлено на ${when(at)}. Состояние до восстановления сохранено: ${r.savedAs}.`;
    });
  };

  const age = ageHours(list?.last ?? null);
  const fresh = age != null && age < 26;

  return (
    <section className="card st-card" aria-label="Резервные копии">
      <h2>Резервные копии</h2>
      {!list ? <p className="muted">Загружаем…</p> : (
        <>
          <div className="bk-state">
            <div className={"bk-tile " + (fresh ? "ok" : "warn")}>
              <span>Последняя копия</span>
              <b>{list.last ? when(list.last) : "ещё не было"}</b>
            </div>
            <div className="bk-tile">
              <span>Копий на этом компьютере</span>
              <b>{list.items.length}</b>
            </div>
            <div className={"bk-tile " + (list.extraDir ? (list.extraError ? "warn" : "ok") : "warn")}>
              <span>Вторая копия (флешка, другой диск)</span>
              <b>{list.extraDir ? (list.extraError ? "не удалась" : "включена") : "не настроена"}</b>
            </div>
          </div>
          <span className="st-help">
            Копия делается сама: при запуске программы и раз в сутки, пока она открыта. Хранятся последние {list.keep.daily} автоматических
            копий и по одной за каждый из {list.keep.months} последних месяцев; копии «вручную» не удаляются.
          </span>

          <div className="bk-row">
            <button type="button" className="btn primary" disabled={busy} onClick={makeNow}>{busy ? "Подождите…" : "Сделать копию сейчас"}</button>
            <button type="button" className="btn" onClick={() => api.openBackupFolder().catch((e: Error) => setStatus({ kind: "error", text: e.message }))}>Открыть папку с копиями</button>
            <span className="bk-path muted">{list.folder}</span>
          </div>

          <label className="lbl">Папка для второй копии
            <span className="bk-row">
              <input className="in" value={extra} placeholder="например: E:\MedQT-копии (флешка) — пусто, если не нужно" onChange={(e) => setExtra(e.target.value)} />
              <button type="button" className="btn" disabled={busy || extra === list.extraDir}
                onClick={() => run(async () => {
                  const r = await api.setBackupExtraDir(extra);
                  return r.extraDir ? `Каждая копия будет сохраняться ещё и в «${r.extraDir}».` : "Вторая копия выключена.";
                })}>Сохранить папку</button>
            </span>
            <span className="st-help">
              Если диск ноутбука выйдет из строя, копии на нём пропадут вместе с базой. Вставьте флешку и укажите папку на ней — копия будет дублироваться туда.
              {list.extraError && <><br /><b style={{ color: "var(--amber-text)" }}>{list.extraError}</b></>}
            </span>
          </label>

          {status && <span className={"st-status " + status.kind} role="status">{status.text}</span>}

          {list.items.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table className="bk-table">
                <thead><tr><th>Когда</th><th>Как сделана</th><th>Размер</th><th></th></tr></thead>
                <tbody>
                  {list.items.map((b) => (
                    <tr key={b.name}>
                      <td><b>{when(b.at)}</b></td>
                      <td className="muted">{b.kindLabel}</td>
                      <td className="muted">{size(b.size)}</td>
                      <td>
                        <button type="button" className="link-btn" disabled={busy} onClick={() => restore(b.name, b.at)}>восстановить</button>
                        {b.kind === "manual" && (
                          <button type="button" className="link-btn" disabled={busy}
                            onClick={() => window.confirm(`Удалить копию от ${when(b.at)}?`) && run(async () => { await api.deleteBackup(b.name); return "Копия удалена."; })}>
                            удалить
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
