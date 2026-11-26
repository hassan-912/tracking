"use client";

import { useCallback, useEffect, useState } from "react";
import SiteTabs from "@/components/SiteTabs";
import { categoryOf, type CategoryKey } from "@/lib/categories";

type Client = { id: number; name: string; ref: string; problem: string };
type Result = { client: string; status?: string; problem?: string; changed?: string };
type Step = { n: number; total: number; client: string; email: string; site: string };
type Action = "done" | "cancel" | "email" | "password" | "skip";
type Job = {
  id: number; category: string; state: string; windows: number; step: Step | null;
  log: string; error: string;
  results: Result[] | null; has_pdf: boolean; has_xlsx: boolean;
  created_at: string; finished_at: string | null;
};
type Agent = { host: string; last_seen: string; online: boolean } | null;

const ACTIVE = ["queued", "running", "waiting"];

export default function Tracking() {
  const [site, setSite] = useState<CategoryKey>("wes");
  const [loaded, setLoaded] = useState<{ site: CategoryKey; list: Client[] } | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [agent, setAgent] = useState<Agent>(null);
  const [error, setError] = useState("");
  const cat = categoryOf(site)!;
  const clients = loaded?.site === site ? loaded.list : null;   // null while loading

  useEffect(() => {
    fetch(`/api/clients?category=${site}`).then((r) => r.json())
      .then((list: Client[]) => setLoaded({ site, list }));
  }, [site]);

  function changeSite(key: CategoryKey) {
    setSite(key);
    setPicked([]);
  }

  const poll = useCallback(async () => {
    const r = await fetch("/api/jobs");
    if (!r.ok) return;
    const data = await r.json();
    setJob(data.job);
    setAgent(data.agent);
  }, []);

  useEffect(() => {
    const first = setTimeout(poll, 0);
    const t = setInterval(poll, 3000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [poll]);

  const busy = !!job && ACTIVE.includes(job.state);
  const ready = clients?.filter((c) => !c.problem) ?? [];

  async function start(ids: number[] | null) {
    setError("");
    const r = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: site, ids }),
    });
    if (!r.ok) setError((await r.json()).error ?? "Could not start.");
    setPicked([]);
    poll();
  }

  async function act(action: Action) {
    if (!job) return;
    if (action === "cancel" && !confirm("Stop this tracking run?")) return;
    await fetch(`/api/jobs/${job.id}/${action}`, { method: "POST" });
    poll();
  }

  const toggle = (id: number) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  return (
    <>
      <h1>Tracking</h1>
      <AgentStatus agent={agent} />
      <SiteTabs value={site} onChange={changeSite} />

      <section className="card">
        <div className="toolbar">
          <button className="primary" disabled={busy || !ready.length || !agent?.online}
                  onClick={() => start(null)}>
            Check all {ready.length} clients
          </button>
          <button disabled={busy || !picked.length || !agent?.online}
                  onClick={() => start(picked)}>
            Check {picked.length} selected
          </button>
          {cat.usesCaptcha && (
            <span className="muted">CAPTCHA windows open on the office PC{agent?.host ? ` (${agent.host})` : ""}.</span>
          )}
          {cat.manualLogin && (
            <span className="muted">
              One client at a time: you log in on the office PC{agent?.host ? ` (${agent.host})` : ""},
              the program copies the details and reads the status.
            </span>
          )}
        </div>
        {error && <p className="error">{error}</p>}
        <table className="grid">
          <thead>
            <tr><th></th><th>Client</th><th>{cat.refLabel}</th><th>Ready?</th></tr>
          </thead>
          <tbody>
            {clients === null && <tr><td colSpan={4} className="muted">Loading…</td></tr>}
            {clients?.length === 0 && (
              <tr><td colSpan={4} className="muted">No clients yet — add them in Data entry.</td></tr>
            )}
            {clients?.map((c) => (
              <tr key={c.id} onClick={() => !c.problem && toggle(c.id)} className="clickable">
                <td>
                  <input type="checkbox" checked={picked.includes(c.id)} disabled={!!c.problem}
                         onChange={() => toggle(c.id)} onClick={(e) => e.stopPropagation()} />
                </td>
                <td>{c.name || "—"}</td>
                <td className="mono">{c.ref}</td>
                <td className={c.problem ? "bad" : "good"}>{c.problem ? `✖ ${c.problem}` : "✔"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {job && <JobPanel job={job} onAct={act} />}
    </>
  );
}

function AgentStatus({ agent }: { agent: Agent }) {
  if (agent?.online) {
    return <p className="pill good-pill">● Office PC helper is online ({agent.host})</p>;
  }
  return (
    <p className="pill bad-pill">
      ● Office PC helper is offline — start “Start office helper.bat” on the office PC to run checks.
    </p>
  );
}

function JobPanel({ job, onAct }: { job: Job; onAct: (a: Action) => void }) {
  const title = categoryOf(job.category)?.title ?? job.category;
  const results = job.results ?? [];
  const okCount = results.filter((r) => !r.problem).length;
  const changed = results.filter((r) => r.changed === "YES").length;

  return (
    <section className="card">
      <div className="toolbar">
        <h2 className="small-heading">{title} — {LABELS[job.state] ?? job.state}</h2>
        {ACTIVE.includes(job.state) && <button onClick={() => onAct("cancel")}>Stop</button>}
      </div>

      {job.state === "queued" && <p className="muted">Waiting for the office PC to start…</p>}
      {job.state === "running" && (
        <p className="muted">
          Working… this page updates by itself. “Needs you in the browser” in the details usually
          just means a site is slow — act on the office PC only if a window there asks for an OTP
          or a security question.
        </p>
      )}
      {job.state === "waiting" && job.step && <TlsStep step={job.step} onAct={onAct} />}
      {job.state === "waiting" && !job.step && (
        <div className="callout">
          <strong>Your turn: CAPTCHAs</strong>
          <p>
            {job.windows} window(s) are open on the office PC. In each one: type the CAPTCHA and
            submit (BLS: Verify → pictures → Submit · Brazil: hCaptcha → SEARCH). Wait until every
            window shows its result, then press the button.
          </p>
          <button className="primary" onClick={() => onAct("done")}>
            I&apos;ve finished all the CAPTCHAs
          </button>
        </div>
      )}
      {job.state === "failed" && <p className="error">Tracking stopped: {job.error}</p>}

      {job.state === "finished" && (
        <>
          <p className="good">
            {okCount} checked · {changed} changed since last time · {results.length - okCount} need a look
          </p>
          <div className="toolbar">
            {job.has_pdf && <a className="button primary" href={`/api/jobs/${job.id}/pdf`}>Screenshots PDF</a>}
            {job.has_xlsx && <a className="button" href={`/api/jobs/${job.id}/xlsx`}>Results Excel</a>}
          </div>
          <table className="grid">
            <thead><tr><th>Client</th><th>Status</th><th>Changed?</th><th>Problem</th></tr></thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i}>
                  <td>{r.client || "—"}</td><td>{r.status ?? ""}</td>
                  <td>{r.changed ?? ""}</td><td className={r.problem ? "bad" : ""}>{r.problem ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {job.log && (
        <details open={job.state !== "finished"}>
          <summary>Details</summary>
          <pre>{job.log.split("\n").slice(-40).join("\n")}</pre>
        </details>
      )}
    </section>
  );
}

/** TLS: the client whose Edge window is open on the office PC right now. */
function TlsStep({ step, onAct }: { step: Step; onAct: (a: Action) => void }) {
  return (
    <div className="callout">
      <strong>
        Your turn: TLS {step.site} login {step.n} of {step.total} · {step.client}
      </strong>
      <ol>
        <li>In the Edge window on the office PC, tick “Verify you are human” if it shows, then open Login.</li>
        <li>The email <span className="mono">{step.email}</span> is already copied: click the email box and press Ctrl+V.</li>
        <li>Press <em>Copy password</em> here, click the password box and press Ctrl+V. Click Log in.</li>
        <li>When the page shows the application, press <em>Next client</em>. The program takes the screenshot and reads the status.</li>
      </ol>
      <div className="toolbar">
        <button onClick={() => onAct("email")}>Copy email again</button>
        <button onClick={() => onAct("password")}>Copy password</button>
        <button className="primary" onClick={() => onAct("done")}>
          {step.n < step.total ? "Next client" : "Finish"}
        </button>
        <button onClick={() => onAct("skip")}>Skip this client</button>
      </div>
    </div>
  );
}

const LABELS: Record<string, string> = {
  queued: "starting", running: "running", waiting: "waiting for you",
  finished: "finished", failed: "failed", cancelled: "stopped",
};
