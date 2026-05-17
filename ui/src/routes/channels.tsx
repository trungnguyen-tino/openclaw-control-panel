import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

interface ChannelField {
  key: string;
  cli: string;
  label: string;
  secret: boolean;
}

interface Account {
  id: string;
  label: string;
}

interface ChannelEntry {
  label: string;
  installed: boolean;
  origin: string;
  accounts: Account[];
  fields: ChannelField[];
}

type SchemaResp = { schema: Record<string, { label: string; fields: ChannelField[] }> };
type ChannelsResp = { channels: Record<string, ChannelEntry> };

type FormMode = { type: "add" } | { type: "edit"; accountId: string };

export function ChannelsPage() {
  const qc = useQueryClient();
  const data = useQuery({
    queryKey: ["channels"],
    queryFn: () => api<ChannelsResp>("/api/channels"),
  });
  const schema = useQuery({
    queryKey: ["channels-schema"],
    queryFn: () => api<SchemaResp>("/api/channels/schema"),
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Kênh & Pairing"
        desc="Mỗi kênh có thể đăng ký nhiều tài khoản. Routing Bindings sẽ định tuyến tin nhắn từ kênh + account tới agent."
        actions={
          <Button variant="secondary" onClick={() => qc.invalidateQueries()}>
            <RefreshCw className="w-3.5 h-3.5" />
            Làm mới
          </Button>
        }
      />

      {data.isLoading && <p className="text-[13px] text-slate-500">Đang tải...</p>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {schema.data?.schema &&
          Object.entries(data.data?.channels ?? {}).map(([id, ch]) => (
            <ChannelCard
              key={id}
              channelId={id}
              channel={ch}
              fields={schema.data!.schema[id]?.fields ?? []}
              onChange={() => qc.invalidateQueries({ queryKey: ["channels"] })}
            />
          ))}
      </div>
    </div>
  );
}

function ChannelCard({
  channelId,
  channel,
  fields,
  onChange,
}: {
  channelId: string;
  channel: ChannelEntry;
  fields: ChannelField[];
  onChange: () => void;
}) {
  const [mode, setMode] = useState<FormMode | null>(null);

  const remove = useMutation({
    mutationFn: (accountId: string) =>
      api(`/api/channels/${channelId}/accounts/${accountId}`, { method: "DELETE" }),
    onSuccess: onChange,
  });

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle className="capitalize">{channel.label}</CardTitle>
          <CardDescription>
            {channel.accounts.length} account · origin: {channel.origin}
          </CardDescription>
        </div>
        <Button
          size="sm"
          variant={mode?.type === "add" ? "secondary" : "primary"}
          onClick={() => setMode(mode?.type === "add" ? null : { type: "add" })}
        >
          <Plus className="w-3.5 h-3.5" />
          {mode?.type === "add" ? "Đóng" : "Thêm account"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {channel.accounts.length === 0 ? (
          <p className="text-[13px] text-slate-500">Chưa có account.</p>
        ) : (
          <div className="space-y-2">
            {channel.accounts.map((a: Account) => {
              const isEditing = mode?.type === "edit" && mode.accountId === a.id;
              return (
                <div key={a.id} className="space-y-2">
                  <div className="flex items-center justify-between p-3 rounded-lg border border-slate-200 bg-slate-50">
                    <div className="flex items-center gap-2">
                      <Badge tone="slate" className="font-mono">
                        {a.id}
                      </Badge>
                      {a.label !== a.id && (
                        <span className="text-[13px]">{a.label}</span>
                      )}
                      {a.id === "default" && <Badge tone="success">mặc định</Badge>}
                    </div>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant={isEditing ? "primary" : "secondary"}
                        onClick={() =>
                          setMode(isEditing ? null : { type: "edit", accountId: a.id })
                        }
                      >
                        <Pencil className="w-3 h-3" />
                        {isEditing ? "Đóng" : "Sửa"}
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => {
                          if (confirm(`Xoá account ${a.id}?`)) remove.mutate(a.id);
                        }}
                        title="Xoá"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                  {isEditing && (
                    <AccountForm
                      mode={{ type: "edit", accountId: a.id }}
                      channelId={channelId}
                      fields={fields}
                      onSaved={() => {
                        setMode(null);
                        onChange();
                      }}
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {mode?.type === "add" && (
          <AccountForm
            mode={{ type: "add" }}
            channelId={channelId}
            fields={fields}
            onSaved={() => {
              setMode(null);
              onChange();
            }}
          />
        )}
      </CardContent>
    </Card>
  );
}

function AccountForm({
  mode,
  channelId,
  fields,
  onSaved,
}: {
  mode: FormMode;
  channelId: string;
  fields: ChannelField[];
  onSaved: () => void;
}) {
  const isEdit = mode.type === "edit";
  const [accountId, setAccountId] = useState(isEdit ? mode.accountId : "");
  const [values, setValues] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () => {
      // Only include fields the user actually typed — in edit mode, empty
      // fields keep the existing stored value (openclaw add is idempotent).
      const body: Record<string, string> = { account_id: accountId };
      for (const [k, v] of Object.entries(values)) {
        if (v && v.trim()) body[k] = v;
      }
      return api(`/api/channels/${channelId}/accounts`, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      setValues({});
      setMsg(isEdit ? "✓ Đã cập nhật account" : "✓ Đã thêm account");
      onSaved();
    },
    onError: (e: Error) => setMsg(`Lỗi: ${e.message}`),
  });

  return (
    <div className="space-y-3 p-4 rounded-lg bg-brand-50/40 border border-brand-100">
      <Field
        label={isEdit ? "Account ID (khoá)" : "Account ID *"}
        hint={isEdit ? "Để trống field nào → giữ giá trị cũ. Chỉ điền field muốn thay đổi." : undefined}
      >
        <Input
          placeholder="vd: bot-sales, bot-support (a-z0-9-_)"
          value={accountId}
          onChange={(e) =>
            setAccountId(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))
          }
          readOnly={isEdit}
          className={isEdit ? "bg-slate-100 cursor-not-allowed" : ""}
        />
      </Field>
      {fields.map((f) => (
        <Field key={f.key} label={f.label}>
          <Input
            type={f.secret ? "password" : "text"}
            placeholder={
              isEdit ? `(giữ giá trị cũ — chỉ điền nếu muốn đổi)` : f.label
            }
            value={values[f.key] ?? ""}
            onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            className={f.secret ? "font-mono" : ""}
          />
        </Field>
      ))}
      <div className="flex gap-2 items-center">
        <Button onClick={() => submit.mutate()} disabled={!accountId || submit.isPending}>
          {submit.isPending ? "Đang lưu..." : isEdit ? "Cập nhật" : "Lưu account"}
        </Button>
        {msg && (
          <p
            className={
              "text-xs " + (msg.startsWith("Lỗi") ? "text-red-600" : "text-slate-500")
            }
          >
            {msg}
          </p>
        )}
      </div>
    </div>
  );
}
