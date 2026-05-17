import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  MessageSquare,
  ExternalLink,
  Eye,
  EyeOff,
  Copy,
  RefreshCw,
  Trash2,
  Lock,
  Plus,
  Check,
} from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { MeterCard } from "@/components/ui/MeterCard";
import { useSystemInfo } from "@/hooks/useSystemInfo";

interface InfoResp {
  ok: boolean;
  domain: string;
  ip: string;
  dashboardUrl: string;
  gatewayToken: string;
  mgmtApiKey: string;
  status: string;
  version: string;
  ssl: string;
  dnsStatus: string;
}

interface AuthUserResp {
  ok: boolean;
  configured: boolean;
  username: string;
}

interface ConfigResp {
  ok: boolean;
  provider?: string | null;
  model?: string | null;
}

interface ChannelsResp {
  ok: boolean;
  channels?: Record<
    string,
    { label: string; installed: boolean; accounts: { id: string }[]; origin: string }
  >;
}

export function ServiceInfoPage() {
  const qc = useQueryClient();
  const info = useQuery({ queryKey: ["info"], queryFn: () => api<InfoResp>("/api/info") });
  const user = useQuery({
    queryKey: ["auth-user"],
    queryFn: () => api<AuthUserResp>("/api/auth/user"),
  });
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => api<ConfigResp>("/api/config") });
  const channels = useQuery({
    queryKey: ["channels"],
    queryFn: () => api<ChannelsResp>("/api/channels"),
  });
  const sys = useSystemInfo();

  const [showToken, setShowToken] = useState(false);
  const [copied, setCopied] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const regenerate = useMutation({
    mutationFn: async () => {
      const newToken = Array.from(crypto.getRandomValues(new Uint8Array(32)))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
      return api("/api/env/OPENCLAW_GATEWAY_TOKEN", {
        method: "PUT",
        body: JSON.stringify({ value: newToken }),
      });
    },
    onSuccess: () => {
      setMsg("Đã tạo token mới. Khởi động lại OpenClaw để áp dụng.");
      qc.invalidateQueries({ queryKey: ["info"] });
    },
  });

  const deleteUser = useMutation({
    mutationFn: () => api("/api/auth/user", { method: "DELETE" }),
    onSuccess: () => {
      setMsg("Đã xoá tài khoản đăng nhập.");
      qc.invalidateQueries({ queryKey: ["auth-user"] });
    },
  });

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [createErr, setCreateErr] = useState<string | null>(null);

  // Change password state
  const [changePassOpen, setChangePassOpen] = useState(false);
  const [pwNew, setPwNew] = useState("");
  const [pwConfirm, setPwConfirm] = useState("");
  const [pwErr, setPwErr] = useState<string | null>(null);

  const changePassword = useMutation({
    mutationFn: (body: { password: string }) =>
      api<{ ok: boolean; error?: string }>("/api/auth/change-password", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (resp) => {
      if (resp.ok) {
        setMsg("✓ Đã đổi mật khẩu");
        setChangePassOpen(false);
        setPwNew("");
        setPwConfirm("");
        setPwErr(null);
      } else {
        setPwErr(resp.error ?? "Đổi mật khẩu thất bại");
      }
    },
    onError: (err: unknown) =>
      setPwErr(err instanceof Error ? err.message : String(err)),
  });

  function submitChangePass(e: FormEvent) {
    e.preventDefault();
    setPwErr(null);
    if (pwNew.length < 6) {
      setPwErr("Mật khẩu mới phải ≥ 6 ký tự");
      return;
    }
    if (pwNew !== pwConfirm) {
      setPwErr("Nhập lại mật khẩu không khớp");
      return;
    }
    changePassword.mutate({ password: pwNew });
  }

  const createUser = useMutation({
    mutationFn: (body: { username: string; password: string }) =>
      api<{ ok: boolean; error?: string }>("/api/auth/create-user", jsonBody(body)),
    onSuccess: (resp) => {
      if (resp.ok) {
        setMsg(`Đã tạo tài khoản "${newUsername}".`);
        setNewUsername("");
        setNewPassword("");
        setCreateErr(null);
        qc.invalidateQueries({ queryKey: ["auth-user"] });
      } else {
        setCreateErr(resp.error ?? "Tạo tài khoản thất bại");
      }
    },
    onError: (err: unknown) => {
      setCreateErr(err instanceof Error ? err.message : String(err));
    },
  });

  function submitCreate(e: FormEvent) {
    e.preventDefault();
    setCreateErr(null);
    if (!newUsername.trim() || !newPassword) {
      setCreateErr("Vui lòng nhập tài khoản và mật khẩu");
      return;
    }
    if (newPassword.length < 6) {
      setCreateErr("Mật khẩu phải ≥ 6 ký tự");
      return;
    }
    createUser.mutate({ username: newUsername.trim(), password: newPassword });
  }

  const token = info.data?.gatewayToken ?? "";
  const copyToken = () => {
    navigator.clipboard?.writeText(token);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };
  const uptime = sys.data?.uptime
    ? formatUptime(sys.data.uptime)
    : "—";
  const configuredChannels = Object.entries(channels.data?.channels ?? {})
    .filter(([, c]) => c.installed)
    .map(([id, c]) => ({ id, label: c.label, count: c.accounts.length }));

  return (
    <div className="space-y-5">
      <PageHeader
        title="Thông tin dịch vụ"
        desc="Tổng quan về Opencrawl đang chạy trên VPS của bạn"
        actions={
          <>
            <Button variant="secondary" onClick={() => qc.invalidateQueries()}>
              <RefreshCw className="w-3.5 h-3.5" />
              Làm mới
            </Button>
            <Button asChild>
              <Link to="/chat">
                <MessageSquare className="w-3.5 h-3.5" />
                Mở Chat AI
              </Link>
            </Button>
          </>
        }
      />

      {/* Hero — domain card */}
      <div className="relative overflow-hidden bg-gradient-to-br from-brand-600 via-brand-700 to-brand-900 text-white rounded-xl shadow-brand p-6 md:p-7">
        <div className="hero-pattern absolute inset-0 pointer-events-none" />
        <div className="relative flex flex-wrap items-start gap-6 justify-between">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-widest opacity-80">Tên miền dịch vụ</div>
            <div className="text-2xl md:text-3xl font-extrabold tracking-tight mt-1 font-mono break-all">
              {info.data?.domain ?? "—"}
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-2 mt-4 text-[13px] opacity-95">
              <HeroMeta k="IP công cộng" v={info.data?.ip ?? "—"} />
              <HeroMeta k="Phiên bản" v={info.data?.version ?? "—"} />
              <HeroMeta k="Uptime" v={uptime} />
              <HeroMeta k="SSL" v={info.data?.ssl ?? "—"} />
            </div>
          </div>
          <div className="flex flex-col items-end gap-3 shrink-0">
            <span className="inline-flex items-center gap-2 px-3 py-1.5 bg-white/15 backdrop-blur rounded-full text-sm font-semibold">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse-dot" />
              {info.data?.status === "running" ? "Đang chạy ổn định" : "Không hoạt động"}
            </span>
            <div className="flex gap-2 flex-wrap justify-end">
              <a
                href={`https://${info.data?.domain ?? "localhost"}/gw/#token=${encodeURIComponent(info.data?.gatewayToken ?? "")}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-yellow-400 to-amber-500 hover:from-yellow-300 hover:to-amber-400 text-amber-950 rounded-lg text-sm font-bold shadow-lg shadow-yellow-500/30 ring-1 ring-yellow-300/50 transition-all hover:shadow-yellow-400/50 hover:scale-[1.02] active:scale-[0.98]"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Gateway Control
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* MeterCard row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MeterCard
          title="CPU"
          value={sys.data?.cpuPct != null ? `${sys.data.cpuPct}%` : "—"}
          pct={sys.data?.cpuPct ?? 0}
          right={sys.data?.loadavg?.map((v) => v.toFixed(2)).join(" · ")}
          accent="brand"
        />
        <MeterCard
          title="Bộ nhớ"
          value={
            sys.data?.memUsed && sys.data?.memTotal
              ? `${(sys.data.memUsed / 1e9).toFixed(1)} / ${(sys.data.memTotal / 1e9).toFixed(1)} GB`
              : "—"
          }
          pct={sys.data?.memPct ?? 0}
          right={sys.data?.memPct != null ? `${sys.data.memPct}% đang dùng` : ""}
          accent="cyan"
        />
        <MeterCard
          title="Ổ đĩa /"
          value={
            sys.data?.diskUsed && sys.data?.diskTotal
              ? `${(sys.data.diskUsed / 1e9).toFixed(0)} / ${(sys.data.diskTotal / 1e9).toFixed(0)} GB`
              : "—"
          }
          pct={sys.data?.diskPct ?? 0}
          right={
            sys.data?.diskPct != null && sys.data?.diskTotal && sys.data?.diskUsed
              ? `còn ${((sys.data.diskTotal - sys.data.diskUsed) / 1e9).toFixed(0)} GB`
              : ""
          }
          accent={(sys.data?.diskPct ?? 0) > 85 ? "red" : "emerald"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left col — 2/3 width */}
        <div className="lg:col-span-2 space-y-5">
          {/* Gateway Token */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Gateway Token</CardTitle>
                <CardDescription>
                  Token này cấp quyền cho các thiết bị/agent kết nối tới Opencrawl Gateway.
                </CardDescription>
              </div>
              <Badge tone="info" dot>
                Đang hoạt động
              </Badge>
            </CardHeader>
            <CardContent className="p-5 space-y-3">
              <div className="flex gap-2 items-center">
                <input
                  type={showToken ? "text" : "password"}
                  readOnly
                  value={token}
                  className="flex-1 h-9 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1 text-[13px] font-mono"
                />
                <Button variant="secondary" size="icon" onClick={() => setShowToken((s) => !s)}>
                  {showToken ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </Button>
                <Button variant="secondary" size="icon" onClick={copyToken}>
                  {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                </Button>
                <Button
                  onClick={() => {
                    if (
                      confirm(
                        "Tạo token mới sẽ làm mất kết nối các thiết bị đã pair. Tiếp tục?",
                      )
                    )
                      regenerate.mutate();
                  }}
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Tạo mới
                </Button>
              </div>
              {msg && <p className="text-xs text-slate-500">{msg}</p>}
            </CardContent>
          </Card>

          {/* Provider AI */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Provider AI đang dùng</CardTitle>
                <CardDescription>Mô hình trả lời mặc định cho Opencrawl</CardDescription>
              </div>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/ai-config">Thay đổi →</Link>
              </Button>
            </CardHeader>
            <CardContent className="p-5">
              <div className="flex items-center gap-4">
                <div className="w-11 h-11 rounded-xl bg-brand-900 text-white grid place-items-center font-bold">
                  {cfg.data?.provider?.[0]?.toUpperCase() ?? "?"}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold capitalize">{cfg.data?.provider ?? "Chưa cấu hình"}</div>
                  <div className="text-[13px] text-slate-500 font-mono">
                    {cfg.data?.provider && cfg.data?.model
                      ? `${cfg.data.provider} / ${cfg.data.model}`
                      : "—"}
                  </div>
                </div>
                <Badge tone={cfg.data?.provider ? "success" : "warn"}>
                  <Check className="w-3 h-3" />
                  {cfg.data?.provider ? "Đã cấu hình" : "Chưa cấu hình"}
                </Badge>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right col — 1/3 width */}
        <div className="space-y-5">
          {/* User account */}
          <Card>
            <CardHeader>
              <CardTitle>Tài khoản đăng nhập</CardTitle>
              {user.data?.configured && (
                <Badge tone="success">
                  <Check className="w-3 h-3" />
                  Đã cấu hình
                </Badge>
              )}
            </CardHeader>
            <CardContent className="p-5">
              {user.data?.configured ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-full bg-gradient-to-br from-brand-500 to-cyan-400 text-white grid place-items-center font-bold">
                      {user.data.username.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold">{user.data.username}</div>
                      <div className="text-[12px] text-slate-500 font-mono">@admin</div>
                    </div>
                  </div>
                  <div className="border-t border-slate-200" />
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      className="flex-1"
                      onClick={() => setChangePassOpen((v) => !v)}
                    >
                      <Lock className="w-3.5 h-3.5" />
                      {changePassOpen ? "Đóng" : "Đổi mật khẩu"}
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => {
                        if (confirm(`Xoá tài khoản ${user.data?.username}?`)) deleteUser.mutate();
                      }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                  {changePassOpen && (
                    <form onSubmit={submitChangePass} className="space-y-3 pt-3 border-t border-slate-200">
                      <Field label="Mật khẩu mới (≥6 ký tự)">
                        <Input
                          type="password"
                          value={pwNew}
                          onChange={(e) => setPwNew(e.target.value)}
                          autoComplete="new-password"
                        />
                      </Field>
                      <Field label="Nhập lại mật khẩu">
                        <Input
                          type="password"
                          value={pwConfirm}
                          onChange={(e) => setPwConfirm(e.target.value)}
                          autoComplete="new-password"
                        />
                      </Field>
                      {pwErr && <p className="text-xs text-red-600">{pwErr}</p>}
                      <Button type="submit" disabled={changePassword.isPending} className="w-full">
                        <Lock className="w-3.5 h-3.5" />
                        {changePassword.isPending ? "Đang lưu…" : "Lưu mật khẩu mới"}
                      </Button>
                    </form>
                  )}
                </div>
              ) : (
                <form onSubmit={submitCreate} className="space-y-3">
                  <p className="text-[13px] text-slate-500">
                    Chưa cấu hình. Tạo tài khoản admin để đăng nhập panel.
                  </p>
                  <Field label="Tài khoản">
                    <Input
                      value={newUsername}
                      onChange={(e) => setNewUsername(e.target.value)}
                      placeholder="admin"
                      autoComplete="username"
                    />
                  </Field>
                  <Field label="Mật khẩu (≥6 ký tự)">
                    <Input
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      autoComplete="new-password"
                    />
                  </Field>
                  {createErr && <p className="text-xs text-red-600">{createErr}</p>}
                  <Button type="submit" disabled={createUser.isPending} className="w-full">
                    <Plus className="w-3.5 h-3.5" />
                    {createUser.isPending ? "Đang tạo…" : "Tạo tài khoản"}
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>

          {/* Channel summary */}
          <Card>
            <CardHeader>
              <CardTitle>Kênh kết nối</CardTitle>
              <Badge>{configuredChannels.length} kênh</Badge>
            </CardHeader>
            <CardContent className="p-0">
              {configuredChannels.length === 0 ? (
                <p className="p-5 text-[13px] text-slate-500">
                  Chưa có kênh nào.{" "}
                  <Link to="/channels" className="text-brand-700 font-semibold">
                    Cấu hình →
                  </Link>
                </p>
              ) : (
                configuredChannels.map((c, i) => (
                  <div
                    key={c.id}
                    className={`flex items-center gap-3 px-5 py-3 ${i > 0 ? "border-t border-slate-200" : ""}`}
                  >
                    <div className="w-9 h-9 rounded-lg bg-brand-100 text-brand-700 grid place-items-center font-bold text-sm">
                      {c.label[0]}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-[13.5px]">{c.label}</div>
                      <div className="text-[12px] text-slate-500 font-mono">
                        {c.count} account
                      </div>
                    </div>
                    <Badge tone="success" dot>
                      Online
                    </Badge>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

        </div>
      </div>
    </div>
  );
}

function HeroMeta({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <span>
      <span className="opacity-70">{k} </span>
      <b className="font-semibold">{v}</b>
    </span>
  );
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d} ngày ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}
