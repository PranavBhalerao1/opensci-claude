/**
 * Walkthrough accounts (the built-in list plus WALKTHROUGH_EMAILS, comma-separated) only
 * ever see the scripted product walkthrough at /walkthrough; everyone else is kept out of
 * it. The backend refuses these accounts on every API route as well. Server-only.
 */
export const WALKTHROUGH_PATH = "/walkthrough";

const BUILT_IN = ["yc@theopenscientist.com"];

export function isWalkthroughAccount(email: string | null | undefined): boolean {
  if (!email) return false;
  return [...BUILT_IN, ...(process.env.WALKTHROUGH_EMAILS ?? "").split(",")]
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean)
    .includes(email.trim().toLowerCase());
}
