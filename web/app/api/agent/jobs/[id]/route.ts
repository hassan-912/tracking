import { NextResponse } from "next/server";
import { agentDenied } from "@/lib/agent";
import { ensureSchema, sql } from "@/lib/db";

// The office helper reports progress on a run:
//   {log: "new lines"}                       append to the run's details
//   {state: "waiting", windows: 3}           CAPTCHA windows are ready
//   {state: "waiting", windows: 1, step: {…}} TLS: this client's window is open
//   {state: "finished", results: [...]}      done
//   {state: "failed", error: "..."}          went wrong
//   {file: {kind: "pdf"|"xlsx", part: 0, data: "<base64>"}}  one part of a file
// Answers with the run's state, whether "I've finished the CAPTCHAs" / "Next client"
// was pressed, and any TLS button pressed since the last message (then forgets it).
export async function POST(request: Request, ctx: RouteContext<"/api/agent/jobs/[id]">) {
  const denied = agentDenied(request);
  if (denied) return denied;
  await ensureSchema();
  const id = Number((await ctx.params).id);
  const body = await request.json();
  const db = sql();
  // Any message from the helper during a run also means "still online".
  await db`UPDATE agent SET last_seen = now() WHERE id = 1`;

  if (body.file) {
    const { kind, part, data } = body.file;
    if ((kind === "pdf" || kind === "xlsx") && Number.isInteger(part)) {
      await db`INSERT INTO job_files (job_id, kind, part, data)
               VALUES (${id}, ${kind}, ${part}, decode(${String(data)}, 'base64'))
               ON CONFLICT (job_id, kind, part) DO UPDATE SET data = EXCLUDED.data`;
    }
  }
  if (body.log) {
    await db`UPDATE jobs SET log = right(log || ${String(body.log)}, 20000) WHERE id = ${id}`;
  }
  if (body.state === "waiting") {
    await db`UPDATE jobs SET state = 'waiting', windows = ${Number(body.windows ?? 0)},
               step = ${body.step ? JSON.stringify(body.step) : null}::jsonb,
               done_clicked = false, request = ''
             WHERE id = ${id} AND state <> 'cancelled'`;
  } else if (body.state === "running") {
    await db`UPDATE jobs SET state = 'running', step = NULL
             WHERE id = ${id} AND state <> 'cancelled'`;
  } else if (body.state === "finished" || body.state === "failed") {
    await db`UPDATE jobs SET state = ${body.state}, results = ${JSON.stringify(body.results ?? null)}::jsonb,
               error = ${String(body.error ?? "")}, finished_at = now()
             WHERE id = ${id}`;
  }

  const rows = (await db`WITH old AS (SELECT id, request FROM jobs WHERE id = ${id} FOR UPDATE)
      UPDATE jobs SET request = '' FROM old WHERE jobs.id = old.id
      RETURNING jobs.state, jobs.done_clicked, old.request`) as
    { state: string; done_clicked: boolean; request: string }[];
  return NextResponse.json(rows[0] ?? { state: "missing", done_clicked: true });
}
