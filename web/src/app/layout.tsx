import type { Metadata, Viewport } from "next";
import { Figtree } from "next/font/google";

import "./vibe.generated.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

import { AppShell } from "@/components/AppShell";

const figtree = Figtree({ subsets: ["latin"], variable: "--font-figtree", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Griffon", template: "%s · Griffon" },
  description: "Les annonces de logements à louer du Grand Montréal, réunies et dédoublonnées.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#181b34" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr-CA" className={figtree.variable} suppressHydrationWarning>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
