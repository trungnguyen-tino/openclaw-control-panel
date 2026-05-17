import { Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { getStoredKey } from "@/lib/api";
import { LoginPage } from "@/routes/login";
import { ServiceInfoPage } from "@/routes/service-info";
import { ChatPage } from "@/routes/chat";
import { DomainPage } from "@/routes/domain";
import { AiConfigPage } from "@/routes/ai-config";
import { MultiAgentPage } from "@/routes/multi-agent";
import { ChannelsPage } from "@/routes/channels";
import { VersionPage } from "@/routes/version";
import { LogsPage } from "@/routes/logs";
import { ControlPage } from "@/routes/control";
import { TerminalPage } from "@/routes/terminal";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function Protected({ children }: { children: React.ReactNode }) {
  return getStoredKey() ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <Protected>
              <AppShell />
            </Protected>
          }
        >
          <Route index element={<ServiceInfoPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="openclaw-chat" element={<Navigate to="/chat" replace />} />
          <Route path="domain" element={<DomainPage />} />
          <Route path="ai-config" element={<AiConfigPage />} />
          <Route path="multi-agent" element={<MultiAgentPage />} />
          <Route path="channels" element={<ChannelsPage />} />
          <Route path="version" element={<VersionPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="control" element={<ControlPage />} />
          <Route path="terminal" element={<TerminalPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </QueryClientProvider>
  );
}
