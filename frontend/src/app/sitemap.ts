import type { MetadataRoute } from "next";

import { NEWS } from "@/lib/news";
import { SITE_URL } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: SITE_URL, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE_URL}/pricing`, changeFrequency: "monthly", priority: 0.9 },
    { url: `${SITE_URL}/waitlist`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${SITE_URL}/demo`, changeFrequency: "monthly", priority: 0.6 },
    { url: `${SITE_URL}/news`, changeFrequency: "weekly", priority: 0.7 },
    ...NEWS.map((p) => ({ url: `${SITE_URL}/news/${p.slug}`, lastModified: p.date, priority: 0.6 })),
  ];
}
