import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { api, jsonBody, setStoredKey } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Input } from "@/components/ui/Input";
import { BrandLogo } from "@/components/ui/BrandLogo";

type AuthMode = "password" | "apikey";

export function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>("password");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [rawKey, setRawKey] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      if (mode === "apikey") {
        if (!rawKey.trim()) throw new Error("Vui lòng dán Management API key");
        setStoredKey(rawKey.trim());
      } else {
        if (!password) throw new Error("Vui lòng nhập mật khẩu");
        const resp = await api<{ ok: boolean; mgmtApiKey?: string; error?: string }>(
          "/api/auth/login",
          jsonBody({ username, password }),
        );
        if (!resp.ok) throw new Error(resp.error ?? "Đăng nhập thất bại");
        if (!resp.mgmtApiKey) throw new Error("Server chưa trả mgmtApiKey");
        setStoredKey(resp.mgmtApiKey);
      }
      navigate("/", { replace: true });
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex bg-[#F6F9FD]">
      {/* Hero — left col, desktop only */}
      <aside className="hero-pattern relative hidden md:flex md:flex-1 bg-gradient-to-br from-brand-700 via-brand-800 to-brand-900 text-white p-12 flex-col justify-between overflow-hidden">
        <div className="flex items-center gap-3.5 z-10">
          <BrandLogo size={40} full />
          <div className="text-lg font-extrabold tracking-tight leading-tight">
            Opencrawl Management Panel
          </div>
        </div>

        <div className="max-w-lg z-10">
          <div className="text-xs uppercase tracking-[0.14em] opacity-85 font-mono">
            VPS · Self-hosted · v1.1.4
          </div>
          <h1 className="text-[38px] font-extrabold tracking-tight mt-3 mb-3.5 leading-[1.1]">
            Panel quản lý<br />
            Opencrawl <span className="text-sand">chuyên nghiệp</span>
          </h1>
          <p className="text-[15px] opacity-90 leading-relaxed">
            Theo dõi gateway, định tuyến đa agent, cấu hình AI provider và SSL — tất cả trong một
            bảng điều khiển tối ưu cho doanh nghiệp Việt Nam.
          </p>
          <div className="flex gap-6 mt-7 flex-wrap">
            <Stat value="23+" label="AI Providers hỗ trợ" />
            <Stat value="56" label="API endpoints" />
            <Stat value="SSE" label="Real-time logs" />
          </div>
        </div>

        <div className="z-10" />
      </aside>

      {/* Form — right col */}
      <section className="flex-1 max-w-full md:max-w-[480px] flex items-center justify-center p-6 md:p-10">
        <div className="w-full max-w-md">
          <div className="md:hidden flex items-center gap-2 mb-6 justify-center">
            <BrandLogo size={28} full />
          </div>
          <div className="text-xs tracking-[0.12em] uppercase text-brand-700 font-bold">
            Đăng nhập
          </div>
          <h2 className="text-2xl font-extrabold tracking-tight mt-1.5 mb-1">Chào mừng trở lại</h2>
          <p className="text-slate-500 text-[13.5px] mb-5">
            Đăng nhập để quản lý Opencrawl của bạn
          </p>

          {/* Tab pill */}
          <div className="flex bg-slate-100 p-[3px] rounded-lg border border-slate-200 mb-5">
            {(
              [
                ["password", "Tài khoản"],
                ["apikey", "API Key"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setMode(id)}
                className={
                  "flex-1 h-8 rounded-md text-[13px] font-semibold transition-colors " +
                  (mode === id
                    ? "bg-white shadow-soft text-ink"
                    : "text-slate-500 hover:text-slate-700")
                }
              >
                {label}
              </button>
            ))}
          </div>

          <form className="space-y-4" onSubmit={submit}>
            {mode === "password" ? (
              <>
                <Field label="Tài khoản" htmlFor="login-user">
                  <Input
                    id="login-user"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                  />
                </Field>
                <Field label="Mật khẩu" htmlFor="login-pass">
                  <Input
                    id="login-pass"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="current-password"
                  />
                </Field>
              </>
            ) : (
              <Field
                label="OPENCLAW_MGMT_API_KEY"
                htmlFor="login-key"
                hint="Lấy giá trị key trong /opt/openclaw/.env hoặc output của install.sh."
              >
                <Input
                  id="login-key"
                  type="password"
                  value={rawKey}
                  onChange={(e) => setRawKey(e.target.value)}
                  placeholder="ock_..."
                  className="font-mono"
                />
              </Field>
            )}

            {err && (
              <div className="bg-red-50 text-red-600 px-3 py-2 rounded-lg text-[13px]">{err}</div>
            )}

            <Button type="submit" disabled={busy} size="lg" className="w-full">
              {busy ? "Đang đăng nhập…" : "Đăng nhập"}
              <ArrowRight className="w-4 h-4" />
            </Button>
          </form>

        </div>
      </section>
    </main>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="text-[22px] font-extrabold font-mono">{value}</div>
      <div className="opacity-85 text-xs">{label}</div>
    </div>
  );
}
