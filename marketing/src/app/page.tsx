import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Hero } from "@/components/sections/Hero";
import { LanguageMarquee } from "@/components/sections/LanguageMarquee";
import { Problem } from "@/components/sections/Problem";
import { Pillars } from "@/components/sections/Pillars";
import { Pipeline } from "@/components/sections/Pipeline";
import { Compare } from "@/components/sections/Compare";
import { PlatformsStrip } from "@/components/sections/PlatformsStrip";
import { Install } from "@/components/sections/Install";
import { OpenSource } from "@/components/sections/OpenSource";
import { Faq, FaqJsonLd } from "@/components/sections/Faq";
import { CtaBand } from "@/components/sections/CtaBand";

export default function HomePage() {
  return (
    <>
      <FaqJsonLd />
      <Nav />
      <main>
        <Hero />
        <LanguageMarquee />
        <Problem />
        <Pillars />
        <Pipeline />
        <Compare />
        <PlatformsStrip />
        <Install />
        <OpenSource />
        <Faq />
        <CtaBand />
      </main>
      <Footer />
    </>
  );
}
