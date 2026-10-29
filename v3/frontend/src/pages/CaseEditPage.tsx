import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AdmissionIn, api, Dictionaries } from "../api";
import { dobProblem, plural, todayIso } from "../format";
import "./diary.css";
import "./record.css";

interface EditData { caseId: string; number: string; status: string; dischargedAt: string | null; otherCases: number; form: AdmissionIn }

/** Fixing what was typed at admission: the patient's name, birth date, address and the stay's own data. */
export function CaseEditPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<EditData | null>(null);
  const [form, setForm] = useState<AdmissionIn | null>(null);
  const [dict, setDict] = useState<Dictionaries | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.caseEdit(caseId).then((d) => { setData(d); setForm(d.form); }, (e: Error) => setError(e.message));
    api.dictionaries().then(setDict, () => undefined);
  }, [caseId]);

  const set = (k: keyof AdmissionIn, v: string | null) => {
    setForm((f) => (f ? { ...f, [k]: v } : f));
    setError(null);
  };
  const dirty = !!form && !!data && JSON.stringify(form) !== JSON.stringify(data.form);

  const save = async () => {
    if (!form) return;
    const dob = dobProblem(form.dob);
    if (dob?.block) return setError(dob.text);
    if (dob && !window.confirm(`${dob.text}. Всё верно, сохранить так?`)) return;
    setSaving(true);
    try {
      await api.saveCaseEdit(caseId, form);
      navigate(`/case/${caseId}`);
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  };

  const input = (k: keyof AdmissionIn, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <input className="in" value={(form?.[k] as string) ?? ""} onChange={(e) => set(k, e.target.value)} {...extra} />
  );
  const fio = form ? [form.surname, form.name, form.patronymic].filter(Boolean).join(" ") : "…";

  return (
    <main className="page dy">
      <div className="dy-top">
        <Link to={`/case/${caseId}`} className="round-btn white" aria-label="Назад к истории">
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <div style={{ flex: "1 1 300px" }}>
          <h1>Данные пациента и поступления</h1>
          <div className="muted">{fio}{data && ` · история № ${data.number}`}</div>
        </div>
        <Link to={`/case/${caseId}`} className="btn">Отмена</Link>
        <button type="button" className="btn primary" onClick={save} disabled={!dirty || saving}>{saving ? "Сохраняем…" : "Сохранить"}</button>
      </div>

      {error && <div className="dy-banner dy-error" role="alert">{error}</div>}
      {data && data.otherCases > 0 && (
        <div className="dy-banner">
          У пациента ещё {data.otherCases} {plural(data.otherCases, "история", "истории", "историй")}. Ф. И. О., дата рождения и адрес
          изменятся и в них — это один и тот же человек. Данные поступления меняются только в этой истории.
        </div>
      )}

      {form && (
        <div className="dy-body">
          <section className="card dy-card dy-form" aria-label="Пациент">
            <h2>Пациент</h2>
            <div className="ce-grid">
              <label className="lbl">Фамилия *{input("surname", { maxLength: 80 })}</label>
              <label className="lbl">Имя{input("name", { maxLength: 80 })}</label>
              <label className="lbl">Отчество{input("patronymic", { maxLength: 80 })}</label>
              <label className="lbl">Дата рождения
                <input className="in" type="date" value={form.dob ?? ""} max={todayIso()} onChange={(e) => set("dob", e.target.value || null)} />
                {dobProblem(form.dob) && <span className="pill tone-amber" role="status" style={{ alignSelf: "flex-start" }}>{dobProblem(form.dob)!.text}</span>}
              </label>
              <label className="lbl">Населённый пункт{input("city", { list: "ce-cities", maxLength: 120 })}</label>
              <label className="lbl">Улица{input("street", { list: "ce-streets", maxLength: 160 })}</label>
              <label className="lbl">Дом, кв.{input("house", { maxLength: 60 })}</label>
              <label className="lbl">Для отчёта
                <select className="in" value={form.residence} onChange={(e) => set("residence", e.target.value)}>
                  {(dict?.residence ?? [""]).map((r) => <option key={r} value={r}>{r || "местный житель"}</option>)}
                </select>
              </label>
            </div>

            <h2 style={{ marginTop: 10 }}>Поступление</h2>
            <div className="ce-grid">
              <label className="lbl">№ мед. карты
                <input className="in" inputMode="numeric" maxLength={6} value={form.medCard} onChange={(e) => set("medCard", e.target.value.replace(/\D/g, ""))} />
              </label>
              <label className="lbl">Дата поступления *
                <input className="in" type="date" value={form.admittedDate} max={todayIso()} onChange={(e) => set("admittedDate", e.target.value)} />
              </label>
              <label className="lbl">Время{input("admittedTime", { placeholder: "ЧЧ:ММ", maxLength: 5 })}</label>
              <label className="lbl">Как поступил
                <select className="in" value={form.channel} onChange={(e) => set("channel", e.target.value)}>
                  <option value="">не указано</option>
                  {dict?.channels.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            </div>
            <label className="lbl">Диагноз при поступлении *{input("dxAdmission", { list: "ce-dx", maxLength: 500 })}</label>
            <label className="lbl">Клинический диагноз{input("dxClinical", { list: "ce-dx", maxLength: 500 })}</label>
            <label className="lbl">Сопутствующие{input("dxComorbid", { list: "ce-comorbid", maxLength: 500 })}</label>
            <span className="st-help">
              Заключительный диагноз, исход и дата выписки меняются в выписке. Новые данные появятся в шапке следующих напечатанных листов.
            </span>
          </section>
        </div>
      )}

      <datalist id="ce-cities">{dict?.cities.map((c) => <option key={c} value={c} />)}</datalist>
      <datalist id="ce-streets">{dict?.streets.map((s) => <option key={s} value={s} />)}</datalist>
      <datalist id="ce-dx">{dict?.ophthalmic.map((d) => <option key={d} value={d} />)}</datalist>
      <datalist id="ce-comorbid">{dict?.comorbid.map((d) => <option key={d} value={d} />)}</datalist>
    </main>
  );
}
