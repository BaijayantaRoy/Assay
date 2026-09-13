"use client";

/**
 * The two things every page in this workbench needs and none of them had: a way to see how
 * the whole portal fits together, and a way to ask "what is this page for" without leaving it.
 *
 * Both live here rather than inside individual pages so they are structurally impossible to
 * forget — a new page under `app/` gets them for free from the layout, and the only thing a
 * page owner has to do is add one entry to `PAGE_GUIDES` in `components/v1/guide.tsx`. If they
 * do not, this bar says so out loud ("no guide written yet") instead of quietly hiding the
 * button, because a visible gap gets filled in and an invisible one does not.
 */

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { HelpCircle, LifeBuoy, Map as MapIcon } from "lucide-react";
import { findGuide, PageGuideModal, PortalMapModal } from "@/components/v1/guide";

export default function TopBar() {
  const pathname = usePathname();
  const guide = findGuide(pathname);
  const [showMap, setShowMap] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  return (
    <>
      <div className="sticky top-0 z-30 flex items-center justify-between gap-2 border-b bg-background/85 py-2.5 pl-14 pr-3 sm:px-6 backdrop-blur-sm">
        <p className="min-w-0 truncate text-xs font-medium text-muted-foreground">
          {guide ? guide.title : pathname}
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <Link
            href="/help"
            aria-label="Open Help Centre"
            className="flex items-center gap-1.5 rounded-lg border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-blue-500/60 hover:text-blue-300"
          >
            <LifeBuoy className="h-3.5 w-3.5" />
            <span className="hidden md:inline">Help Centre</span>
          </Link>
          <button
            onClick={() => setShowMap(true)}
            aria-label="Open portal map"
            className="flex items-center gap-1.5 rounded-lg border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-violet-500/60 hover:text-violet-300"
          >
            <MapIcon className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Portal map</span>
          </button>
          <button
            onClick={() => setShowHelp(true)}
            aria-label={guide ? `About ${guide.title}` : "No page guide available"}
            disabled={!guide}
            className="flex items-center gap-1.5 rounded-lg border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-emerald-500/60 hover:text-emerald-300 disabled:cursor-not-allowed disabled:opacity-40"
            title={guide ? undefined : "No guide written yet for this page"}
          >
            <HelpCircle className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{guide ? "About this page" : "No guide yet"}</span>
          </button>
        </div>
      </div>

      {showMap && <PortalMapModal onClose={() => setShowMap(false)} />}
      {showHelp && guide && (
        <PageGuideModal guide={guide} onClose={() => setShowHelp(false)} />
      )}
    </>
  );
}
