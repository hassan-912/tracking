import "server-only";
import { createCipheriv, createDecipheriv, createHmac, randomBytes, timingSafeEqual } from "node:crypto";

// ---- client passwords / birth dates: AES-256-GCM, key only in env vars ----
// Format "v1:<iv>:<tag>:<ciphertext>" (base64). The office PC helper reads the same format.

function dataKey(): Buffer {
  const key = Buffer.from(process.env.CLIENT_DATA_KEY ?? "", "base64");
  if (key.length !== 32) throw new Error("CLIENT_DATA_KEY must be 32 bytes, base64");
  return key;
}

export function encrypt(plain: string): string {
  if (!plain) return "";
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", dataKey(), iv);
  const body = Buffer.concat([cipher.update(plain, "utf8"), cipher.final()]);
  return ["v1", iv, cipher.getAuthTag(), body].map((p) => (typeof p === "string" ? p : p.toString("base64"))).join(":");
}

export function decrypt(stored: string): string {
  if (!stored) return "";
  const [version, iv, tag, body] = stored.split(":");
  if (version !== "v1") throw new Error("Unknown encrypted format");
  const decipher = createDecipheriv("aes-256-gcm", dataKey(), Buffer.from(iv, "base64"));
  decipher.setAuthTag(Buffer.from(tag, "base64"));
  return Buffer.concat([decipher.update(Buffer.from(body, "base64")), decipher.final()]).toString("utf8");
}

// ---- office password check ----

export function passwordMatches(typed: string): boolean {
  const expected = process.env.OFFICE_PASSWORD ?? "";
  if (!expected) return false;
  const a = createHmac("sha256", "cmp").update(typed).digest();
  const b = createHmac("sha256", "cmp").update(expected).digest();
  return timingSafeEqual(a, b);
}
