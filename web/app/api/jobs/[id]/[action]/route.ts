import { NextResponse } from "next/server";
import { ensureSchema, sql } from "@/lib/db";

// POST /api/jobs/5/done    -> "I've finished all the CAPTCHAs"
// POST /api/jobs/5/cancel  -> stop this run
// POST /api/jobs/5/email | password | skip  -> TLS: copy that onto the office PC's
//                                             clipboard, or skip this client
export async function POST(_request: Request, ctx: RouteContext<"/api/jobs/[id]/[action]">) {
  await ensureSchema();
  const { id, action } = await ctx.params;
  const db = sql();
  if (action === "done") {
    await db`UPDATE jobs SET done_clicked = true WHERE id = ${Number(id)}`;
  } else if (action === "email" || action === "password" || action === "skip") {
    await db`UPDATE jobs SET request = ${action} WHERE id = ${Number(id)} AND state = 'waiting'`;
  } else if (action === "cancel") {
    await db`UPDATE jobs SET state = 'cancelled', finished_at = now()
             WHERE id = ${Number(id)} AND state IN ('queued', 'running', 'waiting')`;
  } else {
    return NextResponse.json({ error: "Unknown action" }, { status: 404 });
  }
  return NextResponse.json({ ok: true });
}

// GET /api/jobs/5/pdf  or  /api/jobs/5/xlsx -> download the run's file.
// Streamed part by part, so files bigger than Vercel's 4.5 MB response cap still work.
export async function GET(_request: Request, ctx: RouteContext<"/api/jobs/[id]/[action]">) {
  await ensureSchema();
  const { id, action } = await ctx.params;
  if (action !== "pdf" && action !== "xlsx") {
    return NextResponse.json({ error: "Unknown file" }, { status: 404 });
  }
  const jobId = Number(id);
  const db = sql();
  const info = (await db`SELECT j.category, j.created_at, COUNT(f.part)::int AS parts
      FROM jobs j LEFT JOIN job_files f ON f.job_id = j.id AND f.kind = ${action}
      WHERE j.id = ${jobId} GROUP BY j.id`) as { category: string; created_at: string; parts: number }[];
  if (!info[0]?.parts) return NextResponse.json({ error: "No file" }, { status: 404 });

  const { category, created_at, parts } = info[0];
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (let part = 0; part < parts; part++) {
        const rows = (await db`SELECT encode(data, 'base64') AS b64 FROM job_files
            WHERE job_id = ${jobId} AND kind = ${action} AND part = ${part}`) as { b64: string }[];
        controller.enqueue(new Uint8Array(Buffer.from(rows[0]?.b64 ?? "", "base64")));
      }
      controller.close();
    },
  });
  const stamp = new Date(created_at).toISOString().slice(0, 16).replace("T", " ").replace(":", "-");
  const name = action === "pdf" ? `Tracking screenshots ${category} ${stamp}.pdf`
                                : `Tracking ${category} ${stamp}.xlsx`;
  return new Response(stream, {
    headers: {
      "Content-Type": action === "pdf" ? "application/pdf"
        : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="${name}"`,
    },
  });
}
