import { useEffect, useState } from "react";
import type { Notification } from "../lib/types";
import { useApi } from "../lib/useApi";
import { ErrorNote } from "../components/Layout";

export function Notifications() {
  const api = useApi();
  const [items, setItems] = useState<Notification[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { api.notifications().then((p) => setItems(p.items), setError); }, [api]);
  return (
    <section className="card narrow">
      <h2>Notifications</h2>
      <ErrorNote error={error} />
      {items === null ? <p>Loading…</p> : items.length === 0 ? <p className="muted">No notifications yet.</p> : (
        <ul className="notes">
          {items.map((n, i) => (
            <li key={`${n.created_at}-${i}`}><strong>{n.title}</strong><span>{n.message}</span><time>{new Date(n.created_at).toLocaleString()}</time></li>
          ))}
        </ul>
      )}
    </section>
  );
}
