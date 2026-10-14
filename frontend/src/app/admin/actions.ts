"use server";

import { redirect } from "next/navigation";

import { approve, getAdminEmail, invite, revoke, setCap } from "@/lib/admin";

/**
 * Server Actions for /admin. They are reachable by direct POST, so every one
 * re-checks the admin before touching anything. Each finishes by redirecting back
 * to /admin with a message, which also reloads the lists.
 */

function done(message: string, ok = true): never {
  redirect(`/admin?${ok ? "ok" : "err"}=${encodeURIComponent(message)}`);
}

function readEmail(form: FormData): string {
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) done("Enter a valid email address.", false);
  return email;
}

/** "" → null (no cap / unchanged), "5" or "$5" → 5. */
function readCap(form: FormData): number | null {
  const raw = String(form.get("cap") ?? "").trim().replace(/^\$/, "");
  if (!raw) return null;
  const cap = Number(raw);
  if (!Number.isFinite(cap) || cap < 0) done(`"${raw}" isn't a dollar amount.`, false);
  return cap;
}

async function run(action: () => Promise<string>): Promise<never> {
  if (!(await getAdminEmail())) done("Not allowed.", false);
  let message: string;
  try {
    message = await action();
  } catch (e) {
    done(e instanceof Error ? e.message : "Something went wrong.", false);
  }
  done(message);
}

export async function inviteAction(form: FormData) {
  const email = readEmail(form);
  const cap = readCap(form);
  await run(() => invite(email, cap));
}

export async function approveAction(form: FormData) {
  const email = readEmail(form);
  const cap = readCap(form);
  await run(() => approve(email, cap));
}

export async function setCapAction(form: FormData) {
  const email = readEmail(form);
  const cap = readCap(form);
  await run(() => setCap(email, cap));
}

export async function revokeAction(form: FormData) {
  const email = readEmail(form);
  await run(() => revoke(email));
}
