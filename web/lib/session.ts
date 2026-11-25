// Signed sign-in cookie. Uses Web Crypto so it works in proxy.ts and in routes.

export const SESSION_COOKIE = "vt_session";
export const SESSION_DAYS = 14;

const enc = new TextEncoder();

async function hmac(data: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(process.env.SESSION_SECRET ?? ""), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(data));
  return btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/=+$/, "")
    .replace(/\+/g, "-").replace(/\//g, "_");
}

/** "<expires-ms>.<signature>" */
export async function makeSession(): Promise<string> {
  const expires = Date.now() + SESSION_DAYS * 86_400_000;
  return `${expires}.${await hmac(String(expires))}`;
}

export async function validSession(value: string | undefined): Promise<boolean> {
  if (!value || !process.env.SESSION_SECRET) return false;
  const [expires, sig] = value.split(".");
  if (!expires || !sig || Number(expires) < Date.now()) return false;
  const good = await hmac(expires);
  if (good.length !== sig.length) return false;
  let diff = 0;
  for (let i = 0; i < good.length; i++) diff |= good.charCodeAt(i) ^ sig.charCodeAt(i);
  return diff === 0;
}
