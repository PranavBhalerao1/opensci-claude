import type { Metadata } from "next";

import ReplayPage from "./ReplayPage";

export const metadata: Metadata = { title: "Investigation", robots: { index: false, follow: false } };

export default async function Page({ params, searchParams }: PageProps<"/replay/[slug]">) {
  const { slug } = await params;
  const speed = Number((await searchParams).speed);
  return <ReplayPage slug={slug} speed={speed > 0 ? speed : 1} />;
}
