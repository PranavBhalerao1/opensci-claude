import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import NewsSubscribe from "@/components/NewsSubscribe";
import { SiteFooter, SiteHeader } from "@/components/Site";
import { formatNewsDate, NEWS, newsPost } from "@/lib/news";

export function generateStaticParams() {
  return NEWS.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: PageProps<"/news/[slug]">): Promise<Metadata> {
  const post = newsPost((await params).slug);
  if (!post) return {};
  return { title: post.title, description: post.summary, alternates: { canonical: `/news/${post.slug}` } };
}

export default async function NewsArticle({ params }: PageProps<"/news/[slug]">) {
  const post = newsPost((await params).slug);
  if (!post) notFound();

  return (
    <div className="flex min-h-full flex-col bg-paper text-ink">
      <SiteHeader />
      <main className="mx-auto w-full max-w-2xl flex-1 px-6 pb-32 pt-20">
        <Link href="/news" className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint hover:text-ink">
          ← News
        </Link>
        <article className="mt-12">
          <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">
            {formatNewsDate(post.date)} · {post.time}
          </div>
          <h1 className="mt-4 font-serif text-[48px] leading-[1.08] tracking-tight max-sm:text-[36px]">{post.title}</h1>
          <div className="mt-12 space-y-7 font-serif text-[20px] leading-[1.7] max-sm:text-[18px]">
            {post.body.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
          <p className="mt-14 font-serif text-[20px] italic text-muted">The OpenScientist team</p>
        </article>
        <div className="mt-20">
          <NewsSubscribe />
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
