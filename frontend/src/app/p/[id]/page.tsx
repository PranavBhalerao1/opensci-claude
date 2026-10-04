import BetaGate from "@/components/BetaGate";
import Workspace from "@/components/Workspace";

export default async function ProjectPage({ params }: PageProps<"/p/[id]">) {
  const { id } = await params;
  return (
    <BetaGate>
      <Workspace projectId={id} />
    </BetaGate>
  );
}
