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

// Inline pre-paint theme script — same key + shape as marketing so the
// dashboard and marketing share theme state across same-origin tabs.
// Default is light to match the marketing site; honors a saved 'dark'
// preference if one exists. Runs before paint, so no FOUC.
const themeScript = `(function(){try{var s=localStorage.getItem('clariti-theme');var d=document.documentElement;if(s==='dark'){d.classList.add('dark');}else{d.classList.remove('dark');}}catch(e){}})();`;

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
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full bg-background text-foreground flex flex-col font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
