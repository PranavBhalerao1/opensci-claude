import Workspace from "@/components/Workspace";

export default async function ProjectPage({ params }: PageProps<"/p/[id]">) {
  const { id } = await params;
  return <Workspace projectId={id} />;
}
