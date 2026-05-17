import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

export function DomainPage() {
  const qc = useQueryClient();
  const info = useQuery({
    queryKey: ["info"],
    queryFn: () => api<{ domain: string; ip: string; ssl: string }>("/api/info"),
  });
  const [newDomain, setNewDomain] = useState("");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const change = useMutation({
    mutationFn: () =>
      api("/api/domain", {
        method: "PUT",
        body: JSON.stringify({ domain: newDomain, email }),
      }),
    onSuccess: () => {
      setMsg({
        kind: "ok",
        text: "Đang đổi tên miền — kiểm tra trạng thái Caddy trong vài giây.",
      });
      qc.invalidateQueries();
    },
    onError: (e: Error) => setMsg({ kind: "err", text: e.message }),
  });

  return (
    <div className="space-y-5">
      <PageHeader title="Tên miền & SSL" desc="Cấu hình tên miền và chứng chỉ SSL cho Opencrawl" />

      <Card className="bg-emerald-50 border-emerald-200">
        <CardContent className="p-4 text-[13px] text-emerald-800">
          Vui lòng trỏ tên miền về IP{" "}
          <span className="font-mono font-bold">{info.data?.ip ?? "—"}</span> trước khi thực hiện
          thao tác này.
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Tên miền hiện tại</CardTitle>
            <CardDescription>
              SSL hiện tại: <span className="font-semibold text-ink">{info.data?.ssl ?? "—"}</span>
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <Input
            value={info.data?.domain ?? ""}
            readOnly
            className="bg-slate-50 font-mono cursor-not-allowed"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Đổi tên miền</CardTitle>
            <CardDescription>
              Caddy auto-issue cert qua Let's Encrypt sau khi DNS đã trỏ về IP đúng.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <Field label="Tên miền mới">
            <Input
              placeholder="vd: openclaw.example.com"
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
            />
          </Field>
          <Field
            label="Email (cho Let's Encrypt)"
            hint="Tuỳ chọn — chỉ dùng cho thông báo gia hạn cert."
          >
            <Input
              placeholder="vd: admin@example.com"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Button onClick={() => change.mutate()} disabled={!newDomain || change.isPending}>
            {change.isPending ? "Đang cập nhật…" : "Cập nhật tên miền"}
          </Button>
          {msg && (
            <p
              className={
                "text-xs " + (msg.kind === "ok" ? "text-emerald-700" : "text-red-600")
              }
            >
              {msg.text}
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="bg-amber-50 border-amber-200">
        <CardContent className="p-4 text-[12px] text-amber-800">
          <strong>Lưu ý</strong>: Việc thay đổi tên miền sẽ cấu hình lại SSL và khởi động lại dịch
          vụ. DNS phải trỏ đúng IP trước khi thay đổi.
        </CardContent>
      </Card>
    </div>
  );
}
