import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearStoredKey } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";

const PAGE_LABELS: Record<string, string> = {
  "/": "Thông tin dịch vụ",
  "/chat": "Chat AI",
  "/openclaw-chat": "Chat AI",
  "/domain": "Tên miền & SSL",
  "/ai-config": "Cấu hình AI",
  "/multi-agent": "Multi-Agent",
  "/channels": "Kênh & Pairing",
  "/version": "Phiên bản & Nâng cấp",
  "/logs": "Nhật ký",
  "/control": "Điều khiển dịch vụ",
  "/terminal": "Terminal",
};

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Auto-close mobile drawer after route nav.
  useEffect(() => setDrawerOpen(false), [location.pathname]);

  const pageLabel = PAGE_LABELS[location.pathname] ?? "Bảng điều khiển";

  const handleLogout = () => {
    clearStoredKey();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex bg-[#F6F9FD]">
      {/* Mobile backdrop */}
      {drawerOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-black/40"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      {/* Sidebar — sticky desktop / off-canvas mobile */}
      <div
        className={cn(
          "z-40",
          // Desktop: sticky column
          "md:sticky md:top-0 md:h-screen md:flex",
          // Mobile: off-canvas drawer
          "fixed inset-y-0 left-0 transition-transform duration-200",
          drawerOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        <Sidebar onItemClick={() => setDrawerOpen(false)} />
      </div>

      {/* Main */}
      <main className="flex-1 min-w-0 flex flex-col">
        <Topbar
          pageLabel={pageLabel}
          onLogout={handleLogout}
          onMenuClick={() => setDrawerOpen((v) => !v)}
        />
        <div className="flex-1 p-4 md:p-6 max-w-7xl w-full mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
