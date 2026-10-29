import { useEffect, useMemo, useRef, useState } from "react";
import { api, DictInfo, DictName, DictValue } from "../api";
import { plural } from "../format";

type Groups = Record<string, string[]>;
const ONE = "";        // a plain list is edited as a single group with this key

const asGroups = (v: DictValue): Groups => (Array.isArray(v) ? { [ONE]: v } : v);
const fold = (s: string) => s.toLocaleLowerCase("ru").replace(/ё/g, "е");

/** One dictionary in the settings: find, add, rename, reorder, remove; saved as a whole. */
export function DictionarySection({ name, onDirty }: { name: DictName; onDirty: (dirty: boolean) => void }) {
  const [info, setInfo] = useState<DictInfo | null>(null);
  const [draft, setDraft] = useState<Groups>({});
  const [group, setGroup] = useState(ONE);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<{ index: number; text: string } | null>(null);
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const findRef = useRef<HTMLInputElement>(null);

  const take = (d: DictInfo) => {
    setInfo(d);
    setDraft(asGroups(d.value));
    setGroup((g) => (d.groups && !(g in d.groups) ? Object.keys(d.groups)[0] : d.groups ? g : ONE));
  };

  useEffect(() => {
    setInfo(null);
    setQuery("");
    setEditing(null);
    setStatus(null);
    setGroup(ONE);
    api.dictionary(name).then(take, (e: Error) => setStatus({ kind: "error", text: e.message }));
  }, [name]);

  const dirty = !!info && JSON.stringify(draft) !== JSON.stringify(asGroups(info.value));
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  const items = draft[group] ?? [];
  const q = fold(query.trim());
  const shown = useMemo(
    () => items.map((text, index) => ({ text, index })).filter((x) => !q || fold(x.text).includes(q)),
    [items, q],
  );
  const exact = !!q && items.some((x) => fold(x) === q);

  const change = (next: string[]) => {
    setDraft((d) => ({ ...d, [group]: next }));
    setStatus(null);
  };
  const add = () => {
    const text = query.trim().replace(/\s+/g, " ");
    if (!text || exact) return;
    change([...items, text]);
    setQuery("");
    findRef.current?.focus();
  };
  const remove = (i: number) => change(items.filter((_, k) => k !== i));
  const move = (i: number, by: number) => {
    const j = i + by;
    if (j < 0 || j >= items.length) return;
    const next = [...items];
    [next[i], next[j]] = [next[j], next[i]];
    change(next);
  };
  const rename = () => {
    if (!editing) return;
    const text = editing.text.trim().replace(/\s+/g, " ");
    if (text && !items.some((x, k) => k !== editing.index && fold(x) === fold(text))) {
      change(items.map((x, k) => (k === editing.index ? text : x)));
    }
    setEditing(null);
  };
  const sortAbc = () => change([...items].sort((a, b) => a.localeCompare(b, "ru")));

  const save = async () => {
    if (!info) return;
    setBusy(true);
    try {
      const value: DictValue = info.groups ? draft : draft[ONE] ?? [];
      take(await api.saveDictionary(name, value));
      setStatus({ kind: "ok", text: "Сохранено. Новые подсказки появятся сразу." });
    } catch (e) {
      setStatus({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!window.confirm(`Вернуть «${info?.title}» к списку, который был при установке программы? Всё, что вы добавили или изменили в нём, пропадёт.`)) return;
    setBusy(true);
    try {
      take(await api.resetDictionary(name));
      setStatus({ kind: "ok", text: "Список возвращён к исходному." });
    } catch (e) {
      setStatus({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  if (!info) {
    return <section className="card st-card"><p className={status ? "st-status error" : "muted"}>{status?.text ?? "Загружаем…"}</p></section>;
  }

  return (
    <section className="card st-card" aria-label={info.title}>
      <div>
        <h2>{info.title}</h2>
        <span className="st-help">{info.hint}</span>
      </div>

      {info.groups && (
        <div className="dc-groups" role="tablist" aria-label="Разделы">
          {Object.entries(info.groups).map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={group === key}
              className={"chip" + (group === key ? " on" : "")}
              onClick={() => { setGroup(key); setEditing(null); }}>
              {label} <span className="dc-n">{(draft[key] ?? []).length}</span>
            </button>
          ))}
        </div>
      )}

      <div className="bk-row">
        <input ref={findRef} className="in" value={query} placeholder="Найти или добавить…" aria-label="Найти или добавить"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } if (e.key === "Escape") setQuery(""); }} />
        <button type="button" className="btn" disabled={!query.trim() || exact} onClick={add}>
          {query.trim() && !exact ? `Добавить «${query.trim()}»` : "Добавить"}
        </button>
        <button type="button" className="link-btn" disabled={items.length < 2} onClick={sortAbc}>по алфавиту</button>
      </div>

      <div className="dc-meta muted">
        {items.length} {plural(items.length, "значение", "значения", "значений")}
        {q && <> · найдено {shown.length}{exact && " · такое уже есть"}</>}
      </div>

      <ol className="dc-list">
        {shown.map(({ text, index }) => (
          <li key={index + text} className="dc-item">
            {editing?.index === index ? (
              <input className="in dc-edit" autoFocus value={editing.text} aria-label="Новое название"
                onChange={(e) => setEditing({ index, text: e.target.value })}
                onBlur={rename}
                onKeyDown={(e) => { if (e.key === "Enter") rename(); if (e.key === "Escape") setEditing(null); }} />
            ) : (
              <button type="button" className="dc-text" title="Изменить" onClick={() => setEditing({ index, text })}>{text}</button>
            )}
            {!q && (
              <>
                <button type="button" className="dc-icon" aria-label={`Выше: ${text}`} disabled={index === 0} onClick={() => move(index, -1)}>↑</button>
                <button type="button" className="dc-icon" aria-label={`Ниже: ${text}`} disabled={index === items.length - 1} onClick={() => move(index, 1)}>↓</button>
              </>
            )}
            <button type="button" className="dc-icon del" aria-label={`Убрать: ${text}`} onClick={() => remove(index)}>×</button>
          </li>
        ))}
        {items.length === 0 && <li className="muted dc-empty">Список пуст. Напишите значение выше и нажмите Enter.</li>}
      </ol>

      <div className="st-foot">
        {status && <span className={"st-status " + status.kind} role="status">{status.text}</span>}
        {info.canReset && info.edited && !dirty && (
          <button type="button" className="link-btn" disabled={busy} onClick={reset}>вернуть как при установке</button>
        )}
        <div style={{ flex: 1 }} />
        <button type="button" className="btn" disabled={!dirty || busy} onClick={() => { setDraft(asGroups(info.value)); setEditing(null); }}>Отменить</button>
        <button type="button" className="btn primary" disabled={!dirty || busy} onClick={save}>{busy ? "Сохраняем…" : "Сохранить"}</button>
      </div>
    </section>
  );
}
