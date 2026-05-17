import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Square, RefreshCw, AlertTriangle } from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

interface StatusResp {
  openclaw: { status: string; startedAt: string | null };
  caddy: { status: string };
}

export function ControlPage() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["status"],
    queryFn: () => api<StatusResp>("/api/status"),
    refetchInterval: 4000,
  });
  const [confirm, setConfirm] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  function call(path: string, label: string) {
    return useMutation({
      mutationFn: () => api(path, { method: "POST" }),
      onSuccess: () => {
        setMsg(`✓ Đã ${label}`);
        qc.invalidateQueries({ queryKey: ["status"] });
      },
      onError: (e: Error) => setMsg(`Lỗi ${label}: ${e.message}`),
    });
  }

  const restart = call("/api/restart", "khởi động lại");
  const stop = call("/api/stop", "dừng");
  const rebuild = call("/api/rebuild", "rebuild");

  const reset = useMutation({
    mutationFn: () => api("/api/reset", jsonBody({ confirm })),
    onSuccess: () => {
      setMsg("✓ Đã reset toàn bộ config + restart.");
      setConfirm("");
      qc.invalidateQueries();
    },
    onError: (e: Error) => setMsg(`Lỗi reset: ${e.message}`),
  });

  const openclawActive = status.data?.openclaw.status === "active";
  const caddyActive = status.data?.caddy.status === "active";

  return (
    <div className="space-y-5">
      <PageHeader
        title="Điều khiển dịch vụ"
        desc="Khởi động, dừng, rebuild hoặc reset Opencrawl"
      />

      <Card>
        <CardHeader>
          <CardTitle>Trạng thái container</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ServiceRow
            name="openclaw"
            active={openclawActive}
            meta={status.data?.openclaw.startedAt ? `started ${status.data.openclaw.startedAt}` : ""}
          />
          <ServiceRow name="caddy" active={caddyActive} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5 flex gap-2 flex-wrap">
          <Button onClick={() => restart.mutate()} disabled={restart.isPending}>
            <RotateCcw className="w-3.5 h-3.5" />
            Khởi động lại
          </Button>
          <Button variant="secondary" onClick={() => stop.mutate()} disabled={stop.isPending}>
            <Square className="w-3.5 h-3.5" />
            Dừng
          </Button>
          <Button variant="secondary" onClick={() => rebuild.mutate()} disabled={rebuild.isPending}>
            <RefreshCw className="w-3.5 h-3.5" />
            Rebuild
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => qc.invalidateQueries({ queryKey: ["status"] })}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Làm mới
          </Button>
        </CardContent>
      </Card>

      {msg && (
        <Card
          className={
            msg.startsWith("Lỗi")
              ? "bg-red-50 border-red-200"
              : "bg-emerald-50 border-emerald-200"
          }
        >
          <CardContent className="p-3 text-[13px]">{msg}</CardContent>
        </Card>
      )}

      <Card className="border-red-200">
        <CardHeader>
          <div>
            <CardTitle className="text-red-600 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              Vùng nguy hiểm
            </CardTitle>
            <CardDescription>
              Reset sẽ xoá toàn bộ dữ liệu & cấu hình, tạo lại từ mặc định. File{" "}
              <code className="font-mono">.env</code> (token) được giữ lại.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <Field
            label="Xác nhận"
            hint={
              <>
                Nhập <span className="font-bold">RESET</span> để cho phép button
              </>
            }
          >
            <Input
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="RESET"
              className="font-mono"
            />
          </Field>
          <Button
            variant="destructive"
            onClick={() => reset.mutate()}
            disabled={confirm !== "RESET" || reset.isPending}
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            Reset toàn bộ
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function ServiceRow({ name, active, meta }: { name: string; active: boolean; meta?: string }) {
  return (
    <div className="flex items-center gap-2.5 p-3 rounded-lg border border-slate-200 bg-slate-50">
      <Badge tone={active ? "success" : "danger"} dot>
        {active ? "Đang chạy" : "Đã dừng"}
      </Badge>
      <span className="text-[13px] font-mono text-ink">{name}</span>
      {meta && <span className="text-[12px] text-slate-500 ml-auto">{meta}</span>}
    </div>
  );
}
