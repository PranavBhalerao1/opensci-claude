import type { Metadata } from "next";
import { redirect } from "next/navigation";

import Walkthrough from "@/components/walkthrough/Walkthrough";
import { createClient } from "@/lib/supabase/server";
import { isWalkthroughAccount } from "@/lib/walkthrough";

export const metadata: Metadata = { title: "Walkthrough", robots: { index: false, follow: false } };

export default async function WalkthroughPage() {
  // The proxy already routes accounts here; check again so the page never renders for anyone else.
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  if (!isWalkthroughAccount(user.email)) redirect("/");
  return <Walkthrough email={user.email ?? ""} />;
}
