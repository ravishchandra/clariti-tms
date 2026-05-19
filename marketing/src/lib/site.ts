export const site = {
  name: "Clariti TMS",
  tagline: "The translation management system you actually own.",
  description:
    "Clariti TMS is a self-hosted, AGPL-licensed translation management system with context-aware LLM translation, bring-your-own provider (Claude, GPT, DeepL, Ollama), back-translation QA, and native iOS / Android / web pipelines. Replace Lokalise, Phrase, and Crowdin without seat pricing.",
  url: "https://clariti-tms.vercel.app",
  github: "https://github.com/ravishchandra/clariti-tms",
  twitter: "https://twitter.com/claritihq",
  navLinks: [
    { href: "/playground", label: "Playground" },
    { href: "/agents", label: "Agents" },
    { href: "/#compare", label: "Compare" },
    { href: "/pricing", label: "Pricing" },
    { href: "/changelog", label: "Changelog" },
  ],
  ctaPrimary: { href: "/playground", label: "Try the playground" },
  ctaSecondary: { href: "/#install", label: "Self-host in 5 min" },
};

export type Locale = {
  code: string;
  label: string;
  native: string;
  rtl?: boolean;
};

export const showcaseLocales: Locale[] = [
  { code: "fr-FR", label: "French", native: "Français" },
  { code: "de-DE", label: "German", native: "Deutsch" },
  { code: "ja-JP", label: "Japanese", native: "日本語" },
  { code: "es-ES", label: "Spanish", native: "Español" },
  { code: "pt-BR", label: "Portuguese (BR)", native: "Português" },
  { code: "ko-KR", label: "Korean", native: "한국어" },
  { code: "zh-CN", label: "Chinese (S)", native: "简体中文" },
  { code: "ar-SA", label: "Arabic", native: "العربية", rtl: true },
  { code: "hi-IN", label: "Hindi", native: "हिन्दी" },
  { code: "it-IT", label: "Italian", native: "Italiano" },
  { code: "nl-NL", label: "Dutch", native: "Nederlands" },
  { code: "pl-PL", label: "Polish", native: "Polski" },
  { code: "tr-TR", label: "Turkish", native: "Türkçe" },
  { code: "ru-RU", label: "Russian", native: "Русский" },
  { code: "sv-SE", label: "Swedish", native: "Svenska" },
  { code: "id-ID", label: "Indonesian", native: "Bahasa Indonesia" },
];
