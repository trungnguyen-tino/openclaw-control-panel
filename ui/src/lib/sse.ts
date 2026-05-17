import { getStoredKey } from "./api";

// EventSource cannot set Authorization headers, so we pass the Bearer as a
// `token=` query param. The backend SSE routes accept both.
export function sseStream(
  path: string,
  handlers: {
    onMessage?: (data: unknown) => void;
    onEvent?: (event: string, data: unknown) => void;
    onError?: (err: Event) => void;
  },
): () => void {
  const key = getStoredKey() ?? "";
  const sep = path.includes("?") ? "&" : "?";
  const es = new EventSource(`${path}${sep}token=${encodeURIComponent(key)}`);
  const parse = (raw: string) => {
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  };
  es.onmessage = (e) => handlers.onMessage?.(parse(e.data));
  for (const name of ["start", "end", "error"]) {
    es.addEventListener(name, (e) => {
      const data = (e as MessageEvent).data;
      handlers.onEvent?.(name, data ? parse(data) : null);
    });
  }
  es.onerror = (e) => handlers.onError?.(e);
  return () => es.close();
}
