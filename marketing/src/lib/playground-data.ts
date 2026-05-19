/**
 * Realistic-but-deterministic data backing the /playground simulator.
 * The numbers and translations here mirror what the real pipeline in
 * `app/llm/` and `app/mt/qa.py` produces; this lets the marketing site
 * demo the full pipeline shape without depending on a live backend.
 *
 * When a public read-only Clariti instance exists, swap the runSimulation
 * helper for a fetch() to it.
 */

export type SourceString = { key: string; value: string };

export type GlossaryMatch = {
  term: string;
  rule: "keep" | "lock" | "placeholder";
  note: string;
};

export type TmMatch = {
  source: string;
  target: string;
  similarity: number;
};

export type TranslatedString = SourceString;

export type QaScores = {
  naturalness: number;
  consistency: number;
  accuracy: number;
  back: number;
  passed: boolean;
};

export type SimulationFrame = {
  locale: string;
  localeNative: string;
  rtl: boolean;
  glossary: GlossaryMatch[];
  tm: TmMatch[];
  translations: TranslatedString[];
  backTranslations: TranslatedString[];
  qa: QaScores;
};

export const sampleSources: { label: string; strings: SourceString[] }[] = [
  {
    label: "Checkout screen (e-commerce)",
    strings: [
      { key: "checkout.title", value: "Review your order" },
      { key: "checkout.button.pay", value: "Pay {amount}" },
      { key: "checkout.shipping.eta", value: "Arrives in 2–3 business days" },
      { key: "checkout.coupon.applied", value: "Coupon applied" },
    ],
  },
  {
    label: "Onboarding (SaaS)",
    strings: [
      { key: "onboard.welcome", value: "Welcome to Clariti" },
      { key: "onboard.cta.start", value: "Set up your first project" },
      { key: "onboard.skip", value: "I'll do this later" },
      { key: "onboard.help", value: "Need a hand? Talk to the team." },
    ],
  },
  {
    label: "Error states (mobile)",
    strings: [
      { key: "err.network.title", value: "We can't reach the network." },
      { key: "err.network.cta", value: "Try again" },
      { key: "err.auth.expired", value: "Your session has expired. Please sign in again." },
      { key: "err.payment.declined", value: "Your card was declined." },
    ],
  },
];

export const availableProviders: { id: string; label: string; note: string }[] = [
  { id: "claude-sonnet-4", label: "claude-sonnet-4", note: "default · best for product UI" },
  { id: "gpt-4-turbo", label: "gpt-4-turbo", note: "fallback · strong on idiom" },
  { id: "deepl/api", label: "deepl/api", note: "plain-text locales (fr, de, es)" },
  { id: "ollama/llama-3.1", label: "ollama/llama-3.1", note: "on-prem · no data egress" },
];

export const availableLocales: { code: string; native: string; rtl?: boolean }[] = [
  { code: "fr-FR", native: "Français" },
  { code: "de-DE", native: "Deutsch" },
  { code: "ja-JP", native: "日本語" },
  { code: "es-ES", native: "Español" },
  { code: "ar-SA", native: "العربية", rtl: true },
];

/**
 * Hand-crafted translations for each (sample source, locale) pair.
 * Keyed by `${sourceLabel} :: ${locale}`.
 */
