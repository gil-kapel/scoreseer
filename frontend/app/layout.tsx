import type { Metadata } from "next";

import { HeaderStrip } from "@/components/header-strip";
import { MobileNav, Sidebar } from "@/components/sidebar";
import { api, safe } from "@/lib/api";

import "./globals.css";

export const metadata: Metadata = {
  title: "ScoreSeer",
  description: "World Cup 2026 match result estimator — accuracy lab",
};

// Set the theme from localStorage before first paint to avoid a flash.
const THEME_INIT = `(function(){try{var t=localStorage.getItem('scoreseer-theme');if(t==='light'||t==='dark'){document.documentElement.dataset.theme=t}}catch(e){}})();`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const { data: metrics } = await safe(api.metrics());
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>
        <div className="flex min-h-screen">
          <Sidebar />
          <div className="flex flex-1 flex-col overflow-hidden">
            <HeaderStrip metrics={metrics} />
            {/* pb-24 on mobile leaves room for the fixed bottom nav */}
            <main className="flex-1 overflow-auto p-4 pb-24 md:p-6 md:pb-6">{children}</main>
          </div>
        </div>
        <MobileNav />
      </body>
    </html>
  );
}
