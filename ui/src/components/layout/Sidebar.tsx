import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  MessageSquare,
  Globe,
  Cpu,
  Users,
  Plug,
  ArrowUpCircle,
  ScrollText,
  Power,
  Terminal as TerminalIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { IctsaigonLogo } from "@/components/ui/IctsaigonLogo";
import { ComponentType } from "react";

interface NavItemDef {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  end?: boolean;
}

// Sectioned per v2 design: Tổng quan / Vận hành / Hệ thống.
const NAV_OVERVIEW: NavItemDef[] = [
  { to: "/", label: "Thông tin dịch vụ", icon: LayoutDashboard, end: true },
];
const NAV_OPS: NavItemDef[] = [
  { to: "/chat", label: "Chat AI", icon: MessageSquare },
  { to: "/domain", label: "Tên miền & SSL", icon: Globe },
  { to: "/ai-config", label: "Cấu hình AI", icon: Cpu },
  { to: "/multi-agent", label: "Multi-Agent", icon: Users },
  { to: "/channels", label: "Kênh & Pairing", icon: Plug },
];
const NAV_SYSTEM: NavItemDef[] = [
  { to: "/version", label: "Phiên bản & Nâng cấp", icon: ArrowUpCircle },
  { to: "/logs", label: "Nhật ký", icon: ScrollText },
  { to: "/control", label: "Điều khiển dịch vụ", icon: Power },
  { to: "/terminal", label: "Terminal", icon: TerminalIcon },
];

interface SidebarProps {
  onItemClick?: () => void;
}

export function Sidebar({ onItemClick }: SidebarProps) {
  return (
    <aside className="w-[260px] shrink-0 bg-white border-r border-slate-200 flex flex-col h-full">
      {/* Brand */}
      <div className="px-4 py-4 border-b border-slate-200 flex items-center gap-3">
        <IctsaigonLogo size={28} full />
        <div className="ml-auto text-right leading-tight whitespace-nowrap">
          <div className="text-[11.5px] font-bold text-ink">Opencrawl</div>
          <div className="text-[10px] text-slate-400 font-mono">Panel v1.1.4</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        <SectionLabel>Tổng quan</SectionLabel>
        {NAV_OVERVIEW.map((n) => (
          <NavItem key={n.to} item={n} onClick={onItemClick} />
        ))}
        <SectionLabel className="mt-3">Vận hành</SectionLabel>
        {NAV_OPS.map((n) => (
          <NavItem key={n.to} item={n} onClick={onItemClick} />
        ))}
        <SectionLabel className="mt-3">Hệ thống</SectionLabel>
        {NAV_SYSTEM.map((n) => (
          <NavItem key={n.to} item={n} onClick={onItemClick} />
        ))}
      </nav>
    </aside>
  );
}

function SectionLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "px-3 pb-1 text-[10.5px] font-bold uppercase tracking-widest text-slate-400",
        className,
      )}
    >
      {children}
    </div>
  );
}

function NavItem({ item, onClick }: { item: NavItemDef; onClick?: () => void }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onClick}
      className={({ isActive }) =>
        cn(
          "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] font-medium transition-colors text-left",
          isActive
            ? "bg-gradient-to-b from-brand-50 to-brand-50/40 text-brand-700 font-semibold"
            : "text-slate-600 hover:bg-slate-50 hover:text-ink",
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cn(
              "w-7 h-7 rounded-lg grid place-items-center shrink-0",
              isActive ? "bg-brand-600 text-white shadow-brand" : "bg-slate-100 text-slate-500",
            )}
          >
            <Icon className="w-3.5 h-3.5" />
          </span>
          <span className="truncate flex-1">{item.label}</span>
        </>
      )}
    </NavLink>
  );
}
