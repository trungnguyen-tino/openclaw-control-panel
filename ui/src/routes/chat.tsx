import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, RefreshCw, Radio, MessageSquare, Trash2, Plus } from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { getStoredKey } from "@/lib/api";

interface OpenclawSession {
  id: string;
  key: string;
  updatedAt: number | null;
  startedAt: number | null;
  status: string | null;
  chatType: string | null;
  endedAt: number | null;
  runtimeMs: number | null;
  hasMessages: boolean;
}

// Raw event from openclaw's jsonl — shape varies. We only project a few
// fields for display; full payload is rendered as collapsible JSON for now.
interface OpenclawEvent {
  type?: string;
  role?: string;
  content?: unknown;
  text?: string;
  message?: { role?: string; content?: unknown };
  ts?: number;
  [k: string]: unknown;
}

export function ChatPage() {
  const qc = useQueryClient();
  const sessions = useQuery({
    queryKey: ["openclaw-sessions"],
    queryFn: () => api<{ sessions: OpenclawSession[] }>("/api/openclaw/sessions"),
    refetchInterval: 10_000,
  });

  const [activeId, setActiveId] = useState<string | null>(null);
  const [liveEvents, setLiveEvents] = useState<OpenclawEvent[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [input, setInput] = useState("");
  const [sendErr, setSendErr] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-pick first session on initial load. Skip the auto-pick when user
  // is composing a brand-new chat (`activeId === "new"`).
  useEffect(() => {
    if (!activeId && sessions.data?.sessions.length) {
      setActiveId(sessions.data.sessions[0].id);
    }
  }, [sessions.data, activeId]);

  const isComposingNew = activeId === "new";

  // SSE subscription to active session's jsonl tail.
  useEffect(() => {
    if (!activeId || activeId === "new") return;
    const key = getStoredKey();
    if (!key) return;
    setLiveEvents([]);
    setStreaming(true);
    // EventSource has no header API — auth must travel via query string.
    const url = `/api/openclaw/sessions/${encodeURIComponent(activeId)}/stream?auth=${encodeURIComponent(key)}`;
    const es = new EventSource(url);
    es.onmessage = (ev) => {
      if (!ev.data) return;
      try {
        const parsed = JSON.parse(ev.data) as OpenclawEvent;
        setLiveEvents((prev) => [...prev, parsed]);
      } catch {
        // Non-JSON line — ignore.
      }
    };
    es.onerror = () => {
      setStreaming(false);
      es.close();
    };
    return () => {
      es.close();
      setStreaming(false);
    };
  }, [activeId]);

  // Auto-scroll on new events.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [liveEvents]);

  const sendMsg = useMutation({
    mutationFn: (message: string) => {
      if (!activeId) throw new Error("Chưa chọn session");
      return api<{ ok: boolean; text?: string; error?: string }>(
        `/api/openclaw/sessions/${encodeURIComponent(activeId)}/send`,
        jsonBody({ message }),
      );
    },
    onSuccess: (resp) => {
      if (resp.ok) {
        setInput("");
        setSendErr(null);
        // For a brand-new chat, refetch sessions then jump to the newest one
        // (daemon created it for us during one_shot).
        if (activeId === "new") {
          sessions.refetch().then((r) => {
            const newest = r.data?.sessions[0];
            if (newest) setActiveId(newest.id);
          });
        } else {
          qc.invalidateQueries({ queryKey: ["openclaw-sessions"] });
        }
      } else {
        setSendErr(resp.error ?? "Gửi thất bại");
      }
    },
    onError: (err: unknown) =>
      setSendErr(err instanceof Error ? err.message : String(err)),
  });

  const deleteSession = useMutation({
    mutationFn: (sid: string) =>
      api<{ ok: boolean; archived?: string[]; error?: string }>(
        `/api/openclaw/sessions/${encodeURIComponent(sid)}`,
        { method: "DELETE" },
      ),
    onSuccess: (_resp, sid) => {
      if (sid === activeId) setActiveId(null);
      qc.invalidateQueries({ queryKey: ["openclaw-sessions"] });
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const m = input.trim();
    if (!m) return;
    sendMsg.mutate(m);
  }

  const activeSession = useMemo(
    () => sessions.data?.sessions.find((s) => s.id === activeId) ?? null,
    [sessions.data, activeId],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Chat AI"
        desc="Theo dõi + gửi tin nhắn vào sessions của Opencrawl Gateway theo thời gian thực."
      />

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
        {/* Sidebar: sessions list */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4" /> Sessions
            </CardTitle>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setActiveId("new");
                  setLiveEvents([]);
                  setInput("");
                  setSendErr(null);
                }}
                title="Tạo chat mới"
              >
                <Plus className="w-3.5 h-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => sessions.refetch()}
                disabled={sessions.isFetching}
                title="Làm mới"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${sessions.isFetching ? "animate-spin" : ""}`} />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-2 space-y-1 max-h-[600px] overflow-y-auto">
            {sessions.isLoading && (
              <p className="text-xs text-slate-500 p-2">Đang tải…</p>
            )}
            {sessions.data?.sessions.length === 0 && (
              <p className="text-xs text-slate-500 p-2">Chưa có session nào.</p>
            )}
            {sessions.data?.sessions.map((s) => (
              <div
                key={s.id}
                className={`group flex items-stretch rounded-md text-[12px] transition-colors ${
                  s.id === activeId
                    ? "bg-brand-50 text-brand-700"
                    : "hover:bg-slate-50 text-slate-700"
                }`}
              >
                <button
                  onClick={() => setActiveId(s.id)}
                  className={`flex-1 text-left px-2 py-1.5 ${s.id === activeId ? "font-semibold" : ""}`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="font-mono text-[11px] truncate">{s.id.slice(0, 8)}</span>
                    <StatusBadge status={s.status} />
                  </div>
                  <div className="text-[10.5px] text-slate-400 mt-0.5">
                    {s.updatedAt ? new Date(s.updatedAt).toLocaleString() : "—"}
                  </div>
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm(`Xoá session ${s.id.slice(0, 8)}? File jsonl sẽ được archive.`)) {
                      deleteSession.mutate(s.id);
                    }
                  }}
                  disabled={deleteSession.isPending}
                  title="Xoá session"
                  className="px-2 text-slate-400 hover:text-red-600 opacity-0 group-hover:opacity-100 disabled:opacity-30"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Main thread */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 flex-wrap gap-2">
            <div>
              <CardTitle>
                {isComposingNew ? "Chat mới" : activeSession ? "Hội thoại" : "Chọn session"}
              </CardTitle>
              {activeSession && !isComposingNew && (
                <p className="text-[11px] text-slate-500 font-mono mt-0.5 truncate max-w-md">
                  {activeSession.id}
                </p>
              )}
            </div>
            {streaming && !isComposingNew && (
              <Badge tone="success">
                <Radio className="w-3 h-3 animate-pulse" /> Live
              </Badge>
            )}
          </CardHeader>
          <CardContent className="p-0">
            <div
              ref={scrollRef}
              className="px-4 py-3 space-y-2 max-h-[480px] min-h-[320px] overflow-y-auto bg-slate-50 border-y border-slate-200"
            >
              {!activeId && (
                <p className="text-sm text-slate-500 text-center py-8">
                  Chọn 1 session bên trái để xem nội dung.
                </p>
              )}
              {isComposingNew && (
                <p className="text-sm text-slate-500 text-center py-8">
                  Bắt đầu chat mới — gõ tin nhắn và nhấn Enter để Opencrawl tạo session.
                </p>
              )}
              {activeId && !isComposingNew && liveEvents.length === 0 && (
                <p className="text-sm text-slate-500 text-center py-8">
                  Session này chưa có message (file .jsonl chưa được openclaw tạo).
                </p>
              )}
              {liveEvents.map((ev, i) => (
                <EventBubble key={i} ev={ev} />
              ))}
            </div>

            {sendErr && (
              <div className="mx-3 mt-3 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-[12.5px] text-red-700">
                <div className="font-semibold mb-0.5">✗ Không gửi được tin nhắn</div>
                <div className="font-mono text-[11px] break-all">{sendErr}</div>
              </div>
            )}
            <form onSubmit={submit} className="p-3 flex gap-2 items-center">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={activeId ? "Nhập tin nhắn… (Enter để gửi)" : "Chọn session trước"}
                disabled={!activeId || sendMsg.isPending}
                className="flex-1 h-10 rounded-md border border-slate-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-slate-100"
              />
              <Button type="submit" disabled={!activeId || sendMsg.isPending || !input.trim()}>
                <Send className="w-3.5 h-3.5" />
                {sendMsg.isPending ? "Đang gửi…" : "Gửi"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return null;
  const tone: "slate" | "success" | "warn" | "danger" =
    status === "running"
      ? "success"
      : status === "failed"
        ? "danger"
        : status === "completed"
          ? "slate"
          : "warn";
  return (
    <Badge tone={tone} className="text-[9px] px-1.5 py-0.5">
      {status}
    </Badge>
  );
}

function extractText(content: unknown): string | null {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const parts = content
      .map((p) => {
        if (typeof p === "string") return p;
        if (p && typeof p === "object" && "text" in p && typeof (p as { text: unknown }).text === "string") {
          return (p as { text: string }).text;
        }
        return "";
      })
      .filter(Boolean);
    return parts.length ? parts.join("\n") : null;
  }
  return null;
}

function EventBubble({ ev }: { ev: OpenclawEvent }) {
  // Only render conversational turns (role=user|assistant|model). Skip jsonl
  // metadata events like `session`, `model_change`, `thinking_level_change`,
  // tool calls, etc. — they belong in a debug panel, not the chat thread.
  const role = ev.role ?? (ev.message as { role?: string } | undefined)?.role ?? null;
  if (role !== "user" && role !== "assistant" && role !== "model") return null;

  const text =
    extractText(ev.text) ??
    extractText(ev.content) ??
    extractText((ev.message as { content?: unknown } | undefined)?.content);
  if (!text) return null;

  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-3 py-2 text-[13px] whitespace-pre-wrap ${
          isUser
            ? "bg-brand-600 text-white"
            : "bg-white border border-slate-200 text-ink"
        }`}
      >
        <div className="text-[9.5px] uppercase opacity-60 mb-0.5">
          {isUser ? "Bạn" : "Assistant"}
        </div>
        {text}
      </div>
    </div>
  );
}
