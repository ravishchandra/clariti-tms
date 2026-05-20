import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { site } from "@/lib/site";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafaf7" },
    { media: "(prefers-color-scheme: dark)", color: "#07080a" },
  ],
  width: "device-width",
  initialScale: 1,
};

// Inline script runs before paint to apply the saved theme — no flash on reload.
// Default is light; honors a previously-saved choice if present.
const themeScript = `(function(){try{var s=localStorage.getItem('clariti-theme');var d=document.documentElement;if(s==='dark'){d.classList.add('dark');}else{d.classList.remove('dark');}}catch(e){}})();`;

export const metadata: Metadata = {
  metadataBase: new URL(site.url),
  title: {
    default: `${site.name} — ${site.tagline}`,
    template: `%s · ${site.name}`,
  },
  description: site.description,
  applicationName: site.name,
  keywords: [
    "translation management system",
    "TMS",
    "self-hosted translation",
    "open source localization",
    "i18n platform",
    "Lokalise alternative",
    "Phrase alternative",
    "Crowdin alternative",
    "LLM translation",
    "context-aware machine translation",
    "translation memory",
    "iOS .strings",
    "Android strings.xml",
    "i18next",
    "ICU MessageFormat",
    "XLIFF",
    "OTA translations",
  ],
  authors: [{ name: "ClaritiTMS contributors" }],
  creator: "ClaritiTMS",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: site.name,
    title: `${site.name} — ${site.tagline}`,
    description: site.description,
    url: site.url,
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: `${site.name} — ${site.tagline}`,
    description: site.description,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1 },
  },
  category: "developer tools",
};

const organizationJsonLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: site.name,
  url: site.url,
  description: site.description,
  sameAs: [site.github, site.twitter],
  logo: `${site.url}/logo.svg`,
};

const softwareJsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: site.name,
  applicationCategory: "DeveloperApplication",
  applicationSubCategory: "Translation Management System",
  operatingSystem: "Linux, macOS, Docker",
  description: site.description,
  url: site.url,
  offers: [
    {
      "@type": "Offer",
      name: "Self-hosted (Open Source)",
      price: "0",
      priceCurrency: "USD",
      description: "AGPL-3.0 self-host. Free forever for teams that run their own infrastructure.",
    },
    {
      "@type": "Offer",
      name: "Commercial License",
      description: "Commercial license for organisations whose use is incompatible with the AGPL.",
    },
  ],
  softwareRequirements: "Python 3.12+, PostgreSQL 16 with pgvector, Node 20+",
  featureList: [
    "Self-hosted, data stays in your infrastructure",
    "Bring your own LLM (Claude, GPT, DeepL, Ollama)",
    "Screen-batch translation with full context",
    "Back-translation QA on every machine output",
    "Native iOS .strings, .xcstrings, .stringsdict",
    "Native Android strings.xml + layout grouping",
    "i18next JSON, ICU MessageFormat, XLIFF, Excel round-trip",
    "GitHub PR-back and Contentful sync",
    "OTA delivery for mobile apps",
    "Translation memory with HNSW vector search",
    "Keyboard-first review UI",
  ],
  license: "https://www.gnu.org/licenses/agpl-3.0.html",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationJsonLd) }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareJsonLd) }}
        />
        {children}
      </body>
    </html>
  );
}
