import "server-only";
import { neon } from "@neondatabase/serverless";

export function sql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set (add the Neon database in Vercel)");
  return neon(url);
}

let ready: Promise<void> | null = null;

/** Create the tables the first time (safe to call on every request). */
export function ensureSchema(): Promise<void> {
  ready ??= (async () => {
    const db = sql();
    await db`CREATE TABLE IF NOT EXISTS clients (
      id SERIAL PRIMARY KEY,
      category TEXT NOT NULL,
      name TEXT NOT NULL DEFAULT '',
      ref TEXT NOT NULL DEFAULT '',
      secret_enc TEXT NOT NULL DEFAULT '',
      notes TEXT NOT NULL DEFAULT '',
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now())`;
    await db`CREATE TABLE IF NOT EXISTS jobs (
      id SERIAL PRIMARY KEY,
      category TEXT NOT NULL,
      client_ids INTEGER[],
      state TEXT NOT NULL DEFAULT 'queued',
      windows INTEGER NOT NULL DEFAULT 0,
      done_clicked BOOLEAN NOT NULL DEFAULT false,
      log TEXT NOT NULL DEFAULT '',
      error TEXT NOT NULL DEFAULT '',
      results JSONB,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      started_at TIMESTAMPTZ,
      finished_at TIMESTAMPTZ)`;
    // PDF / Excel of a run, uploaded by the office PC in parts (Vercel caps each request at 4.5 MB).
    await db`CREATE TABLE IF NOT EXISTS job_files (
      job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
      kind TEXT NOT NULL,
      part INTEGER NOT NULL,
      data BYTEA NOT NULL,
      PRIMARY KEY (job_id, kind, part))`;
    await db`CREATE TABLE IF NOT EXISTS agent (
      id INTEGER PRIMARY KEY DEFAULT 1,
      host TEXT NOT NULL DEFAULT '',
      last_seen TIMESTAMPTZ)`;
  })().catch((e) => {
    ready = null;
    throw e;
  });
  return ready;
}
