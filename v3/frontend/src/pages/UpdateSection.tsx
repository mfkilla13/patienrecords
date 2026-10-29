import { useEffect, useRef, useState } from "react";
import { api, UpdateStatus } from "../api";
import { fullDate } from "../format";

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(0)} МБ`;
const busyPhase = (s: UpdateStatus | null) => !!s?.progress && !["ready", "error"].includes(s.progress.phase);

/** «Обновление программы»: check GitHub, install the new version next to this one, go back to the previous one. */
export function UpdateSection() {
  const [st, setSt] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => { api.update().then(setSt, (e: Error) => setError(e.message)); }, []);
  // While installing, follow the progress.
  useEffect(() => {
    if (!busyPhase(st)) return;
    const t = window.setTimeout(() => api.update().then(setSt, () => undefined), 700);
    return () => window.clearTimeout(t);
  }, [st]);

  const act = async (fn: () => Promise<UpdateStatus>) => {
    setError(null);
    try {
      setSt(await fn());
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const check = async () => {
    setChecking(true);
    await act(api.updateCheck);
    setChecking(false);
  };
  const install = () => {
    if (!window.confirm(`Скачать и установить версию ${st?.latest?.version}?\n\nПеред установкой программа сохранит копию базы. Прежняя версия останется — к ней можно вернуться.`)) return;
    act(api.updateDownload);
  };
  const fromFile = (f: File | undefined) => {
    if (file.current) file.current.value = "";
    if (!f) return;
    if (!window.confirm(`Установить MedQT из файла «${f.name}»?`)) return;
    act(() => api.updateFile(f));
  };
  const rollback = () => {
    const r = st?.rollback;
    if (!r) return;
    const text = r.needsDb
      ? `Вернуться к версии ${r.version}?\n\nОна не откроет базу в нынешнем виде, поэтому база вернётся к копии, сделанной перед обновлением${r.backupAt ? ` (${fullDate(r.backupAt)} ${r.backupAt.slice(11, 16)})` : ""}. Всё, что записано после обновления, пропадёт из программы (нынешнее состояние сохранится отдельной копией).`
      : `Вернуться к версии ${r.version}? Данные останутся как есть.`;
    if (!window.confirm(text)) return;
    act(() => api.updateRollback(r.needsDb));
  };
  const restart = async () => {
    setError(null);
    try {
      await api.updateRestart();
      setRestarting(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const p = st?.progress;
  const busy = busyPhase(st);
  return (
    <section className="card st-card" aria-label="Обновление программы">
      <h2>Обновление программы</h2>
      {!st ? <p className="muted">{error ?? "Загружаем…"}</p> : (
        <>
          <div className="bk-state">
            <div className="bk-tile">
              <span>Установлена версия</span>
              <b>{st.current}</b>
            </div>
            <div className={"bk-tile " + (st.available ? "warn" : st.checkedAt && !st.error ? "ok" : "")}>
              <span>{st.checkedAt ? `Проверено ${fullDate(st.checkedAt)} ${st.checkedAt.slice(11, 16)}` : "Ещё не проверялось"}</span>
              <b>{st.available ? `Доступна ${st.latest!.version}` : st.error ? "Нет связи" : st.checkedAt ? "Это последняя версия" : "—"}</b>
            </div>
          </div>
          <span className="st-help">
            Программа сама заглядывает на GitHub после запуска, если есть интернет (можно раздать с телефона). Без вашего нажатия ничего не ставится.
          </span>
          {st.error && <span className="st-status error">{st.error}</span>}

          {st.available && st.latest && (
            <div className="up-new">
              <b>Версия {st.latest.version}{st.latest.publishedAt && <span className="muted"> · {fullDate(st.latest.publishedAt)} · {mb(st.latest.size)}</span>}</b>
              {st.latest.notes && <div className="up-notes">{st.latest.notes}</div>}
            </div>
          )}

          {p && (
            <div className={"up-progress " + p.phase} role="status">
              <span>{p.text}</span>
              {p.phase === "download" && p.total > 0 && (
                <span className="dep-meter"><i style={{ width: `${Math.min(100, (p.done / p.total) * 100)}%` }} /></span>
              )}
            </div>
          )}

          <div className="bk-row">
            {p?.phase === "ready" ? (
              <button type="button" className="btn primary" disabled={restarting} onClick={restart}>
                {restarting ? "Перезапускаем…" : "Перезапустить программу"}
              </button>
            ) : st.available ? (
              <button type="button" className="btn primary" disabled={busy || !st.installable} onClick={install}>
                {busy ? "Устанавливаем…" : "Скачать и установить"}
              </button>
            ) : null}
            <button type="button" className="btn" disabled={checking || busy} onClick={check}>{checking ? "Проверяем…" : "Проверить сейчас"}</button>
            <button type="button" className="btn" disabled={busy || !st.installable} onClick={() => file.current?.click()}>Установить из файла…</button>
            <input ref={file} type="file" accept=".zip" hidden onChange={(e) => fromFile(e.target.files?.[0])} />
          </div>
          {!st.installable && (
            <span className="st-help">Это не установленная программа (запуск из исходников) — здесь можно только проверить, установка работает в папке MedQT.</span>
          )}
          {error && <span className="st-status error">{error}</span>}

          {st.rollback && p?.phase !== "ready" && (
            <div className="up-back">
              <span>Прежняя версия {st.rollback.version} сохранена.</span>
              <button type="button" className="btn small" disabled={busy} onClick={rollback}>Вернуться к версии {st.rollback.version}</button>
            </div>
          )}
          {restarting && <span className="st-help">Окно закроется и откроется уже в новой версии. Если не открылось за полминуты — запустите MedQT с рабочего стола.</span>}
        </>
      )}
    </section>
  );
}
