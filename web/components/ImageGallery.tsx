import Image from "next/image";

type Img = { url: string; width: number | null; height: number | null; attribution: string; license: string };

/**
 * Source-hosted images are hotlinked unoptimised (we never copy them — LEGAL rule 7).
 * Licensed images (manufacturer / CC) go through next/image for AVIF/WebP.
 * Fixed square boxes with explicit dimensions keep CLS at 0.
 */
export function ImageGallery({ images, alt }: { images: Img[]; alt: string }) {
  if (images.length === 0) {
    return <div className="flex aspect-square w-full max-w-sm items-center justify-center rounded-xl border border-line bg-surface-2 text-sm text-ink-soft">No image yet</div>;
  }
  const [main, ...rest] = images;
  if (!main) return null;
  return (
    <div className="w-full max-w-sm">
      <figure className="relative aspect-square overflow-hidden rounded-xl border border-line bg-white">
        <Image src={main.url} alt={alt} fill sizes="(max-width: 640px) 100vw, 384px" priority
          unoptimized={main.license === "source-hosted"} className="object-contain p-4" />
        <figcaption className="absolute bottom-1 right-2 text-[10px] text-slate-500">{main.attribution}</figcaption>
      </figure>
      {rest.length > 0 ? (
        <ul className="mt-2 flex gap-2" aria-label="More images">
          {rest.slice(0, 4).map((img) => (
            <li key={img.url} className="relative h-16 w-16 overflow-hidden rounded-lg border border-line bg-white">
              <Image src={img.url} alt={`${alt} — ${img.attribution}`} fill sizes="64px" loading="lazy"
                unoptimized={img.license === "source-hosted"} className="object-contain p-1" />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
