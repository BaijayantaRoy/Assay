import Client from "./client";

export function generateStaticParams() { return [{ id: ['1'] }]; }

export default function Page(props: { params: Promise<{ id: string[] }> }) {
  return <Client {...props} />;
}
