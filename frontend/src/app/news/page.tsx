import type { Metadata } from "next";
import Link from "next/link";

import NewsSubscribe from "@/components/NewsSubscribe";
import { SiteFooter, SiteHeader } from "@/components/Site";
import { formatNewsDate, NEWS } from "@/lib/news";

export const metadata: Metadata = {
  title: "News",
  description: "Updates from the OpenScientist team.",
  alternates: { canonical: "/news" },
};

export default function NewsPage() {
  return (
    <div className="flex min-h-full flex-col bg-paper text-ink">
      <SiteHeader />
      <main className="mx-auto w-full max-w-2xl flex-1 px-6 pb-32 pt-20">
        <h1 className="font-serif text-[56px] leading-none tracking-tight max-sm:text-[42px]">News</h1>
        <ul className="mt-14 border-t border-rule">
          {NEWS.map((post) => (
            <li key={post.slug} className="border-b border-rule">
              <Link href={`/news/${post.slug}`} className="group block py-9">
                <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">
                  {formatNewsDate(post.date)} · {post.time}
                </div>
                <h2 className="mt-3 font-serif text-[30px] leading-tight group-hover:underline group-hover:underline-offset-4">
                  {post.title}
                </h2>
                <p className="mt-3 font-serif text-[18px] leading-relaxed text-muted">{post.summary}</p>
              </Link>
            </li>
          ))}
        </ul>
        <div className="mt-20">
          <NewsSubscribe />
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
