import { useEffect, useRef, useState } from "react";
import { RefreshCw, Play, Square } from "lucide-react";
import { sseStream } from "@/lib/sse";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

const SERVICES = [
  { id: "openclaw", label: "OpenClaw" },
  { id: "caddy", label: "Caddy" },
  { id: "openclaw-mgmt", label: "Management API" },
];

interface LogsResp {
  ok: boolean;
  service: string;
  lines: number;
  logs: string[];
}

export function LogsPage() {
  const [service, setService] = useState("openclaw");
  const [lines, setLines] = useState(100);
  const [streaming, setStreaming] = useState(false);
  const [output, setOutput] = useState<string[]>([]);
  const closeRef = useRef<(() => void) | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => () => closeRef.current?.(), []);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [output]);

  async function loadSnapshot() {
    closeRef.current?.();
    setStreaming(false);
    setOutput(["Đang tải..."]);
    try {
      const r = await api<LogsResp>(`/api/logs?service=${service}&lines=${lines}`);
      setOutput(r.logs);
    } catch (e) {
      setOutput([`Lỗi: ${e instanceof Error ? e.message : String(e)}`]);
    }
  }

  function startStream() {
    closeRef.current?.();
    setOutput([]);
    setStreaming(true);
    closeRef.current = sseStream(`/api/logs/stream?service=${encodeURIComponent(service)}`, {
      onMessage: (d) => {
        const text = typeof d === "string" ? d : (d as { line?: string }).line ?? JSON.stringify(d);
        setOutput((prev) => [...prev.slice(-2000), text]);
      },
      onEvent: (ev) => {
        if (ev === "end" || ev === "error") setStreaming(false);
      },
      onError: () => setStreaming(false),
    });
  }

  function stopStream() {
    closeRef.current?.();
    closeRef.current = null;
    setStreaming(false);
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Nhật ký hệ thống" desc="Stream log của 3 dịch vụ Opencrawl" />

      <Card>
        <CardHeader>
          <div className="flex gap-3 items-end flex-wrap">
            <Field label="Dịch vụ">
              <select
                className="h-9 px-3 border border-slate-200 rounded-lg bg-white text-[13px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
                value={service}
                onChange={(e) => setService(e.target.value)}
                disabled={streaming}
              >
                {SERVICES.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Số dòng">
              <input
                type="number"
                className="h-9 w-24 px-3 border border-slate-200 rounded-lg bg-white text-[13px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
                min={10}
                max={1000}
                value={lines}
                onChange={(e) =>
                  setLines(Math.max(10, Math.min(1000, Number(e.target.value) || 100)))
                }
                disabled={streaming}
              />
            </Field>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={loadSnapshot} disabled={streaming}>
              <RefreshCw className="w-3.5 h-3.5" />
              Tải lại
            </Button>
            {!streaming ? (
              <Button size="sm" onClick={startStream}>
                <Play className="w-3.5 h-3.5" />
                Stream
              </Button>
            ) : (
              <Button size="sm" variant="destructive" onClick={stopStream}>
                <Square className="w-3.5 h-3.5" />
                Dừng
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="bg-zinc-950 text-emerald-200 rounded-lg p-4 h-[60vh] overflow-y-auto font-mono text-[12px] leading-relaxed">
            {output.length === 0 ? (
              <p className="text-zinc-500 italic">Nhấn "Tải lại" hoặc "Stream" để xem log.</p>
            ) : (
              output.map((l, i) => <div key={i}>{l}</div>)
            )}
            <div ref={bottomRef} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
