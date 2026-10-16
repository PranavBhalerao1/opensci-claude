"use server";

import { redirect } from "next/navigation";

import { supabaseAdmin } from "@/lib/supabase/service";

const field = (form: FormData, name: string, max: number) => String(form.get(name) ?? "").trim().slice(0, max);

/** The Lab plan's "Contact us" form: stored in lab_inquiries and listed on /admin. */
export async function contactLab(form: FormData) {
  const name = field(form, "name", 200);
  const email = field(form, "email", 254).toLowerCase();
  if (!name || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    redirect("/pricing?lab=invalid#lab");
  }
  let ok = true;
  try {
    await supabaseAdmin("/rest/v1/lab_inquiries", {
      prefer: "return=minimal",
      body: {
        name,
        email,
        organization: field(form, "organization", 200) || null,
        team_size: field(form, "team_size", 40) || null,
        message: field(form, "message", 4000) || null,
      },
    });
  } catch (e) {
    console.error("lab inquiry failed", e);
    ok = false;
  }
  redirect(`/pricing?lab=${ok ? "sent" : "failed"}#lab`);
}
