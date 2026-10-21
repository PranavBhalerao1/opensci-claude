/**
 * Walkthrough accounts (emails listed in WALKTHROUGH_EMAILS, comma-separated) only ever
 * see the scripted product walkthrough at /walkthrough; everyone else is kept out of it.
 * If the variable is unset, no account is a walkthrough account. Server-only.
 */
export const WALKTHROUGH_PATH = "/walkthrough";

export function isWalkthroughAccount(email: string | null | undefined): boolean {
  if (!email) return false;
  return (process.env.WALKTHROUGH_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean)
    .includes(email.toLowerCase());
}
