import type { MetadataRoute } from "next";
import { competitors } from "@/lib/competitors";
import { site } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${site.url}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${site.url}/playground`, lastModified: now, changeFrequency: "monthly", priority: 0.9 },
    { url: `${site.url}/agents`, lastModified: now, changeFrequency: "weekly", priority: 0.9 },
    { url: `${site.url}/benchmark`, lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${site.url}/pricing`, lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${site.url}/changelog`, lastModified: now, changeFrequency: "weekly", priority: 0.6 },
    ...competitors.map((c) => ({
      url: `${site.url}/compare/${c.slug}`,
      lastModified: now,
      changeFrequency: "monthly" as const,
      priority: 0.7,
    })),
  ];
}
