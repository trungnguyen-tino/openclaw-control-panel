import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Link2, Check, Trash2 } from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";

interface ProviderRow {
  id: string;
  name: string;
  envKey: string | null;
  oauthOnly: boolean;
  custom?: boolean;
  models: { id: string; name: string }[];
  knownModels: { id: string; name: string }[];
  apiKey: string | null;
  configured: boolean;
}

interface ConfigResp {
  provider: string | null;
  model: string | null;
}

export function AiConfigPage() {
  const qc = useQueryClient();
  const provs = useQuery({
    queryKey: ["providers"],
    queryFn: () => api<{ providers: ProviderRow[] }>("/api/providers"),
  });
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => api<ConfigResp>("/api/config") });

  const [provider, setProvider] = useState("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const saveKey = useMutation({
    mutationFn: () =>
      api("/api/config/api-key", {
        method: "PUT",
        body: JSON.stringify({ provider, apiKey }),
      }),
    onSuccess: () => {
      setApiKey("");
      setMsg("✓ Đã lưu API key");
      qc.invalidateQueries();
    },
  });

  const deleteKey = useMutation({
    mutationFn: (providerId: string) =>
      api("/api/config/api-key", {
        method: "DELETE",
        body: JSON.stringify({ provider: providerId }),
      }),
    onSuccess: (_data, providerId) => {
      setMsg(`✓ Đã xoá API key của ${providerId}`);
      qc.invalidateQueries();
    },
    onError: (err: unknown) =>
      setMsg(err instanceof Error ? `✗ ${err.message}` : `✗ ${String(err)}`),
  });

  const [postSwitchPrompt, setPostSwitchPrompt] = useState(false);

  const switchProvider = useMutation({
    mutationFn: () =>
      api("/api/config/provider", {
        method: "PUT",
        body: JSON.stringify({ provider, model }),
      }),
    onSuccess: () => {
      setMsg(`✓ Đã chuyển sang ${provider}/${model}`);
      setPostSwitchPrompt(true);
      qc.invalidateQueries();
    },
  });

  // Cleanup: delete all existing openclaw sessions so the next chat turn
  // spawns one whose encrypted reasoning items are signed by the *new*
  // provider's key. Avoids `invalid_encrypted_content` from Codex et al.
  const archiveAllSessions = useMutation({
    mutationFn: async () => {
      const resp = await api<{ ok: boolean; sessions: { id: string }[] }>(
        "/api/openclaw/sessions",
      );
      const sessions = resp.sessions ?? [];
      await Promise.all(
        sessions.map((s) =>
          api(`/api/openclaw/sessions/${encodeURIComponent(s.id)}`, { method: "DELETE" }),
        ),
      );
      return sessions.length;
    },
    onSuccess: (n) => {
      setMsg(`✓ Đã archive ${n} session cũ. Chat lần tới sẽ tạo session mới.`);
      setPostSwitchPrompt(false);
    },
    onError: (err: unknown) =>
      setMsg(err instanceof Error ? `✗ ${err.message}` : `✗ ${String(err)}`),
  });

  // OAuth state for the inline paste form (replaces fragile window.prompt).
  const [oauthSession, setOauthSession] = useState<{ sessionId: string; oauthUrl: string } | null>(null);
  const [oauthRedirect, setOauthRedirect] = useState("");
  const [oauthErr, setOauthErr] = useState<string | null>(null);

  const startOauth = useMutation({
    mutationFn: () =>
      api<{ sessionId: string; oauthUrl: string }>("/api/config/chatgpt-oauth/start", jsonBody({})),
    onSuccess: (s) => {
      setOauthErr(null);
      setOauthSession(s);
      setOauthRedirect("");
      window.open(s.oauthUrl, "_blank", "noopener");
    },
    onError: (e: unknown) => setOauthErr(e instanceof Error ? e.message : String(e)),
  });

  const completeOauth = useMutation({
    mutationFn: () =>
      api<{ ok: boolean; email?: string; error?: string }>(
        "/api/config/chatgpt-oauth/complete",
        jsonBody({
          sessionId: oauthSession?.sessionId,
          redirectUrl: oauthRedirect.trim(),
          switchProvider: true,
        }),
      ),
    onSuccess: (r) => {
      if (r.ok) {
        setMsg(`✓ Đã kết nối ChatGPT${r.email ? ` (${r.email})` : ""}`);
        setOauthSession(null);
        setOauthRedirect("");
        setOauthErr(null);
        qc.invalidateQueries();
      } else {
        setOauthErr(r.error ?? "OAuth lỗi không rõ");
      }
    },
    onError: (e: unknown) => setOauthErr(e instanceof Error ? e.message : String(e)),
  });

  const activeProvider = cfg.data?.provider;
  const activeModel = cfg.data?.model;
  const builtinProviders = (provs.data?.providers ?? []).filter((p) => !p.custom);
  const customProviders = (provs.data?.providers ?? []).filter((p) => p.custom);
  const codex = builtinProviders.find((p) => p.id === "openai-codex");

  return (
    <div className="space-y-5">
      <PageHeader
        title="Cấu hình AI Provider"
        desc="Quản lý provider, model và API key cho Opencrawl"
      />

      <Card>
        <CardContent className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider font-semibold">
              Provider hiện tại
            </p>
            <p className="text-base font-bold mt-1 capitalize">
              {activeProvider ?? "Chưa cấu hình"}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider font-semibold">
              Model hiện tại
            </p>
            <p className="text-base font-bold mt-1 font-mono">
              {activeProvider && activeModel ? `${activeProvider}/${activeModel}` : "—"}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Thay đổi Provider & Model</CardTitle>
            <CardDescription>Chọn nhà cung cấp + mô hình mặc định</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium">Provider</label>
              <select
                className="w-full h-9 px-3 border border-slate-200 rounded-lg bg-white text-[13px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value);
                  const p = builtinProviders.find((x) => x.id === e.target.value);
                  setModel(p?.knownModels[0]?.id ?? p?.models[0]?.id ?? "");
                }}
              >
                {[...builtinProviders, ...customProviders].map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.configured ? "✓" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">Model</label>
              <select
                className="w-full h-9 px-3 border border-slate-200 rounded-lg bg-white text-[13px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              >
                {[
                  ...(builtinProviders.find((p) => p.id === provider)?.knownModels ?? []),
                  ...(builtinProviders.find((p) => p.id === provider)?.models ?? []),
                ].map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.id})
                  </option>
                ))}
              </select>
            </div>
          </div>
          <Button onClick={() => switchProvider.mutate()} disabled={!model}>
            Kích hoạt
          </Button>
          {postSwitchPrompt && (
            <div className="mt-4 rounded-md bg-amber-50 border border-amber-300 px-3 py-3 text-[13px] text-amber-900">
              <div className="font-semibold mb-1">⚠ Cần tạo session mới</div>
              <p className="mb-2">
                Sessions cũ chứa reasoning items được encrypt bằng key của provider trước —
                provider mới sẽ <strong>không decrypt được</strong>, mỗi turn sẽ fail với
                <code className="font-mono text-[12px] mx-1">invalid_encrypted_content</code>.
                Archive sessions cũ ngay để tránh lỗi này.
              </p>
              <div className="flex gap-2 flex-wrap">
                <Button
                  size="sm"
                  onClick={() => archiveAllSessions.mutate()}
                  disabled={archiveAllSessions.isPending}
                >
                  {archiveAllSessions.isPending ? "Đang xoá…" : "Archive sessions cũ"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPostSwitchPrompt(false)}>
                  Bỏ qua
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Custom Providers</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-slate-500 mb-2">
            Nhà cung cấp AI tuỳ chỉnh (OpenAI-compatible)
          </p>
          {customProviders.length === 0 ? (
            <p className="text-sm text-slate-500">Chưa có custom provider nào.</p>
          ) : (
            <ul className="text-sm space-y-1">
              {customProviders.map((p) => (
                <li key={p.id} className="font-mono">
                  {p.id}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cập nhật API Key</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium">Provider</label>
            <select
              className="w-full h-9 px-3 border border-slate-200 rounded-lg bg-white text-[13px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              {builtinProviders
                .filter((p) => !p.oauthOnly)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">API Key</label>
            <div className="flex gap-2">
              <Input
                type={showKey ? "text" : "password"}
                placeholder="Nhập API Key mới"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
              <Button variant="secondary" size="icon" onClick={() => setShowKey((s) => !s)} type="button">
                {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              </Button>
            </div>
          </div>
          <Button onClick={() => saveKey.mutate()} disabled={!apiKey}>
            Lưu API Key
          </Button>
          {msg && <p className="text-xs text-slate-500">{msg}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>API Keys đã cấu hình</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {builtinProviders.filter((p) => p.configured).length === 0 ? (
            <p className="text-sm text-slate-500">Chưa có key nào.</p>
          ) : (
            builtinProviders
              .filter((p) => p.configured)
              .map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-3 text-sm py-1">
                  <span className="flex-shrink-0">{p.name}</span>
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-xs text-slate-500 truncate">{p.apiKey}</span>
                    <Button
                      variant="danger"
                      size="sm"
                      disabled={deleteKey.isPending}
                      onClick={() => {
                        if (confirm(`Xoá API key của ${p.name}?`)) deleteKey.mutate(p.id);
                      }}
                      title={`Xoá API key của ${p.name}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              ))
          )}
        </CardContent>
      </Card>

      {codex && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 gap-3 flex-wrap">
            <div>
              <CardTitle>ChatGPT OAuth (OpenAI Codex)</CardTitle>
              <p className="text-xs text-slate-500 mt-1">
                Kết nối tài khoản ChatGPT qua OAuth2 — không cần API key
              </p>
            </div>
            {!oauthSession && (
              <Button onClick={() => startOauth.mutate()} disabled={startOauth.isPending}>
                <Link2 className="w-3.5 h-3.5" />
                {startOauth.isPending ? "Đang mở…" : "Kết nối ChatGPT"}
              </Button>
            )}
            {oauthSession && (
              <Button variant="secondary" size="sm" onClick={() => { setOauthSession(null); setOauthRedirect(""); setOauthErr(null); }}>
                Huỷ
              </Button>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            {!oauthSession && (
              <div className="flex items-center gap-2">
                {codex.configured ? (
                  <Badge tone="success">
                    <Check className="w-3 h-3" /> Đã kết nối
                  </Badge>
                ) : (
                  <p className="text-[13px] text-slate-500">
                    Chưa kết nối. Nhấn "Kết nối ChatGPT" để bắt đầu.
                  </p>
                )}
              </div>
            )}
            {oauthSession && (
              <div className="space-y-3">
                <div className="rounded-md border border-border bg-muted/40 p-3 space-y-2 text-sm">
                  <p className="font-medium">1. Đăng nhập ChatGPT trong tab mới</p>
                  <p className="text-xs text-slate-500">
                    Nếu tab không tự mở, dán URL này vào trình duyệt:
                  </p>
                  <code className="block break-all text-[11px] bg-background p-2 rounded border border-border">
                    {oauthSession.oauthUrl}
                  </code>
                </div>
                <div className="rounded-md border border-border bg-muted/40 p-3 space-y-2 text-sm">
                  <p className="font-medium">2. Sau khi đăng nhập xong</p>
                  <p className="text-xs text-slate-500">
                    Trình duyệt sẽ redirect tới <code>http://localhost:1455/auth/callback?code=…</code>{" "}
                    (trang lỗi "không kết nối được" là bình thường). Copy{" "}
                    <strong>toàn bộ URL trên thanh địa chỉ</strong> và dán vào đây:
                  </p>
                  <textarea
                    value={oauthRedirect}
                    onChange={(e) => setOauthRedirect(e.target.value)}
                    placeholder="http://localhost:1455/auth/callback?code=…&state=…"
                    rows={3}
                    className="w-full text-[11px] font-mono p-2 rounded border border-input bg-background"
                  />
                </div>
                {oauthErr && <p className="text-xs text-destructive">Lỗi: {oauthErr}</p>}
                <Button
                  onClick={() => completeOauth.mutate()}
                  disabled={!oauthRedirect.trim() || completeOauth.isPending}
                >
                  {completeOauth.isPending ? "Đang xác thực…" : "✓ Hoàn tất kết nối"}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
