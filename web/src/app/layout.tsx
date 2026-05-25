import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Providers } from "@/lib/providers";

import "./globals.css";

// Editorial typography stack — mirrors marketing/src/app/layout.tsx so the
// dashboard and the marketing site share a font signature. next/font is
// used here (vs. the geist npm package on marketing) to avoid an extra dep;
// the resulting CSS variables are identical.
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "ClaritiTMS",
  description: "Self-hosted translation management system.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // `dark` is the product default (DESIGN.md: developer tool, dark-first).
    // Font variables on <html> so all descendant Tailwind classes can pick
    // them up — globals.css' @theme inline binds --font-sans to
    // var(--font-geist-sans) so `font-sans` resolves to Geist everywhere.
    <html
      lang="en"
      className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-background text-foreground flex flex-col font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
