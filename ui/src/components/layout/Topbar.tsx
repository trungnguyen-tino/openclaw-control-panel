import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, LogOut, Menu } from "lucide-react";
import { StatPill } from "@/components/ui/StatPill";
import { useSystemInfo } from "@/hooks/useSystemInfo";

interface TopbarProps {
  pageLabel: string;
  username?: string;
  onLogout: () => void;
  onMenuClick?: () => void;
}

export function Topbar({ pageLabel, username = "admin", onLogout, onMenuClick }: TopbarProps) {
  const sys = useSystemInfo();
  const initials = username.slice(0, 2).toUpperCase();

  return (
    <header className="h-16 bg-white border-b border-slate-200 sticky top-0 z-10 flex items-center px-4 md:px-6 gap-4">
      {/* Mobile hamburger */}
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Toggle menu"
        className="md:hidden size-9 rounded-lg hover:bg-slate-100 flex items-center justify-center"
      >
        <Menu className="w-5 h-5 text-slate-600" />
      </button>

      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-[13px] text-slate-400 whitespace-nowrap min-w-0">
        <span className="hidden sm:inline">Bảng điều khiển</span>
        <span className="hidden sm:inline opacity-50">/</span>
        <span className="text-ink font-semibold truncate">{pageLabel}</span>
      </div>

      <div className="flex-1" />

      {/* System stat pills (desktop only) */}
      <div className="hidden lg:flex items-center gap-2.5">
        <StatPill label="Dịch vụ" value="Running" dot="emerald" />
        <StatPill label="CPU" value={sys.data?.cpuPct != null ? `${sys.data.cpuPct}%` : "—"} />
        <StatPill label="RAM" value={sys.data?.memPct != null ? `${sys.data.memPct}%` : "—"} />
        <StatPill label="Disk" value={sys.data?.diskPct != null ? `${sys.data.diskPct}%` : "—"} />
      </div>

      {/* User dropdown */}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            aria-label="Mở menu người dùng"
            className="flex items-center gap-2 h-9 pl-1 pr-2 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand-500 to-cyan-400 text-white grid place-items-center font-bold text-[11px]">
              {initials}
            </div>
            <span className="hidden sm:inline text-[13px] font-semibold text-ink">{username}</span>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={6}
            className="z-50 min-w-[180px] rounded-lg border border-slate-200 bg-white p-1 shadow-lg"
          >
            <div className="px-2 py-1.5 border-b border-slate-100 mb-1">
              <div className="text-[13px] font-semibold text-ink truncate">{username}</div>
              <div className="text-[11px] text-slate-400 font-mono truncate">admin</div>
            </div>
            <DropdownMenu.Item
              onSelect={onLogout}
              className="flex items-center gap-2 px-2 py-1.5 rounded-md text-[13px] text-slate-700 hover:bg-slate-50 focus:bg-slate-50 outline-none cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              Đăng xuất
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </header>
  );
}
