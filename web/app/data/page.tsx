"use client";

import { useCallback, useEffect, useState } from "react";
import SiteTabs from "@/components/SiteTabs";
import { categoryOf, problemOf, type Category, type CategoryKey } from "@/lib/categories";

type Client = { id?: number; name: string; ref: string; secret: string; notes: string };
const EMPTY: Client = { name: "", ref: "", secret: "", notes: "" };

export default function DataEntry() {
  const [site, setSite] = useState<CategoryKey>("wes");
  const [loaded, setLoaded] = useState<{ site: CategoryKey; list: Client[] } | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>();
  const [message, setMessage] = useState("");
  const cat = categoryOf(site)!;
  const clients = loaded?.site === site ? loaded.list : null;   // null while loading

  const reload = useCallback(async () => {
    const [list, n] = await Promise.all([
      fetch(`/api/clients?category=${site}`).then((r) => r.json()),
      fetch("/api/clients").then((r) => r.json()),
    ]);
    setLoaded({ site, list });
    setCounts(n);
  }, [site]);

  useEffect(() => {
    const t = setTimeout(reload, 0);   // load this site's clients when the tab changes
    return () => clearTimeout(t);
  }, [reload]);

  function flash(text: string) {
    setMessage(text);
    setTimeout(() => setMessage(""), 2500);
  }

  async function save(client: Client) {
    const res = await fetch(client.id ? `/api/clients/${client.id}` : "/api/clients", {
      method: client.id ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...client, category: site }),
    });
    if (!res.ok) return flash("Could not save — try again.");
    flash(client.id ? "Saved" : "Client added");
    await reload();
  }

  async function remove(client: Client) {
    if (!client.id || !confirm(`Remove ${client.name || client.ref} from ${cat.title}?`)) return;
    await fetch(`/api/clients/${client.id}`, { method: "DELETE" });
    flash("Client removed");
    await reload();
  }

  return (
    <>
      <h1>Data entry</h1>
      <SiteTabs value={site} onChange={setSite} counts={counts} />
      {message && <div className="toast">{message}</div>}

      <section className="card">
        <h2 className="small-heading">Add a {cat.title} client</h2>
        <ClientRow key={`new-${site}`} cat={cat} client={EMPTY} onSave={save} isNew />
      </section>

      <section className="card">
        <table className="grid">
          <thead>
            <tr>
              <th>Client name</th><th>{cat.refLabel}</th><th>{cat.secretLabel}</th>
              <th>Notes</th><th>Ready?</th><th></th>
            </tr>
          </thead>
          <tbody>
            {clients === null && <tr><td colSpan={6} className="muted">Loading…</td></tr>}
            {clients?.length === 0 && <tr><td colSpan={6} className="muted">No clients yet.</td></tr>}
            {clients?.map((c) => (
              <ClientRow key={c.id} cat={cat} client={c} onSave={save} onRemove={remove} />
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function ClientRow({ cat, client, onSave, onRemove, isNew }: {
  cat: Category;
  client: Client;
  onSave: (c: Client) => Promise<void>;
  onRemove?: (c: Client) => Promise<void>;
  isNew?: boolean;
}) {
  const [draft, setDraft] = useState<Client>(client);
  const [busy, setBusy] = useState(false);
  const changed = JSON.stringify(draft) !== JSON.stringify(client);
  const problem = problemOf(cat, draft.ref, draft.secret);
  const set = (k: keyof Client) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDraft({ ...draft, [k]: e.target.value });

  async function submit() {
    setBusy(true);
    await onSave(draft);
    setBusy(false);
    if (isNew) setDraft(EMPTY);
  }

  const cells = (
    <>
      <td><input value={draft.name} onChange={set("name")} placeholder="Full name" /></td>
      <td><input value={draft.ref} onChange={set("ref")} placeholder={cat.refHint} /></td>
      <td>
        <input value={draft.secret} onChange={set("secret")}
               type={cat.secretKind === "date" ? "date" : "text"} placeholder={cat.secretLabel} />
      </td>
      <td><input value={draft.notes} onChange={set("notes")} placeholder="Notes" /></td>
      <td className={problem ? "bad" : "good"}>{problem ? `✖ ${problem}` : "✔ ready"}</td>
      <td className="actions">
        {(changed || isNew) && (
          <button className="primary" disabled={busy || (isNew && !draft.ref)} onClick={submit}>
            {isNew ? "Add" : "Save"}
          </button>
        )}
        {!isNew && changed && <button onClick={() => setDraft(client)}>Undo</button>}
        {!isNew && !changed && <button className="danger" onClick={() => onRemove?.(client)}>Remove</button>}
      </td>
    </>
  );
  return isNew ? <table className="grid"><tbody><tr>{cells}</tr></tbody></table> : <tr>{cells}</tr>;
}
