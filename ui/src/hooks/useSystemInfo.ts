import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface SystemInfo {
  ok: boolean;
  hostname: string;
  uptime: number;
  loadavg: number[];
  cpuPct?: number;
  memUsed?: number;
  memTotal?: number;
  memPct?: number;
  diskUsed?: number;
  diskTotal?: number;
  diskPct?: number;
  nodeVersion?: string;
  openclawVersion?: string;
}

/**
 * Topbar StatPills + Dashboard MeterCards consume this.
 * Stale 5s — fresh enough for resource gauges without thrashing backend.
 */
export function useSystemInfo() {
  return useQuery({
    queryKey: ["system"],
    queryFn: () => api<SystemInfo>("/api/system"),
    staleTime: 5_000,
    refetchInterval: 10_000,
  });
}
