import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Providers } from "@/lib/providers";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
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
    // them up — Tailwind v4's @theme inline can't resolve runtime CSS vars.
    <html
      lang="en"
      className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-app-bg text-app-text flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
