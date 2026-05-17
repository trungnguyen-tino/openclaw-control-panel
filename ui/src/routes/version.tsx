import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpCircle, RefreshCw } from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Field as FormField } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";

interface VersionResp {
  version: string;
  clawVersion: string;
}

interface HealthResp {
  ok: boolean;
  version: string;
  uptimeSeconds: number;
}

interface VersionEntry {
  version: string;
  isBeta: boolean;
}

interface UpgradeVersionsResp {
  ok: boolean;
  versions: VersionEntry[];
  error?: string;
}

export function VersionPage() {
  const qc = useQueryClient();
  const version = useQuery({
    queryKey: ["version"],
    queryFn: () => api<VersionResp>("/api/version"),
  });
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<HealthResp>("/api/health") });
  const upgradeVersions = useQuery({
    queryKey: ["upgrade-versions"],
    queryFn: () => api<UpgradeVersionsResp>("/api/upgrade/versions"),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const [tag, setTag] = useState("latest");
  const [selectedVersion, setSelectedVersion] = useState("latest");
  const [msg, setMsg] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [includeBeta, setIncludeBeta] = useState(true);

  const allVersions = upgradeVersions.data?.versions ?? [];
  const currentVersion = version.data?.clawVersion;
  const filteredVersions = allVersions.filter((v) => {
    if (!includeBeta && v.isBeta) return v.version === currentVersion;
    if (searchTerm && !v.version.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    return true;
  });

  const upgradeOpenClaw = useMutation({
    mutationFn: (target: string) =>
      api("/api/upgrade", {
        method: "POST",
        body: JSON.stringify({ version: target }),
      }),
    onSuccess: (_data, target) => {
      setMsg(
        `✓ Đang nâng cấp OpenClaw → ${target}. Log: /var/log/openclaw-mgmt/upgrade.log. Dịch vụ sẽ tự restart khi xong.`,
      );
      qc.invalidateQueries();
    },
    onError: (err: unknown) =>
      setMsg(err instanceof Error ? `✗ ${err.message}` : `✗ ${String(err)}`),
  });

  const updateMgmt = useMutation({
    mutationFn: () => api("/api/self-update", jsonBody({ tag })),
    onSuccess: () => {
      setMsg(`✓ Đang tải bản Management API ${tag}. Theo dõi /var/log/openclaw-mgmt/self-update.log.`);
    },
  });

  return (
    <div className="space-y-5">
      <PageHeader title="Phiên bản & Nâng cấp" desc="Xem phiên bản hiện tại và nâng cấp Opencrawl" />

      <Card>
        <CardHeader>
          <CardTitle>Phiên bản hiện tại</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <InfoCell label="OpenClaw" value={version.data?.clawVersion ?? "—"} />
          <InfoCell label="Management API" value={health.data?.version ?? "—"} />
          <InfoCell label="Cấu hình version" value={version.data?.version ?? "—"} />
          <InfoCell
            label="Uptime"
            value={
              health.data?.uptimeSeconds
                ? `${Math.floor(health.data.uptimeSeconds / 60)} phút`
                : "—"
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Nâng cấp OpenClaw (npm)</CardTitle>
            <CardDescription>
              Chạy <code className="font-mono">npm install -g openclaw@&lt;version&gt;</code> và khởi động lại dịch vụ.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 items-end flex-wrap mb-2">
            <FormField label="Tìm phiên bản" className="flex-1 max-w-xs">
              <Input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="vd: 2026.5"
              />
            </FormField>
            <label className="inline-flex items-center gap-1.5 text-sm h-9 pb-1">
              <input
                type="checkbox"
                checked={includeBeta}
                onChange={(e) => setIncludeBeta(e.target.checked)}
                className="w-3.5 h-3.5"
              />
              Hiển thị bản beta
            </label>
          </div>
          <div className="flex gap-2 items-end flex-wrap">
            <FormField
              label={`Phiên bản (${filteredVersions.length} kết quả)`}
              className="flex-1 max-w-xs"
            >
              <select
                value={selectedVersion}
                onChange={(e) => setSelectedVersion(e.target.value)}
                disabled={upgradeVersions.isLoading}
                size={Math.min(Math.max(filteredVersions.length + 1, 5), 12)}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="latest">latest</option>
                {filteredVersions.map((v) => (
                  <option key={v.version} value={v.version}>
                    {v.version}
                    {v.isBeta ? "  [beta]" : ""}
                    {v.version === currentVersion ? "  (đang dùng)" : ""}
                  </option>
                ))}
              </select>
            </FormField>
            <Button
              onClick={() => upgradeOpenClaw.mutate(selectedVersion)}
              disabled={upgradeOpenClaw.isPending}
            >
              <ArrowUpCircle className="w-3.5 h-3.5" />
              {upgradeOpenClaw.isPending ? "Đang nâng cấp…" : "Nâng cấp OpenClaw"}
            </Button>
          </div>
          {upgradeVersions.isError && (
            <p className="text-xs text-amber-700 mt-2">
              Không tải được danh sách phiên bản — có thể nâng cấp bằng "latest".
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Cập nhật Management API</CardTitle>
            <CardDescription>
              Tải tarball release mới từ GitHub, swap, restart mgmt-api.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 items-end flex-wrap">
            <FormField label="Tag" className="flex-1 max-w-xs">
              <Input
                value={tag}
                onChange={(e) => setTag(e.target.value)}
                placeholder="vd: v0.2.0"
              />
            </FormField>
            <Button
              variant="secondary"
              onClick={() => updateMgmt.mutate()}
              disabled={updateMgmt.isPending}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Cập nhật Management API
            </Button>
          </div>
        </CardContent>
      </Card>

      {msg && (
        <Card className="bg-emerald-50 border-emerald-200">
          <CardContent className="p-3 text-[13px]">{msg}</CardContent>
        </Card>
      )}

      <Card className="bg-amber-50 border-amber-200">
        <CardContent className="p-4 text-[12px] text-amber-800">
          <strong>Lưu ý</strong>: Quá trình nâng cấp sẽ pull tarball mới và restart dịch vụ. Có
          thể gián đoạn vài giây.
        </CardContent>
      </Card>
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-slate-500 font-semibold">{label}</p>
      <div className="text-[15px] font-bold font-mono mt-1 text-ink">{value}</div>
    </div>
  );
}
