"use client";

import {
  BarChart3,
  Briefcase,
  History,
  LayoutDashboard,
  Library,
  MessageSquare,
  Settings,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

export const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/plan", label: "Business Plan", icon: Briefcase },
  { href: "/chat", label: "AI Chat", icon: MessageSquare },
  { href: "/documents", label: "Knowledge Base", icon: Library },
  { href: "/upload", label: "Upload Documents", icon: UploadCloud },
  { href: "/history", label: "Conversations", icon: History },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  connection?: { online: boolean; model: string; configured: boolean };
}

export function Sidebar({ open, onClose, connection }: SidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-navy-950/50 backdrop-blur-sm lg:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border bg-card transition-transform duration-300 lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-border px-5">
          <Link href="/dashboard" className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-accent text-white shadow-sm">
              <Sparkles className="h-4.5 w-4.5" />
            </span>
            <span className="flex flex-col leading-tight">
              <span className="text-sm font-semibold">RAGify AI</span>
              <span className="text-[11px] text-muted-foreground">
                Agentic RAG
              </span>
            </span>
          </Link>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-secondary lg:hidden"
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {NAV_ITEMS.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                className={cn(
                  "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                  active
                    ? "bg-gradient-to-r from-primary/10 to-accent/10 text-primary"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                )}
              >
                <Icon
                  className={cn(
                    "h-4 w-4 transition-transform group-hover:scale-110",
                    active && "text-primary",
                  )}
                />
                {item.label}
                {active && (
                  <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border p-4">
          <div className="rounded-lg border border-border bg-secondary/40 p-3">
            <div className="flex items-center gap-2 text-xs font-medium">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  connection?.online ? "bg-emerald-500" : "bg-destructive",
                )}
              />
              {connection?.online ? "Backend online" : "Backend offline"}
            </div>
            <p className="mt-1.5 truncate text-[11px] text-muted-foreground">
              {connection?.configured
                ? connection?.model || "Model ready"
                : "OpenRouter key missing"}
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
