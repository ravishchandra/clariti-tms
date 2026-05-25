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

// Dashboard defaults to light mode. There's no UI to toggle to dark yet, and
// the marketing site's `clariti-theme` localStorage value isn't checked here
// — adding that script back is a small follow-up once a dark-mode toggle
// ships. Until then, omitting the script avoids the Next.js 16 warning about
// `<script>` tags inside React components and keeps the layout SSR-stable.
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full bg-background text-foreground flex flex-col font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
