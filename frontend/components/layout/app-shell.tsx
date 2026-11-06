"use client";

import * as React from "react";

import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { getHealth } from "@/lib/api";

interface Connection {
  online: boolean;
  model: string;
  configured: boolean;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const [connection, setConnection] = React.useState<Connection>({
    online: false,
    model: "openai/gpt-oss-120b",
    configured: false,
  });

  const refresh = React.useCallback(async () => {
    try {
      const health = await getHealth();
      setConnection({
        online: health.status === "ok",
        model: health.model,
        configured: health.openrouter_configured,
      });
    } catch {
      setConnection((current) => ({ ...current, online: false }));
    }
  }, []);

  React.useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 20000);
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [refresh]);

  return (
    <div className="min-h-screen bg-background">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        connection={connection}
      />
      <div className="flex min-h-screen flex-col lg:pl-64">
        <Topbar
          onMenuClick={() => setSidebarOpen(true)}
          connection={connection}
        />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