const TRANSLATIONS: Record<string, { t: Record<string, string>; back: Record<string, string> }> = {
  "Checkout screen (e-commerce) :: fr-FR": {
    t: {
      "checkout.title": "Vérifiez votre commande",
      "checkout.button.pay": "Payer {amount}",
      "checkout.shipping.eta": "Livraison sous 2 à 3 jours ouvrés",
      "checkout.coupon.applied": "Coupon appliqué",
    },
    back: {
      "checkout.title": "Review your order",
      "checkout.button.pay": "Pay {amount}",
      "checkout.shipping.eta": "Delivery in 2 to 3 business days",
      "checkout.coupon.applied": "Coupon applied",
    },
  },
  "Checkout screen (e-commerce) :: de-DE": {
    t: {
      "checkout.title": "Bestellung prüfen",
      "checkout.button.pay": "{amount} bezahlen",
      "checkout.shipping.eta": "Lieferung in 2–3 Werktagen",
      "checkout.coupon.applied": "Gutschein angewendet",
    },
    back: {
      "checkout.title": "Review order",
      "checkout.button.pay": "Pay {amount}",
      "checkout.shipping.eta": "Delivery in 2–3 business days",
      "checkout.coupon.applied": "Coupon applied",
    },
  },
  "Checkout screen (e-commerce) :: ja-JP": {
    t: {
      "checkout.title": "ご注文内容のご確認",
      "checkout.button.pay": "{amount} を支払う",
      "checkout.shipping.eta": "2〜3 営業日でお届けします",
      "checkout.coupon.applied": "クーポンを適用しました",
    },
    back: {
      "checkout.title": "Confirm your order details",
      "checkout.button.pay": "Pay {amount}",
      "checkout.shipping.eta": "Will be delivered in 2–3 business days",
      "checkout.coupon.applied": "Coupon was applied",
    },
  },
  "Checkout screen (e-commerce) :: es-ES": {
    t: {
      "checkout.title": "Revisa tu pedido",
      "checkout.button.pay": "Pagar {amount}",
      "checkout.shipping.eta": "Llega en 2–3 días laborables",
      "checkout.coupon.applied": "Cupón aplicado",
    },
    back: {
      "checkout.title": "Review your order",
      "checkout.button.pay": "Pay {amount}",
      "checkout.shipping.eta": "Arrives in 2–3 business days",
      "checkout.coupon.applied": "Coupon applied",
    },
  },
  "Checkout screen (e-commerce) :: ar-SA": {
    t: {
      "checkout.title": "راجع طلبك",
      "checkout.button.pay": "ادفع {amount}",
      "checkout.shipping.eta": "يصل خلال 2–3 أيام عمل",
      "checkout.coupon.applied": "تم تطبيق القسيمة",
    },
    back: {
      "checkout.title": "Review your order",
      "checkout.button.pay": "Pay {amount}",
      "checkout.shipping.eta": "Arrives within 2–3 business days",
      "checkout.coupon.applied": "Coupon was applied",
    },
  },

  "Onboarding (SaaS) :: fr-FR": {
    t: {
      "onboard.welcome": "Bienvenue sur Clariti",
      "onboard.cta.start": "Configurez votre premier projet",
      "onboard.skip": "Je le ferai plus tard",
      "onboard.help": "Besoin d'aide ? Contactez l'équipe.",
    },
    back: {
      "onboard.welcome": "Welcome to Clariti",
      "onboard.cta.start": "Set up your first project",
      "onboard.skip": "I'll do it later",
      "onboard.help": "Need help? Contact the team.",
    },
  },
  "Onboarding (SaaS) :: de-DE": {
    t: {
      "onboard.welcome": "Willkommen bei Clariti",
      "onboard.cta.start": "Richten Sie Ihr erstes Projekt ein",
      "onboard.skip": "Mache ich später",
      "onboard.help": "Brauchen Sie Hilfe? Sprechen Sie mit dem Team.",
    },
    back: {
      "onboard.welcome": "Welcome to Clariti",
      "onboard.cta.start": "Set up your first project",
      "onboard.skip": "I'll do it later",
      "onboard.help": "Do you need help? Talk to the team.",
    },
  },
  "Onboarding (SaaS) :: ja-JP": {
    t: {
      "onboard.welcome": "Clariti へようこそ",
      "onboard.cta.start": "最初のプロジェクトを設定する",
      "onboard.skip": "後で行う",
      "onboard.help": "お困りですか？チームにご相談ください。",
    },
    back: {
      "onboard.welcome": "Welcome to Clariti",
      "onboard.cta.start": "Set up your first project",
      "onboard.skip": "Do it later",
      "onboard.help": "Are you in trouble? Please consult the team.",
    },
  },
  "Onboarding (SaaS) :: es-ES": {
    t: {
      "onboard.welcome": "Te damos la bienvenida a Clariti",
      "onboard.cta.start": "Configura tu primer proyecto",
      "onboard.skip": "Lo haré más tarde",
      "onboard.help": "¿Necesitas ayuda? Habla con el equipo.",
    },
    back: {
      "onboard.welcome": "Welcome to Clariti",
      "onboard.cta.start": "Set up your first project",
      "onboard.skip": "I'll do it later",
      "onboard.help": "Need help? Talk to the team.",
    },
  },
  "Onboarding (SaaS) :: ar-SA": {
    t: {
      "onboard.welcome": "مرحبًا بك في Clariti",
      "onboard.cta.start": "قم بإعداد مشروعك الأول",
      "onboard.skip": "سأقوم بذلك لاحقًا",
      "onboard.help": "هل تحتاج إلى مساعدة؟ تحدث مع الفريق.",
    },
    back: {
      "onboard.welcome": "Welcome to Clariti",
      "onboard.cta.start": "Set up your first project",
      "onboard.skip": "I will do this later",
      "onboard.help": "Do you need help? Talk with the team.",
    },
  },

  "Error states (mobile) :: fr-FR": {
    t: {
      "err.network.title": "Impossible de joindre le réseau.",
      "err.network.cta": "Réessayer",
      "err.auth.expired": "Votre session a expiré. Veuillez vous reconnecter.",
      "err.payment.declined": "Votre carte a été refusée.",
    },
    back: {
      "err.network.title": "Unable to reach the network.",
      "err.network.cta": "Try again",
      "err.auth.expired": "Your session has expired. Please sign in again.",
      "err.payment.declined": "Your card was declined.",
    },
  },
  "Error states (mobile) :: de-DE": {
    t: {
      "err.network.title": "Wir können das Netzwerk nicht erreichen.",
      "err.network.cta": "Erneut versuchen",
      "err.auth.expired": "Ihre Sitzung ist abgelaufen. Bitte erneut anmelden.",
      "err.payment.declined": "Ihre Karte wurde abgelehnt.",
    },
    back: {
      "err.network.title": "We cannot reach the network.",
      "err.network.cta": "Try again",
      "err.auth.expired": "Your session has expired. Please sign in again.",
      "err.payment.declined": "Your card was declined.",
    },
  },
  "Error states (mobile) :: ja-JP": {
    t: {
      "err.network.title": "ネットワークに接続できません。",
      "err.network.cta": "再試行",
      "err.auth.expired": "セッションの有効期限が切れました。もう一度ログインしてください。",
      "err.payment.declined": "カードが拒否されました。",
    },
    back: {
      "err.network.title": "Cannot connect to the network.",
      "err.network.cta": "Retry",
      "err.auth.expired": "Your session has expired. Please log in again.",
      "err.payment.declined": "Card was declined.",
    },
  },
  "Error states (mobile) :: es-ES": {
    t: {
      "err.network.title": "No podemos conectar con la red.",
      "err.network.cta": "Reintentar",
      "err.auth.expired": "Tu sesión ha caducado. Vuelve a iniciar sesión.",
      "err.payment.declined": "Tu tarjeta ha sido rechazada.",
    },
    back: {
      "err.network.title": "We can't connect to the network.",
      "err.network.cta": "Retry",
      "err.auth.expired": "Your session has expired. Sign in again.",
      "err.payment.declined": "Your card has been declined.",
    },
  },
  "Error states (mobile) :: ar-SA": {
    t: {
      "err.network.title": "تعذّر الوصول إلى الشبكة.",
      "err.network.cta": "أعد المحاولة",
      "err.auth.expired": "انتهت جلستك. يرجى تسجيل الدخول مرة أخرى.",
      "err.payment.declined": "تم رفض بطاقتك.",
    },
    back: {
      "err.network.title": "Could not reach the network.",
      "err.network.cta": "Retry",
      "err.auth.expired": "Your session has ended. Please sign in again.",
      "err.payment.declined": "Your card was declined.",
    },
  },
};

