"use client";

import BetaGate from "@/components/BetaGate";
import { replayBySlug } from "@/components/replay";
import Replay from "@/components/replay/Replay";

export default function ReplayPage({ slug, speed }: { slug: string; speed: number }) {
  const data = replayBySlug(slug);
  if (!data) return <p className="p-10 font-mono text-[13px] text-muted">No such replay.</p>;
  return (
    <BetaGate>
      <Replay data={data} speed={speed} />
    </BetaGate>
  );
}
