"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/tracking", label: "Tracking" },
  { href: "/data", label: "Data entry" },
];

export default function Nav() {
  const path = usePathname();
  const router = useRouter();
  if (path === "/login") return null;

  async function signOut() {
    await fetch("/api/login", { method: "DELETE" });
    router.push("/login");
  }

  return (
    <header className="nav">
      <span className="brand">Visa tracking</span>
      <nav>
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className={path === l.href ? "active" : ""}>
            {l.label}
          </Link>
        ))}
      </nav>
      <button className="link" onClick={signOut}>Sign out</button>
    </header>
  );
}
