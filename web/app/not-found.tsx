import Link from "next/link";

import { SearchBar } from "@/components/SearchBar";

export default function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="mt-2 text-ink-soft">Try searching for the part number.</p>
      <div className="mx-auto mt-6 max-w-xl"><SearchBar /></div>
      <p className="mt-6"><Link className="text-accent" href="/">Home</Link></p>
    </div>
  );
}
