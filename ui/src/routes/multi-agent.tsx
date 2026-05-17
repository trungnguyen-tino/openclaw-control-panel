import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Trash2, ArrowRight } from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

interface AgentRow {
  id: string;
  name: string;
  default: boolean;
  model?: string;
  hasAuthProfiles: boolean;
  apiKeyCount: number;
}

interface Binding {
  agentId: string;
  match: { channel?: string; accountId?: string };
}

interface Account {
  id: string;
  label: string;
}
interface ChannelEntry {
  label: string;
  accounts: Account[];
}

export function MultiAgentPage() {
  const qc = useQueryClient();
  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<{ agents: AgentRow[]; count: number }>("/api/agents"),
  });
  const bindings = useQuery({
    queryKey: ["bindings"],
    queryFn: () => api<{ bindings: Binding[] }>("/api/bindings"),
  });
  const channels = useQuery({
    queryKey: ["channels"],
    queryFn: () => api<{ channels: Record<string, ChannelEntry> }>("/api/channels"),
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [newId, setNewId] = useState("");
  const [newName, setNewName] = useState("");
  const [bindAgentId, setBindAgentId] = useState("");
  const [bindChannel, setBindChannel] = useState("");
  const [bindAccount, setBindAccount] = useState("");

  const create = useMutation({
    mutationFn: () => api("/api/agents", jsonBody({ id: newId, name: newName || newId })),
    onSuccess: () => {
      setNewId("");
      setNewName("");
      setCreateOpen(false);
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/agents/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });

  const setDefault = useMutation({
    mutationFn: (id: string) => api(`/api/agents/${id}/default`, { method: "PUT" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });

  const addBinding = useMutation({
    mutationFn: () => {
      const match: Record<string, string> = { channel: bindChannel };
      if (bindAccount) match.accountId = bindAccount;
      return api("/api/bindings", jsonBody({ agentId: bindAgentId, match }));
    },
    onSuccess: () => {
      setBindAgentId("");
      setBindAccount("");
      qc.invalidateQueries({ queryKey: ["bindings"] });
    },
  });

  const delBinding = useMutation({
    mutationFn: (i: number) => api(`/api/bindings/${i}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bindings"] }),
  });

  const channelEntries = channels.data?.channels ?? {};
  const channelIds = Object.keys(channelEntries);
  const selectedChannelAccounts = channelEntries[bindChannel]?.accounts ?? [];
  const list = agents.data?.agents ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Multi-Agent"
        desc="Quản lý các agent AI và định tuyến tin nhắn theo kênh / account"
        actions={
          <>
            <Button variant="secondary" onClick={() => qc.invalidateQueries()}>
              <RefreshCw className="w-3.5 h-3.5" />
            </Button>
            <Button onClick={() => setCreateOpen((v) => !v)}>
              <Plus className="w-3.5 h-3.5" />
              Tạo Agent
            </Button>
          </>
        }
      />

      {createOpen && (
        <Card className="border-brand-300">
          <CardContent className="p-5">
            <div className="flex flex-wrap items-end gap-3">
              <Field label="ID (a-z, 0-9, dấu -)" className="flex-1 min-w-[200px]">
                <Input
                  value={newId}
                  onChange={(e) => setNewId(e.target.value)}
                  placeholder="vd: marketing-bot"
                />
              </Field>
              <Field label="Tên hiển thị" className="flex-1 min-w-[200px]">
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="vd: Marketing Bot"
                />
              </Field>
              <Button
                onClick={() => create.mutate()}
                disabled={!newId.trim() || create.isPending}
              >
                {create.isPending ? "Đang tạo…" : "Tạo"}
              </Button>
              <Button variant="ghost" onClick={() => setCreateOpen(false)}>
                Huỷ
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Agents */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Agents ({list.length})</CardTitle>
            <CardDescription>
              Mỗi agent có cấu hình provider/model và API key riêng
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {list.length === 0 && (
            <p className="p-5 text-[13px] text-slate-500">Chưa có agent.</p>
          )}
          {list.map((a, i) => (
            <div
              key={a.id}
              className={`flex items-center gap-3.5 p-4 ${i > 0 ? "border-t border-slate-200" : ""}`}
            >
              <div className="w-9 h-9 rounded-lg bg-brand-900 text-white grid place-items-center font-bold text-sm shrink-0">
                {a.name?.[0]?.toUpperCase() ?? "A"}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold">{a.name}</span>
                  <Badge tone="slate" className="font-mono">
                    {a.id}
                  </Badge>
                  {a.default && <Badge tone="success">Mặc định</Badge>}
                </div>
                <div className="text-[12px] text-slate-500 font-mono mt-0.5">
                  {a.model ?? "—"} · {a.apiKeyCount} API key
                </div>
              </div>
              <div className="flex items-center gap-2">
                {!a.default && (
                  <Button variant="secondary" size="sm" onClick={() => setDefault.mutate(a.id)}>
                    Đặt mặc định
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={a.default}
                  onClick={() => {
                    if (confirm(`Xoá agent ${a.id}?`)) remove.mutate(a.id);
                  }}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Bindings */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Routing Bindings</CardTitle>
            <CardDescription>
              Định tuyến tin nhắn: <b>Kênh + Account</b> → Agent. Để trống account để áp dụng cho
              mọi account của kênh.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-[13px]">
            <thead className="text-slate-400 text-[11px] font-bold uppercase tracking-wider">
              <tr className="text-left">
                <th className="px-4 py-2 w-12">#</th>
                <th>Kênh</th>
                <th>Account</th>
                <th className="w-8" />
                <th>Agent</th>
                <th className="w-12" />
              </tr>
            </thead>
            <tbody>
              {(bindings.data?.bindings ?? []).map((b, i) => (
                <tr key={i} className="border-t border-slate-200">
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{i}</td>
                  <td className="font-medium">{b.match?.channel}</td>
                  <td className="font-mono text-xs">{b.match?.accountId ?? "*"}</td>
                  <td className="text-slate-400">
                    <ArrowRight className="w-3.5 h-3.5" />
                  </td>
                  <td className="font-mono">{b.agentId}</td>
                  <td className="px-4">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm(`Xoá binding #${i}?`)) delBinding.mutate(i);
                      }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Add binding form */}
          <div className="p-4 border-t border-slate-200 flex items-end gap-3 flex-wrap">
            <Field label="Kênh" className="min-w-[140px]">
              <select
                className="h-9 px-3 border border-slate-200 rounded-lg bg-white text-[13px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
                value={bindChannel}
                onChange={(e) => {
                  setBindChannel(e.target.value);
                  setBindAccount("");
                }}
              >
                <option value="">— chọn —</option>
                {channelIds.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Account (tuỳ chọn)" className="min-w-[180px]">
              <select
                className="h-9 px-3 border border-slate-200 rounded-lg bg-white text-[13px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100 disabled:opacity-50"
                value={bindAccount}
                onChange={(e) => setBindAccount(e.target.value)}
                disabled={!bindChannel || selectedChannelAccounts.length === 0}
              >
                <option value="">* (mọi account)</option>
                {selectedChannelAccounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Agent" className="min-w-[160px]">
              <select
                className="h-9 px-3 border border-slate-200 rounded-lg bg-white text-[13px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
                value={bindAgentId}
                onChange={(e) => setBindAgentId(e.target.value)}
              >
                <option value="">— chọn agent —</option>
                {list.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.id}
                  </option>
                ))}
              </select>
            </Field>
            <Button
              onClick={() => addBinding.mutate()}
              disabled={!bindChannel || !bindAgentId || addBinding.isPending}
            >
              <Plus className="w-3.5 h-3.5" />
              Thêm Binding
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
