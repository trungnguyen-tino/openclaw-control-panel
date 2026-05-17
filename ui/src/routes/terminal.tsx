import { FormEvent, useEffect, useRef, useState } from "react";
import { api, jsonBody } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";

interface CliResp {
  ok: boolean;
  exitCode?: number;
  stdout?: string;
  stderr?: string;
  cmd?: string;
  error?: string;
  raw?: boolean;
}

interface BufferEntry {
  kind: "input" | "output" | "info";
  text: string;
  ok?: boolean;
  exitCode?: number;
  ts: number;
}

const HISTORY_KEY = "openclaw_terminal_history_v2";
const HISTORY_LIMIT = 200;
const PROMPT = "root@openclaw:~#";

function loadHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(items: string[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(-HISTORY_LIMIT)));
  } catch {
    // ignore
  }
}

export function TerminalPage() {
  const [command, setCommand] = useState("");
  const [busy, setBusy] = useState(false);
  const [buffer, setBuffer] = useState<BufferEntry[]>([
    {
      kind: "info",
      text: "OpenClaw Terminal — shell trực tiếp trên VPS (full bash). Type 'help' để xem gợi ý.",
      ts: Date.now(),
    },
  ]);
  const [cmdHistory, setCmdHistory] = useState<string[]>(loadHistory());
  const [recallIdx, setRecallIdx] = useState<number>(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const bufferRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new buffer entries.
  useEffect(() => {
    bufferRef.current?.scrollTo({ top: bufferRef.current.scrollHeight, behavior: "smooth" });
  }, [buffer]);

  // Focus input on mount and after any buffer click.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function appendBuffer(entries: BufferEntry[]) {
    setBuffer((prev) => [...prev, ...entries]);
  }

  function clearScreen() {
    setBuffer([
      { kind: "info", text: "Screen cleared.", ts: Date.now() },
    ]);
  }

  function showHelp() {
    const helpText = [
      "Gợi ý lệnh:",
      "  openclaw pairing approve telegram <CODE>   # approve bot pairing",
      "  openclaw channels list --json              # list configured channels",
      "  openclaw agents list --json                # list agents",
      "  openclaw doctor                            # health diagnostics",
      "  openclaw config get <path>                 # read config value",
      "  systemctl status openclaw|caddy|openclaw-mgmt",
      "  journalctl -u openclaw -n 50 --no-pager",
      "  tail -100 /tmp/openclaw/openclaw-*.log",
      "  jq '.channels' /opt/openclaw/.openclaw/openclaw.json",
      "  cat /opt/openclaw/.env | head",
      "  df -h | grep -v tmpfs",
      "Special:",
      "  clear   # xoá output",
      "  help    # gợi ý này",
      "↑↓: duyệt lịch sử. Enter: chạy.",
    ].join("\n");
    appendBuffer([{ kind: "output", text: helpText, ts: Date.now() }]);
  }

  async function runCommand(e?: FormEvent) {
    e?.preventDefault();
    const cmd = command.trim();
    if (!cmd || busy) return;

    // Echo input.
    appendBuffer([{ kind: "input", text: cmd, ts: Date.now() }]);

    // Special local commands.
    if (cmd === "clear") {
      setCommand("");
      setRecallIdx(-1);
      clearScreen();
      return;
    }
    if (cmd === "help") {
      setCommand("");
      setRecallIdx(-1);
      showHelp();
      return;
    }

    // Persist to history (dedupe consecutive).
    const nextHist = cmdHistory.at(-1) === cmd ? cmdHistory : [...cmdHistory, cmd];
    setCmdHistory(nextHist);
    saveHistory(nextHist);
    setCommand("");
    setRecallIdx(-1);

    setBusy(true);
    try {
      const resp = await api<CliResp>("/api/cli", jsonBody({ command: cmd, raw: true }));
      const parts: string[] = [];
      if (resp.stdout) parts.push(resp.stdout.replace(/\n$/, ""));
      if (resp.stderr) parts.push((resp.stdout ? "\n" : "") + resp.stderr.replace(/\n$/, ""));
      if (resp.error) parts.push(`[error] ${resp.error}`);
      const text = parts.join("") || "(no output)";
      appendBuffer([
        {
          kind: "output",
          text,
          ok: resp.ok,
          exitCode: resp.exitCode ?? -1,
          ts: Date.now(),
        },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      appendBuffer([
        { kind: "output", text: `[network error] ${msg}`, ok: false, exitCode: -1, ts: Date.now() },
      ]);
    } finally {
      setBusy(false);
      // Re-focus input.
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (cmdHistory.length === 0) return;
      const nextIdx = recallIdx === -1 ? cmdHistory.length - 1 : Math.max(0, recallIdx - 1);
      setCommand(cmdHistory[nextIdx]);
      setRecallIdx(nextIdx);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (recallIdx === -1) return;
      const nextIdx = recallIdx + 1;
      if (nextIdx >= cmdHistory.length) {
        setCommand("");
        setRecallIdx(-1);
      } else {
        setCommand(cmdHistory[nextIdx]);
        setRecallIdx(nextIdx);
      }
    } else if (e.key === "l" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      clearScreen();
    } else if (e.key === "c" && e.ctrlKey && !command) {
      e.preventDefault();
      appendBuffer([{ kind: "output", text: "^C", ts: Date.now() }]);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Terminal"
        desc={
          <>
            Full bash trên VPS — quyền root. Gõ <code className="font-mono">help</code> để xem gợi ý,{" "}
            <code className="font-mono">clear</code> để xoá output.
          </>
        }
      />

      <div
        className="rounded-md bg-zinc-950 text-zinc-100 font-mono text-[13px] leading-relaxed border border-zinc-800 shadow-inner"
        onClick={() => inputRef.current?.focus()}
      >
        {/* Top tab bar — pure cosmetic */}
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-zinc-800 bg-zinc-900/80 rounded-t-md">
          <span className="size-2.5 rounded-full bg-red-500/80" />
          <span className="size-2.5 rounded-full bg-yellow-500/80" />
          <span className="size-2.5 rounded-full bg-green-500/80" />
          <span className="ml-2 text-[11px] text-zinc-400">
            openclaw.trunglab.com — bash {busy && <span className="text-yellow-400">· running…</span>}
          </span>
        </div>

        {/* Output buffer */}
        <div
          ref={bufferRef}
          className="px-4 py-3 h-[78vh] overflow-y-auto"
        >
          {buffer.map((entry, i) => {
            if (entry.kind === "info") {
              return (
                <div key={i} className="text-zinc-500 italic text-xs py-0.5">
                  {entry.text}
                </div>
              );
            }
            if (entry.kind === "input") {
              return (
                <div key={i} className="flex gap-2 py-0.5 select-text">
                  <span className="text-green-400 shrink-0">{PROMPT}</span>
                  <span className="text-zinc-100">{entry.text}</span>
                </div>
              );
            }
            // output
            return (
              <pre
                key={i}
                className={`whitespace-pre-wrap pb-1 select-text ${
                  entry.ok === false ? "text-red-300" : "text-zinc-300"
                }`}
              >
                {entry.text}
                {entry.exitCode !== undefined && entry.exitCode !== 0 && (
                  <span className="text-red-400 text-[11px] block mt-1">
                    exit {entry.exitCode}
                  </span>
                )}
              </pre>
            );
          })}

          {/* Live input prompt at bottom */}
          <form onSubmit={runCommand} className="flex gap-2 items-center py-0.5">
            <span className="text-green-400 shrink-0">{PROMPT}</span>
            <input
              ref={inputRef}
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={busy}
              spellCheck={false}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              className="flex-1 bg-transparent border-0 outline-none text-zinc-100 font-mono text-[13px] disabled:opacity-50"
              placeholder={busy ? "" : ""}
            />
            {busy && <span className="text-yellow-400 text-xs animate-pulse">…</span>}
          </form>
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground">
        ↑↓ duyệt history · Ctrl+L clear · Lệnh chạy với quyền root như SSH. Timeout 60s.
      </p>
    </div>
  );
}
