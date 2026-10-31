import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { isWalkthroughAccount, WALKTHROUGH_PATH } from "@/lib/walkthrough";

// Pages reachable without a session. Everything else redirects to /login.
// robots.txt, the sitemap and the share image must stay public for search engines.
const PUBLIC_PATHS = [
  "/login", "/signup", "/forgot-password", "/auth", "/welcome", "/waitlist", "/demo", "/pricing", "/news",
  "/robots.txt", "/sitemap.xml", "/opengraph-image",
  "/api/stripe", // Stripe's webhook; it authenticates by signature, not session
];

function isPublic(path: string): boolean {
  return PUBLIC_PATHS.some((p) => path === p || path.startsWith(`${p}/`));
}

/**
 * Refreshes the Supabase session cookie on every request and redirects
 * unauthenticated visitors away from protected pages.
 *
 * This is an optimistic, page-level check only (per Next.js's own guidance —
 * see the "Optimistic checks with Proxy" pattern). The FastAPI backend is the
 * real authorization boundary: it verifies the bearer token and project
 * ownership on every API call, independent of anything decided here.
 */
export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          for (const { name, value } of cookiesToSet) request.cookies.set(name, value);
          response = NextResponse.next({ request });
          for (const { name, value, options } of cookiesToSet) response.cookies.set(name, value, options);
        },
      },
    },
  );

  // getUser() (not getSession()) revalidates the token against Supabase's auth
  // server rather than trusting the cookie as-is.
  const { data: { user } } = await supabase.auth.getUser();
  const path = request.nextUrl.pathname;

  // Signed-out visitors to the homepage see the landing page; the URL stays "/".
  if (!user && path === "/") {
    const url = request.nextUrl.clone();
    url.pathname = "/welcome";
    return NextResponse.rewrite(url);
  }

  if (!user && !isPublic(path)) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(path + request.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }

  // Walkthrough accounts see only the walkthrough (auth links still work, so they can
  // sign in and out); nobody else can open it.
  const inWalkthrough = path === WALKTHROUGH_PATH || path.startsWith(`${WALKTHROUGH_PATH}/`);
  if (user && isWalkthroughAccount(user.email)) {
    if (!inWalkthrough && !path.startsWith("/auth")) {
      const url = request.nextUrl.clone();
      url.pathname = WALKTHROUGH_PATH;
      url.search = "";
      return NextResponse.redirect(url);
    }
  } else if (inWalkthrough) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }

  if (user && (path === "/login" || path === "/signup")) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return response;
}
