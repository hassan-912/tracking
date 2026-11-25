import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "Visa tracking",
  description: "Check clients' visa application statuses",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