const GLOSSARY_BY_LABEL: Record<string, GlossaryMatch[]> = {
  "Checkout screen (e-commerce)": [
    { term: "Clariti", rule: "lock", note: "Brand term — never translate." },
    { term: "{amount}", rule: "placeholder", note: "ICU placeholder — preserve literally." },
    { term: "coupon", rule: "keep", note: "Project glossary: keep as is in marketing copy; otherwise localise." },
  ],
  "Onboarding (SaaS)": [
    { term: "Clariti", rule: "lock", note: "Brand term — never translate." },
    { term: "project", rule: "keep", note: "Translate locally; do not capitalise." },
  ],
  "Error states (mobile)": [
    { term: "{0}", rule: "placeholder", note: "ICU placeholder — preserve." },
    { term: "card", rule: "keep", note: "Use the locale's standard for 'bank card'." },
  ],
};

const TM_BY_LABEL: Record<string, TmMatch[]> = {
  "Checkout screen (e-commerce)": [
    { source: "Add to cart", target: "Ajouter au panier", similarity: 0.91 },
    { source: "Order summary", target: "Récapitulatif de la commande", similarity: 0.88 },
    { source: "Pay with card", target: "Payer par carte", similarity: 0.84 },
  ],
  "Onboarding (SaaS)": [
    { source: "Welcome aboard", target: "Bienvenue à bord", similarity: 0.87 },
    { source: "Create your first project", target: "Créez votre premier projet", similarity: 0.93 },
  ],
  "Error states (mobile)": [
    { source: "Connection lost", target: "Connexion perdue", similarity: 0.85 },
    { source: "Try again later", target: "Réessayez plus tard", similarity: 0.81 },
  ],
};

