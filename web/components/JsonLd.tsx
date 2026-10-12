import { type JsonLd as Data, jsonLdString } from "@/lib/seo";

export function JsonLd({ data }: { data: Data | null }) {
  if (!data) return null;
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdString(data) }} />;
}
