import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";

/**
 * Lands here after: Google OAuth, the email-confirmation link, and the
 * password-reset link (all use the PKCE `code` exchange). `next` controls
 * where to go afterwards — the reset-password flow points it at
 * /update-password; everything else defaults to the app.
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(error.message)}`);
  }

  return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent("Missing or expired link")}`);
}
