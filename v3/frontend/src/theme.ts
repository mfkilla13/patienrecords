/** Light / dark theme: «как в Windows» follows the system setting and changes with it. */
export type ThemeChoice = "auto" | "light" | "dark";

const KEY = "medqt-theme";
const media = window.matchMedia("(prefers-color-scheme: dark)");
let choice: ThemeChoice = "auto";

function resolve(): "light" | "dark" {
  return choice === "auto" ? (media.matches ? "dark" : "light") : choice;
}

function paint(): void {
  document.documentElement.dataset.theme = resolve();
}

media.addEventListener("change", () => { if (choice === "auto") paint(); });

export function applyTheme(next: string | null | undefined): void {
  choice = next === "light" || next === "dark" ? next : "auto";
  try {
    localStorage.setItem(KEY, choice);       // only so the first frame is already right; the setting lives in the database
  } catch {
    /* private mode or blocked storage: the theme still applies */
  }
  paint();
}

/** Before the first render: the last known choice, so the window does not flash light first. */
export function initTheme(): void {
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(KEY);
  } catch {
    saved = null;
  }
  applyTheme(saved);
}
