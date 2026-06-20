"use client";

import {
  BarChart3,
  FlaskConical,
  History,
  LayoutGrid,
  Lightbulb,
  Network,
  Settings2,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

const NAV = [
  { href: "/", label: "Dashboard", Icon: LayoutGrid, mobile: true },
  { href: "/forecast", label: "Forecast", Icon: Network, mobile: true },
  { href: "/estimators", label: "Lab", Icon: FlaskConical, mobile: true },
  { href: "/insights", label: "Insights", Icon: Lightbulb, mobile: true },
  { href: "/history", label: "History", Icon: History, mobile: false },
  { href: "/admin/runs", label: "Admin", Icon: Settings2, mobile: true },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-52 shrink-0 flex-col border-r border-border bg-surface md:flex">
      <div className="border-b border-border px-4 py-4">
        <div className="flex items-center gap-2 text-sm font-semibold tracking-wide text-primary text-glow">
          <BarChart3 className="h-4 w-4" />
          ESTIMATOR 2026
        </div>
        <div className="label mt-1.5">World Cup · accuracy lab</div>
      </div>
      <nav className="flex flex-col gap-0.5 p-2">
        {NAV.map(({ href, label, Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-surface-2 font-medium text-primary"
                  : "text-fg-muted hover:bg-surface-2 hover:text-fg",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

/** Fixed bottom tab bar — the mobile replacement for the sidebar (thumb-reachable). */
export function MobileNav() {
  const pathname = usePathname();
  const items = NAV.filter((n) => n.mobile);
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] md:hidden">
      {items.map(({ href, label, Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            aria-label={label}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px]",
              active ? "text-primary" : "text-fg-muted",
            )}
          >
            <Icon className="h-5 w-5" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
