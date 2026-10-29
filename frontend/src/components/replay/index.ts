import { heatwave } from "./heatwave";
import { proteins } from "./proteins";
import { sleep } from "./sleep";
import type { ReplayData } from "./types";

/** Pre-made runs. "Fascinate me" offers their questions; submitting one exactly replays that run. */
export const REPLAYS: ReplayData[] = [heatwave, proteins, sleep];

const norm = (s: string) => s.trim().replace(/\s+/g, " ").toLowerCase();

export function replayFor(question: string): ReplayData | undefined {
  return REPLAYS.find((r) => norm(r.question) === norm(question));
}

export function replayBySlug(slug: string): ReplayData | undefined {
  return REPLAYS.find((r) => r.slug === slug);
}