const QA_BY_LOCALE: Record<string, QaScores> = {
  "fr-FR": { naturalness: 4.8, consistency: 4.9, accuracy: 4.7, back: 0.96, passed: true },
  "de-DE": { naturalness: 4.6, consistency: 4.9, accuracy: 4.8, back: 0.95, passed: true },
  "ja-JP": { naturalness: 4.7, consistency: 4.8, accuracy: 4.9, back: 0.93, passed: true },
  "es-ES": { naturalness: 4.7, consistency: 4.8, accuracy: 4.8, back: 0.95, passed: true },
  "ar-SA": { naturalness: 4.6, consistency: 4.7, accuracy: 4.8, back: 0.94, passed: true },
};

export function buildFrame(
  sourceLabel: string,
  sourceStrings: SourceString[],
  locale: string,
): SimulationFrame | null {
  const key = `${sourceLabel} :: ${locale}`;
  const pair = TRANSLATIONS[key];
  if (!pair) return null;

  const localeMeta = availableLocales.find((l) => l.code === locale)!;

  return {
    locale,
    localeNative: localeMeta.native,
    rtl: !!localeMeta.rtl,
    glossary: GLOSSARY_BY_LABEL[sourceLabel] ?? [],
    tm: TM_BY_LABEL[sourceLabel] ?? [],
    translations: sourceStrings.map((s) => ({ key: s.key, value: pair.t[s.key] ?? s.value })),
    backTranslations: sourceStrings.map((s) => ({ key: s.key, value: pair.back[s.key] ?? s.value })),
    qa: QA_BY_LOCALE[locale],
  };
}

export function renderPrompt({
  sourceLabel,
  sourceStrings,
  locale,
  provider,
  glossary,
  tm,
}: {
  sourceLabel: string;
  sourceStrings: SourceString[];
  locale: string;
  provider: string;
  glossary: GlossaryMatch[];
  tm: TmMatch[];
}) {
  const formality = locale === "ja-JP" ? "polite (です/ます)" : locale === "de-DE" ? "Sie (formal)" : "neutral";
  return (
    `# clariti.translate_v3 — prompt template\n` +
    `provider: ${provider}\n` +
    `target_locale: ${locale}\n` +
    `formality: ${formality}\n` +
    `\n[brand voice]\n` +
    `- Concise. Direct. No marketing fluff.\n` +
    `\n[glossary — terminology locks]\n` +
    glossary.map((g) => `- ${g.term} → ${g.rule === "lock" ? "DO NOT TRANSLATE" : g.rule === "placeholder" ? "PRESERVE LITERALLY" : "translate per locale norms"}`).join("\n") +
    `\n\n[translation memory — top-3 nearest by cosine, project-scoped]\n` +
    tm.map((t) => `- "${t.source}" → "${t.target}"  (sim ${t.similarity.toFixed(2)})`).join("\n") +
    `\n\n[context]\n` +
    `screen: ${sourceLabel}\n` +
    `\n[strings to translate — emit JSON, keys preserved]\n` +
    sourceStrings.map((s) => `  ${s.key}: ${JSON.stringify(s.value)}`).join("\n")
  );
}
