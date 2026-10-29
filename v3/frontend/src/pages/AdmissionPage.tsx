import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AdmissionIn, api, Dictionaries, PatientMatch } from "../api";
import { fullDate, plural, todayIso } from "../format";
import "./admission.css";

type Eye = "OD" | "OS" | "OU" | "";

const nowHm = () => new Date().toTimeString().slice(0, 5);

function age(dob: string | null): number | null {
  if (!dob) return null;
  const [y, m, d] = dob.split("-").map(Number);
  const t = new Date();
  return t.getFullYear() - y - (t.getMonth() + 1 < m || (t.getMonth() + 1 === m && t.getDate() < d) ? 1 : 0);
}

/** "Незрелая катаракта" + OD -> "Незрелая катаракта OD" (unless the eye is already written). */
function withEye(text: string, eye: Eye): string {
  const t = text.trim();
  if (!t || !eye || /\b(OD|OS|OU)$/.test(t)) return t;
  return `${t} ${eye}`;
}

export function AdmissionPage() {
  const navigate = useNavigate();
  const [dict, setDict] = useState<Dictionaries | null>(null);
  const [form, setForm] = useState<AdmissionIn>({
    patientId: null, surname: "", name: "", patronymic: "", dob: null, city: "", street: "", house: "", medCard: "",
    admittedDate: todayIso(), admittedTime: nowHm(), dxAdmission: "", dxClinical: "", dxComorbid: "", channel: "", residence: "",
  });
  const [eye, setEye] = useState<Eye>("");
  const [matches, setMatches] = useState<PatientMatch[]>([]);
  const [chosen, setChosen] = useState<PatientMatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.dictionaries().then(setDict, (e: Error) => setError(e.message));
  }, []);

  // Search the database while the surname is typed: re-admissions (the second eye) are common.
  useEffect(() => {
    if (chosen) return;
    const q = `${form.surname} ${form.name}`.trim();
    if (form.surname.trim().length < 2) {
      setMatches([]);
      return;
    }
    const t = window.setTimeout(() => api.searchPatients(q).then(setMatches, () => setMatches([])), 250);
    return () => window.clearTimeout(t);
  }, [form.surname, form.name, chosen]);

  const set = (k: keyof AdmissionIn, v: string | null) => setForm((f) => ({ ...f, [k]: v }));

  const choose = (m: PatientMatch) => {
    setChosen(m);
    setMatches([]);
    setForm((f) => ({ ...f, patientId: m.id, surname: m.surname, name: m.name, patronymic: m.patronymic, dob: m.dob,
      city: m.city, street: m.street, house: m.house, residence: m.residence }));
  };
  const unchoose = () => {
    setChosen(null);
    setForm((f) => ({ ...f, patientId: null }));
  };

  const submit = async () => {
    setError(null);
    if (!form.patientId && !form.surname.trim()) return setError("Укажите фамилию");
    if (!form.dxAdmission.trim()) return setError("Укажите диагноз при поступлении");
    setSaving(true);
    try {
      const res = await api.admit({ ...form, dxAdmission: withEye(form.dxAdmission, eye) });
      navigate(`/case/${res.caseId}/exam`);
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  };

  const years = age(form.dob);
  const locked = Boolean(chosen);

  return (
    <div className="ad-overlay">
      <section role="dialog" aria-modal="true" aria-labelledby="ad-title" className="ad-dialog">
        <div className="ad-head">
          <span className="ad-icon" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><circle cx="10" cy="8" r="4" /><path d="M2 21c0-4 3.6-7 8-7" /><path d="M18 14v7M14.5 17.5h7" /></svg>
          </span>
          <div style={{ flex: 1 }}>
            <h1 id="ad-title">Новое поступление</h1>
            <div className="muted">Пациент и данные госпитализации на одном экране. Поля со звёздочкой обязательны.</div>
          </div>
          <Link to="/" className="round-btn" aria-label="Закрыть">
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </Link>
        </div>

        {error && <div className="ad-error" role="alert">{error}</div>}

        <div className="ad-body">
          <div className="ad-col">
            <h2><span className="pr-num">1</span>Пациент</h2>
            {chosen && (
              <div className="ad-chosen">
                <span style={{ flex: 1 }}>
                  <b>Повторное поступление.</b> Данные взяты из базы
                  {chosen.lastCase && ` (история № ${chosen.lastCase.number})`}. Адрес можно поправить.
                </span>
                <button type="button" className="btn white small" onClick={unchoose}>Другой пациент</button>
              </div>
            )}
            <label className="lbl">Фамилия *
              <input className="in" value={form.surname} onChange={(e) => set("surname", e.target.value)} readOnly={locked} autoFocus />
            </label>
            {matches.length > 0 && (
              <div className="ad-matches" role="status">
                <b>Уже есть в базе — возможно, повторное поступление</b>
                {matches.map((m) => (
                  <div key={m.id} className="ad-match">
                    <span className="avatar tone-green" aria-hidden="true">{(m.surname[0] ?? "") + (m.name[0] ?? "")}</span>
                    <span className="ad-match-text">
                      <b>{[m.surname, m.name, m.patronymic].filter(Boolean).join(" ")}</b>
                      <span className="muted">
                        {[m.dob && fullDate(m.dob), m.city,
                          m.lastCase && `история № ${m.lastCase.number}${m.lastCase.diagnosis ? `, ${m.lastCase.diagnosis}` : ""}${m.lastCase.status === "active" ? " — сейчас в отделении" : ""}`]
                          .filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    <button type="button" className="btn primary small" onClick={() => choose(m)}>Это он(а)</button>
                  </div>
                ))}
                <span className="ad-note">Выбор подставит паспортные данные и адрес. Старая история останется в архиве, будет создана новая.</span>
              </div>
            )}
            <div className="ad-grid">
              <label className="lbl">Имя <input className="in" value={form.name} onChange={(e) => set("name", e.target.value)} readOnly={locked} /></label>
              <label className="lbl">Отчество <input className="in" value={form.patronymic} onChange={(e) => set("patronymic", e.target.value)} readOnly={locked} /></label>
              <label className="lbl">Дата рождения
                <span className="ad-row">
                  <input className="in" type="date" value={form.dob ?? ""} onChange={(e) => set("dob", e.target.value || null)} readOnly={locked} />
                  {years != null && <span className="pill tone-tint">{years} {plural(years, "год", "года", "лет")}</span>}
                </span>
              </label>
              <label className="lbl">Населённый пункт
                <input className="in" list="ad-cities" value={form.city} onChange={(e) => set("city", e.target.value)} />
              </label>
              <label className="lbl">Улица
                <input className="in" list="ad-streets" value={form.street} onChange={(e) => set("street", e.target.value)} />
              </label>
              <label className="lbl">Дом, кв. <input className="in" value={form.house} onChange={(e) => set("house", e.target.value)} /></label>
              <label className="lbl">Для отчёта
                <select className="in" value={form.residence} onChange={(e) => set("residence", e.target.value)}>
                  {(dict?.residence ?? [""]).map((r) => <option key={r} value={r}>{r || "местный житель"}</option>)}
                </select>
              </label>
            </div>
          </div>

          <div className="ad-col ad-col-2">
            <h2><span className="pr-num">2</span>Госпитализация</h2>
            <div className="ad-grid">
              <div className="lbl">№ истории болезни
                <span className="ad-number">{dict?.nextNumber ?? "…"} <span className="pill sm tone-neutral">следующий по порядку</span></span>
              </div>
              <label className="lbl">№ мед. карты
                <input className="in white" inputMode="numeric" maxLength={6} placeholder="до 6 цифр" value={form.medCard}
                  onChange={(e) => set("medCard", e.target.value.replace(/\D/g, ""))} />
              </label>
              <label className="lbl">Дата поступления *
                <span className="ad-row">
                  <input className="in white" type="date" value={form.admittedDate} onChange={(e) => set("admittedDate", e.target.value)} />
                  <button type="button" className="chip" onClick={() => set("admittedDate", todayIso())}>Сегодня</button>
                </span>
              </label>
              <label className="lbl">Время *
                <span className="ad-row">
                  <input className="in white" value={form.admittedTime} placeholder="ЧЧ:ММ" onChange={(e) => set("admittedTime", e.target.value)} />
                  <button type="button" className="chip" onClick={() => set("admittedTime", nowHm())}>Сейчас</button>
                </span>
              </label>
            </div>
            <label className="lbl">Как поступил
              <select className="in white" value={form.channel} onChange={(e) => set("channel", e.target.value)}>
                <option value="">не указано</option>
                {dict?.channels.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <span className="ad-note">Для отчёта отделения: экстренно или планово, кем направлен.</span>
            </label>
            <div className="lbl">Диагноз при поступлении *
              <span className="ad-row">
                <span className="seg ad-eye" role="radiogroup" aria-label="Глаз">
                  {(["OD", "OS", "OU"] as Eye[]).map((e) => (
                    <button key={e} type="button" role="radio" aria-checked={eye === e} className={eye === e ? "on" : ""} onClick={() => setEye(eye === e ? "" : e)}>{e}</button>
                  ))}
                </span>
                <input className="in white" list="ad-dx" value={form.dxAdmission} onChange={(e) => set("dxAdmission", e.target.value)}
                  placeholder="начните вводить — подскажем из справочника" />
              </span>
              {form.dxAdmission && <span className="ad-note">Запишется: «{withEye(form.dxAdmission, eye)}»</span>}
            </div>
            <label className="lbl">Клинический диагноз
              <input className="in white" list="ad-dx" value={form.dxClinical} onChange={(e) => set("dxClinical", e.target.value)} placeholder="можно заполнить после осмотра" />
            </label>
            <label className="lbl">Сопутствующие
              <input className="in white" list="ad-comorbid" value={form.dxComorbid} onChange={(e) => set("dxComorbid", e.target.value)} />
            </label>
          </div>
        </div>

        <datalist id="ad-cities">{dict?.cities.map((c) => <option key={c} value={c} />)}</datalist>
        <datalist id="ad-streets">{dict?.streets.map((s) => <option key={s} value={s} />)}</datalist>
        <datalist id="ad-dx">{dict?.ophthalmic.map((d) => <option key={d} value={d} />)}</datalist>
        <datalist id="ad-comorbid">{dict?.comorbid.map((d) => <option key={d} value={d} />)}</datalist>

        <div className="ad-foot">
          <span className="muted" style={{ flex: 1, minWidth: 260 }}>После создания сразу откроется первичный осмотр по шаблону.</span>
          <Link to="/" className="btn">Отмена</Link>
          <button type="button" className="btn primary" onClick={submit} disabled={saving}>{saving ? "Создаём…" : "Создать историю"}</button>
        </div>
      </section>
    </div>
  );
}
