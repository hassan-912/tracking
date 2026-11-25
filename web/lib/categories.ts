// The six tracking sites. Same rules as tracker/clients_db.py on the office PC.

export type CategoryKey =
  | "wes"
  | "bls_tourism"
  | "bls_study"
  | "vfs"
  | "romania_study"
  | "brazil";

export type Category = {
  key: CategoryKey;
  title: string;
  refLabel: string;
  refHint: string;
  refPattern: RegExp;
  secretLabel: string;
  secretKind: "text" | "date" | "password";
  usesCaptcha: boolean;
};

export const CATEGORIES: Category[] = [
  { key: "wes", title: "WES", refLabel: "Email", refHint: "client@email.com",
    refPattern: /^[^@\s]+@[^@\s]+\.[^@\s]+$/, secretLabel: "Password", secretKind: "password",
    usesCaptcha: false },
  { key: "bls_tourism", title: "BLS Tourism", refLabel: "BLS reference", refHint: "CAI12345678901",
    refPattern: /^[A-Z]{3}\d{6,}$/i, secretLabel: "Date of birth", secretKind: "date",
    usesCaptcha: true },
  { key: "bls_study", title: "BLS Study", refLabel: "BLS reference", refHint: "CAI12345678901",
    refPattern: /^[A-Z]{3}\d{6,}$/i, secretLabel: "Date of birth", secretKind: "date",
    usesCaptcha: true },
  { key: "vfs", title: "VFS", refLabel: "VFS reference", refHint: "NLD/CAI/123456/1234/01",
    refPattern: /^[A-Z]{3,4}\/[A-Z0-9/]+$/i, secretLabel: "Surname", secretKind: "text",
    usesCaptcha: true },
  { key: "romania_study", title: "Romania Study", refLabel: "e-Visa file number",
    refHint: "E12345678901234", refPattern: /^E\d{14}$/i, secretLabel: "Password",
    secretKind: "password", usesCaptcha: true },
  { key: "brazil", title: "Brazil", refLabel: "Recovery code", refHint: "AB12CD34EF",
    refPattern: /^[A-Z0-9]{10}$/i, secretLabel: "Date of birth", secretKind: "date",
    usesCaptcha: true },
];

export function categoryOf(key: string | null): Category | undefined {
  return CATEGORIES.find((c) => c.key === key);
}

/** Tidy a reference the way the tracker expects it (no spaces, capitals; emails untouched). */
export function cleanRef(cat: Category, ref: string): string {
  const t = ref.trim();
  return cat.key === "wes" ? t : t.replace(/\s+/g, "").toUpperCase();
}

/** Why this client can't be checked yet ('' when it can). */
export function problemOf(cat: Category, ref: string, secret: string): string {
  const r = cleanRef(cat, ref);
  if (!r) return `${cat.refLabel} is empty`;
  if (!cat.refPattern.test(r)) return `${cat.refLabel} doesn't look right (like ${cat.refHint})`;
  if (!secret.trim()) return `${cat.secretLabel} is empty`;
  if (cat.secretKind === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(secret.trim()))
    return `${cat.secretLabel} must be a date`;
  return "";
}
