import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, DictName, Settings } from "../api";
import { BackupsSection } from "./BackupsSection";
import { DictionarySection } from "./DictionarySection";
import { applyTheme } from "../theme";
import "./settings.css";

const DICTIONARIES: [DictName, string][] = [
  ["ophthalmic", "Диагнозы — глаза"],
  ["comorbid", "Сопутствующие диагнозы"],
  ["treatment", "Обоснование лечения"],
  ["examinations", "Обследования"],
  ["prescriptions", "Шаблоны назначений"],
  ["addresses", "Адреса"],
];
const SETTINGS = [["print", "Учреждение, подпись, печать"], ["backups", "Резервные копии"]] as const;

export function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const s = params.get("s") ?? "";
  const dict = DICTIONARIES.find(([key]) => key === s)?.[0] ?? null;
  const section = dict ?? (s === "backups" ? "backups" : "print");
  const [dictDirty, setDictDirty] = useState(false);
  const onDictDirty = useCallback((d: boolean) => setDictDirty(d), []);
  const open = (key: string) => {
    if (key === section) return;
    if (dictDirty && !window.confirm("В списке есть несохранённые изменения. Уйти без сохранения?")) return;
    setDictDirty(false);
    setParams(key === "print" ? {} : { s: key }, { replace: true });
  };
  const [form, setForm] = useState<Settings | null>(null);
  const [saved, setSaved] = useState<Settings | null>(null);
  const [printers, setPrinters] = useState<{ list: string[]; windowsDefault: string | null }>({ list: [], windowsDefault: null });
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.settings().then((s) => {
      setForm(s);
      setSaved(s);
    }, (e: Error) => setStatus({ kind: "error", text: e.message }));
    api.printers().then((p) => setPrinters({ list: p.printers, windowsDefault: p.default }), () => undefined);
  }, []);

  const set = (k: keyof Settings, v: string) => {
    setForm((f) => (f ? { ...f, [k]: v } : f));
    setStatus(null);
  };
  const dirty = form && saved && JSON.stringify(form) !== JSON.stringify(saved);

  // The theme switches at once and is saved on its own, apart from the other fields' «Сохранить».
  const chooseTheme = async (theme: string) => {
    if (!saved) return;
    applyTheme(theme);
    try {
      const s = await api.saveSettings({ ...saved, theme });
      setSaved(s);
      setForm((f) => (f ? { ...f, theme: s.theme } : f));
    } catch (e) {
      applyTheme(saved.theme);
      setStatus({ kind: "error", text: (e as Error).message });
    }
  };

  const save = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const s = await api.saveSettings(form);
      setForm(s);
      setSaved(s);
      setStatus({ kind: "ok", text: "Сохранено. Подпись появится на всех следующих печатях." });
    } catch (e) {
      setStatus({ kind: "error", text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="page st">
      <nav className="st-nav" aria-label="Справочники и настройки">
        <h1>Справочники</h1>
        {[...DICTIONARIES, null, ...SETTINGS].map((item) => item === null ? (
          <div key="group" className="st-nav-group">Настройки</div>
        ) : (
          <button key={item[0]} type="button" className={"st-nav-item st-nav-btn" + (section === item[0] ? " on" : "")}
            aria-current={section === item[0] ? "page" : undefined} onClick={() => open(item[0])}>
            {item[1]}
          </button>
        ))}
      </nav>

      {dict ? <DictionarySection name={dict} onDirty={onDictDirty} /> : section === "backups" ? <BackupsSection /> : (
      <section className="card st-card" aria-label="Учреждение, подпись, печать">
        <h2>Учреждение, подпись, печать</h2>
        {!form ? (
          <p className="muted">Загружаем…</p>
        ) : (
          <>
            <div className="st-grid">
              <label className="lbl">ФИО для подписи в листах
                <input className="in" value={form.doctor_signature} onChange={(e) => set("doctor_signature", e.target.value)}
                  placeholder="например: Петрова Е. В." maxLength={80} />
                <span className="st-help">Ставится перед линией подписи в дневниках, протоколах и новых осмотрах. Пусто — будет «Подпись ____».</span>
              </label>
              <div className="st-sample" aria-label="Как будет на листе">
                <span className="muted" style={{ fontSize: 12 }}>На листе:</span>
                <span className="st-sign">{form.doctor_signature ? `${form.doctor_signature} __________________` : "Подпись __________________"}</span>
                <span className="st-sign">Хирург {form.doctor_signature || ""} __________________</span>
              </div>

              <label className="lbl">Шапка учреждения
                <textarea className="ta" rows={4} value={form.org_header} onChange={(e) => set("org_header", e.target.value)} maxLength={400} />
                <span className="st-help">Каждая строка — отдельной строкой в шапке выписки. По умолчанию — как было в 2.9.</span>
              </label>
              <div className="st-sample st-header" aria-label="Шапка выписки">
                <span className="muted" style={{ fontSize: 12 }}>В выписке:</span>
                {form.org_header.split("\n").map((line, i) => <span key={i}>{line || " "}</span>)}
              </div>

              <label className="lbl">Отделение
                <input className="in" value={form.department} onChange={(e) => set("department", e.target.value)} maxLength={120} />
              </label>
              <span />

              <label className="lbl">Принтер по умолчанию
                <select className="in" value={form.default_printer} onChange={(e) => set("default_printer", e.target.value)}>
                  <option value="">как в Windows{printers.windowsDefault && !form.default_printer ? ` (${printers.windowsDefault})` : ""}</option>
                  {printers.list.map((p) => <option key={p} value={p}>{p}</option>)}
                  {form.default_printer && !printers.list.includes(form.default_printer) && (
                    <option value={form.default_printer}>{form.default_printer} — сейчас не найден</option>
                  )}
                </select>
                <span className="st-help">Будет выбран в окне печати. Если его не найдётся, программа возьмёт принтер Windows.</span>
              </label>
              <span />

              <div className="lbl">Тема
                <span className="seg st-theme" role="radiogroup" aria-label="Тема">
                  {([["auto", "Как в Windows"], ["light", "Светлая"], ["dark", "Тёмная"]] as const).map(([v, label]) => (
                    <button key={v} type="button" role="radio" aria-checked={form.theme === v} className={form.theme === v ? "on" : ""}
                      onClick={() => chooseTheme(v)}>{label}</button>
                  ))}
                </span>
                <span className="st-help">Меняется сразу. Листы и выписка в предпросмотре остаются белыми — это бумага.</span>
              </div>
              <span />

              <label className="lbl">Коек в отделении
                <input className="in" inputMode="numeric" maxLength={4} value={form.beds} style={{ maxWidth: 140 }}
                  onChange={(e) => set("beds", e.target.value.replace(/\D/g, ""))} />
                <span className="st-help">Для отчёта отделения: оборот койки, число дней работы койки.</span>
              </label>
              <label className="lbl">План койко-дней на год
                <input className="in" inputMode="numeric" maxLength={6} value={form.bed_days_plan} style={{ maxWidth: 160 }}
                  placeholder="не задан" onChange={(e) => set("bed_days_plan", e.target.value.replace(/\D/g, ""))} />
                <span className="st-help">Для «процента выполнения плана койко-дней». Пусто — строка не считается.</span>
              </label>
            </div>

            <div className="st-foot">
              {status && <span className={"st-status " + status.kind} role="status">{status.text}</span>}
              <div style={{ flex: 1 }} />
              <button type="button" className="btn" disabled={!dirty || saving} onClick={() => saved && setForm(saved)}>Отменить</button>
              <button type="button" className="btn primary" disabled={!dirty || saving} onClick={save}>
                {saving ? "Сохраняем…" : "Сохранить"}
              </button>
            </div>
          </>
        )}
      </section>
      )}
    </main>
  );
}
