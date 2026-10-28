import { Link } from "react-router-dom";

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <main className="page" style={{ paddingTop: 24 }}>
      <section className="card" style={{ padding: "28px 32px", display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-start" }}>
        <h1 style={{ margin: 0, fontSize: 28 }}>{title}</h1>
        <p className="muted" style={{ margin: 0 }}>Этот экран ещё в работе.</p>
        <Link to="/" className="btn">← В отделение</Link>
      </section>
    </main>
  );
}
