import type { Metadata } from "next";
import "./globals.css";
import "./premium.css";
import "./crypto.css";
export const metadata: Metadata = {
  title: "Aiventra OS — Command Center",
  description: "A supervised operating system for your AI workforce.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
