import { useState } from "react";

/** Toggle chips; «+» adds the doctor's own value, which is ticked and printed like any other. */
export function MultiChips({ options, value, onChange, disabled }: { options: string[]; value: string[]; onChange: (v: string[]) => void; disabled?: boolean }) {
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const extra = value.filter((v) => !options.includes(v));

  const add = () => {
    const v = text.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setText("");
    setAdding(false);
  };

  return (
    <span className="ex-chips">
      {[...options, ...extra].map((o) => {
        const on = value.includes(o);
        return (
          <button key={o} type="button" className={"chip" + (on ? " on" : "")} aria-pressed={on} disabled={disabled}
            onClick={() => onChange(on ? value.filter((v) => v !== o) : [...value, o])}>
            {o}
          </button>
        );
      })}
      {!disabled && (adding ? (
        <input className="in ex-add" autoFocus placeholder="свой вариант, Enter — добавить" value={text}
          onChange={(e) => setText(e.target.value)} onBlur={add}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); add(); }
            if (e.key === "Escape") { setText(""); setAdding(false); }
          }} />
      ) : (
        <button type="button" className="chip ex-plus" aria-label="Добавить свой вариант" title="Добавить свой вариант" onClick={() => setAdding(true)}>
          <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M7 2v10M2 7h10" /></svg>
        </button>
      ))}
    </span>
  );
}
