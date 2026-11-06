"use client";

import { Menu, Moon, Sun } from "lucide-react";
import { usePathname } from "next/navigation";

import { NAV_ITEMS } from "@/components/layout/sidebar";
import { useTheme } from "@/components/theme-provider";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface TopbarProps {
  onMenuClick: () => void;
  connection: { online: boolean; model: string; configured: boolean };
}

export function Topbar({ onMenuClick, connection }: TopbarProps) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();

  const active =
    NAV_ITEMS.find(
      (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
    ) ?? NAV_ITEMS[0];

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-xl sm:px-6">
      <button
        onClick={onMenuClick}
        className="rounded-lg border border-border p-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground lg:hidden"
        aria-label="Open sidebar"
      >
        <Menu className="h-4 w-4" />
      </button>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">{active.label}</p>
        <p className="hidden truncate text-xs text-muted-foreground sm:block">
          {connection.configured
            ? `Model: ${connection.model}`
            : "OpenRouter API key not configured"}
        </p>
      </div>

      <Badge
        variant={connection.online ? "success" : "danger"}
        className="hidden sm:inline-flex"
      >
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            connection.online ? "bg-emerald-500" : "bg-destructive",
          )}
        />
        {connection.online ? "Connected" : "Offline"}
      </Badge>

      <button
        onClick={toggleTheme}
        className="rounded-lg border border-border p-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        aria-label="Toggle theme"
      >
        {theme === "dark" ? (
          <Sun className="h-4 w-4" />
        ) : (
          <Moon className="h-4 w-4" />
        )}
      </button>
    </header>
  );
}
