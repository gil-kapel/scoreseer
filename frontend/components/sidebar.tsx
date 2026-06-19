"use client";

import { BarChart3, CalendarClock, History, Settings2, Swords } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

const NAV = [
  { href: "/", label: "Upcoming", Icon: CalendarClock },
  { href: "/dashboard", label: "Dashboard", Icon: BarChart3 },
  { href: "/estimators", label: "Estimators", Icon: Swords },
  { href: "/history", label: "History", Icon: History },
  { href: "/admin/runs", label: "Admin", Icon: Settings2 },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-border bg-surface">
      <div className="border-b border-border px-4 py-4">
        <div className="text-sm font-semibold text-fg">ScoreSeer</div>
        <div className="text-xs text-fg-muted">World Cup 2026 · accuracy lab</div>
      </div>
      <nav className="flex flex-col gap-0.5 p-2">
        {NAV.map(({ href, label, Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                active
                  ? "bg-surface-2 text-fg"
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
