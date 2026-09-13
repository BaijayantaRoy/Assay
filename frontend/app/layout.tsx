import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/sidebar";
import TopBar from "@/components/topbar";
import { ThemeProvider } from "@/components/theme-provider";
import { ToastProvider } from "@/components/toast-provider";

export const metadata: Metadata = {
  title: "Assay — Prompt & Agent Workbench",
  description: "Open, git-native engine for writing, running and proving out LLM prompts and agents: harnesses, verified loops, memory, red-teaming, judge calibration and governance evidence.",
  keywords: ["prompt engineering", "AI", "LLM", "prompt management", "open source"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          <ToastProvider>
            <a
              href="#main-content"
              className="fixed left-3 top-3 z-[100] -translate-y-20 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-lg transition-transform focus:translate-y-0 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            >
              Skip to main content
            </a>
            <div className="flex min-h-screen min-w-0">
              <Sidebar />
              <main id="main-content" tabIndex={-1} className="min-w-0 flex-1 overflow-auto flex flex-col">
                <TopBar />
                <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 w-full">
                  {children}
                </div>
              </main>
            </div>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
