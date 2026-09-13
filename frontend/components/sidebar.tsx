"use client";
import React, { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, FolderOpen, FileText, Settings,
  FlaskConical, Activity, ChevronLeft, ChevronRight,
  BookOpen, Moon, Sun, Library, Wand2,
  Scale, SplitSquareHorizontal, BarChart3, ShieldCheck,
  Eye, Database,
  Bot, RefreshCw, Brain, Swords, Gauge, Landmark, Coins, FileCode2, Plug, Menu, X, Rocket, Target, LifeBuoy
} from "lucide-react";
import { useTheme } from "@/components/theme-provider";

/**
 * Two families of navigation live here, and the split is deliberate.
 *
 * Every data-bearing page uses the supported file-backed `/v1` surface: the same engine
 * the CLI and MCP server drive. Groups are now product workflows, not API boundaries.
 */
const NAV_GROUPS = [
  {
    label: "Workspace",
    items: [
      { href: "/",       icon: LayoutDashboard, label: "Dashboard" },
      { href: "/projects",icon: FolderOpen,     label: "Projects" },
      { href: "/prompts", icon: FileText,        label: "All Prompts" },
    ]
  },
  {
    label: "Create",
    items: [
      { href: "/library", icon: Library,  label: "Starter Library" },
      { href: "/studio",  icon: Wand2,    label: "Prompt Studio" },
    ]
  },
  {
    label: "Intelligence",
    items: [
      { href: "/compare",   icon: Scale,               label: "Model Comparator" },
      { href: "/abtests",   icon: SplitSquareHorizontal,label: "A/B Testing" },
      { href: "/guardrails",icon: ShieldCheck,          label: "Guardrails" },
    ]
  },
  {
    label: "Agents",
    items: [
      { href: "/agents/harnesses", icon: Bot,       label: "Harnesses" },
      { href: "/agents/loops",     icon: RefreshCw, label: "Loops" },
      { href: "/agents/memory",    icon: Brain,     label: "Memory" },
      { href: "/context/tokens",   icon: Coins,     label: "Token Economy" },
    ]
  },
  {
    label: "Connect",
    items: [
      { href: "/integrations", icon: Plug, label: "Integrations" },
    ]
  },
  {
    label: "Assurance",
    items: [
      { href: "/benchmark",            icon: Target,   label: "Benchmark" },
      { href: "/security/redteam",     icon: Swords,   label: "Red Team" },
      { href: "/quality/calibration",  icon: Gauge,    label: "Judge Calibration" },
      { href: "/governance",           icon: Landmark, label: "Governance" },
    ]
  },
  {
    label: "Ops",
    items: [
      { href: "/delivery",        icon: Rocket,       label: "Delivery Status" },
      { href: "/datasets",        icon: FlaskConical, label: "Eval Lab" },
      { href: "/analytics",       icon: BarChart3,    label: "Analytics" },
      { href: "/observability",   icon: Activity,     label: "Observability" },
      { href: "/spec",            icon: FileCode2,    label: "Spec & Plugins" },
      { href: "/settings/models", icon: Database,     label: "Global Models" },
      { href: "/settings",        icon: Settings,     label: "Settings" },
    ]
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <>
      <button
        type="button"
        onClick={() => setMobileOpen(open => !open)}
        className="fixed left-3 top-2.5 z-50 flex h-8 w-8 items-center justify-center rounded-lg border bg-card text-foreground shadow-sm md:hidden"
        aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={mobileOpen}
        aria-controls="primary-navigation"
      >
        {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
      </button>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside
        id="primary-navigation"
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r bg-card shadow-xl backdrop-blur-sm transition-transform duration-200 md:visible md:relative md:z-auto md:translate-x-0 md:shadow-none ${
          mobileOpen ? "visible translate-x-0" : "invisible -translate-x-full"
        } ${collapsed ? "md:w-16" : "md:w-56"} shrink-0`}
      >
      {/* Logo */}
      <div className={`flex items-center gap-2.5 px-4 py-5 border-b ${collapsed ? "justify-center px-2" : ""}`}>
        <Image src="/brand/logo-mark-v2.svg" alt="" width={32} height={32} className="h-8 w-8 shrink-0 rounded-lg" />
        {!collapsed && (
          <div className="min-w-0">
            <p className="text-sm font-bold leading-tight truncate">Assay</p>
            <p className="text-[10px] text-muted-foreground">v1.0.0 · Assurance as code</p>
          </div>
        )}
      </div>

      {/* Nav groups */}
      <nav aria-label="Primary navigation" className="flex-1 p-2 overflow-y-auto space-y-3">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            {!collapsed && (
              <p className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground px-3 mb-1">
                {group.label}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map(({ href, icon: Icon, label }) => {
                const active = isActive(href);
                return (
                  <Link key={href} href={href}
                    onClick={() => setMobileOpen(false)}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all group ${
                      active
                        ? "bg-primary/15 text-blue-300"
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                    } ${collapsed ? "justify-center px-2" : ""}`}
                    title={collapsed ? label : undefined}>
                    <Icon className={`h-4 w-4 shrink-0 transition-transform ${active ? "" : "group-hover:scale-110"}`} />
                    {!collapsed && <span className="truncate text-xs">{label}</span>}
                    {active && !collapsed && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className={`p-2 border-t space-y-0.5 ${collapsed ? "" : ""}`}>
        <Link href="/help"
          className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors ${collapsed ? "justify-center px-2" : ""}`}
          title={collapsed ? "Help Centre" : undefined}>
          <LifeBuoy className="h-4 w-4 shrink-0" />
          {!collapsed && <span>Help Centre</span>}
        </Link>

        {/* Docs link */}
        <a href="/api/assay/v1" target="_blank" rel="noopener noreferrer"
          className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors ${collapsed ? "justify-center px-2" : ""}`}
          title={collapsed ? "API Docs" : undefined}>
          <BookOpen className="h-4 w-4 shrink-0" />
          {!collapsed && <span>API root</span>}
        </a>

        {/* Theme toggle */}
        <button onClick={toggleTheme}
          aria-label={theme === "light" ? "Switch to dark theme" : theme === "dark" ? "Switch to eye-care theme" : "Switch to light theme"}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors ${collapsed ? "justify-center px-2" : ""}`}
          title={collapsed ? "Toggle theme" : undefined}>
          {theme === "light" ? <Moon className="h-4 w-4 shrink-0" /> : theme === "dark" ? <Eye className="h-4 w-4 shrink-0" /> : <Sun className="h-4 w-4 shrink-0" />}
          {!collapsed && <span>{theme === "light" ? "Dark mode" : theme === "dark" ? "Eye-care mode" : "Light mode"}</span>}
        </button>

        {/* Collapse toggle */}
        <button onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          aria-expanded={!collapsed}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors ${collapsed ? "justify-center px-2" : ""}`}>
          {collapsed ? <ChevronRight className="h-4 w-4 shrink-0" /> : <ChevronLeft className="h-4 w-4 shrink-0" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
      </aside>
    </>
  );
}
