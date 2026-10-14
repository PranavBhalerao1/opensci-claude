#!/usr/bin/env node
// Private-beta admin from the terminal.
//
//   beta pending                    who is waiting for approval
//   beta approve <email> [cap]      let someone in (cap in USD; omit for no change/unlimited)
//   beta invite <email> [cap]       email an invite; they are approved as soon as it is sent
//   beta revoke <email>             take access away
//
// Needs the Supabase project's secret key, read from ~/.openscientist-admin.env:
//   SUPABASE_URL=https://<project>.supabase.co
//   SUPABASE_SECRET_KEY=sb_secret_...      (or the legacy service_role key)
// Keep that file private (chmod 600); never commit it.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const ENV_FILE = join(homedir(), ".openscientist-admin.env");

function loadEnv() {
  const env = { ...process.env };
  try {
    for (const line of readFileSync(ENV_FILE, "utf8").split("\n")) {
      const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);
      if (m) env[m[1]] ??= m[2].replace(/^["']|["']$/g, "");
    }
  } catch {}
  const url = env.SUPABASE_URL?.replace(/\/+$/, "");
  const key = env.SUPABASE_SECRET_KEY ?? env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) fail(`Missing SUPABASE_URL or SUPABASE_SECRET_KEY. Put them in ${ENV_FILE}.`);
  return { url, key };
}

function fail(message) {
  console.error(`✗ ${message}`);
  process.exit(1);
}

const { url, key } = loadEnv();
// New sb_secret_ keys go in `apikey` only; legacy service_role JWTs also go in Authorization.
const headers = { apikey: key, "Content-Type": "application/json" };
if (!key.startsWith("sb_")) headers.Authorization = `Bearer ${key}`;

async function call(path, body) {
  const res = await fetch(`${url}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const msg = data?.message ?? data?.msg ?? data?.error_description ?? data?.error ?? text;
    const err = new Error(msg || `HTTP ${res.status}`);
    err.status = res.status;
    err.code = data?.error_code ?? data?.code;
    throw err;
  }
  return data;
}

const rpc = (fn, args = {}) => call(`/rest/v1/rpc/${fn}`, args);

function parseCap(raw) {
  if (raw === undefined) return null;
  const cap = Number(String(raw).replace(/^\$/, ""));
  if (!Number.isFinite(cap) || cap < 0) fail(`"${raw}" isn't a dollar amount.`);
  return cap;
}

function needEmail(email) {
  if (!email || !email.includes("@")) fail("Give an email address, e.g. beta approve friend@lab.edu");
  return email.trim().toLowerCase();
}

const [cmd, arg1, arg2] = process.argv.slice(2);

try {
  switch (cmd) {
    case "pending": {
      const rows = await rpc("beta_requests");
      if (!rows.length) {
        console.log("No pending requests.");
        break;
      }
      for (const r of rows) {
        const when = new Date(r.signed_up).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
        console.log(`${r.email.padEnd(36)} ${when}${r.confirmed ? "" : "  (email not confirmed)"}`);
      }
      console.log(`\n${rows.length} pending. Approve with: beta approve <email> [cap]`);
      break;
    }
    case "approve": {
      const email = needEmail(arg1);
      console.log(`✓ ${await rpc("approve_beta", { p_email: email, p_cap_usd: parseCap(arg2) })}`);
      break;
    }
    case "invite": {
      const email = needEmail(arg1);
      const cap = parseCap(arg2);
      try {
        await call("/auth/v1/invite", { email });
        console.log(`✓ Invite sent to ${email}`);
      } catch (e) {
        if (e.status !== 422 && e.code !== "email_exists") throw e;
        console.log(`• ${email} already has an account, so no invite was sent. Approving instead.`);
      }
      console.log(`✓ ${await rpc("approve_beta", { p_email: email, p_cap_usd: cap })}`);
      break;
    }
    case "revoke": {
      console.log(`✓ ${await rpc("revoke_beta", { p_email: needEmail(arg1) })}`);
      break;
    }
    default:
      console.log(`Usage:
  beta pending                  who is waiting for approval
  beta approve <email> [cap]    let someone in, optionally with a USD spending cap
  beta invite <email> [cap]     send an invite (approved immediately), optional cap
  beta revoke <email>           take access away`);
      if (cmd && cmd !== "help") process.exit(1);
  }
} catch (e) {
  fail(e.message);
}
