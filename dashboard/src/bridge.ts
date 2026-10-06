// 页面层：AstrBot 注入的 bridge。页面只通过它访问后端，不自己发 HTTP。

export interface AstrBotBridge {
  ready: () => Promise<unknown>;
  apiGet: <T>(endpoint: string, params?: Record<string, unknown>) => Promise<T>;
  apiPost: <T>(endpoint: string, body?: unknown) => Promise<T>;
}

declare global {
  interface Window {
    AstrBotPluginView?: AstrBotBridge;
    AstrBotPluginPage?: AstrBotBridge;
  }
}

export function getBridge(): AstrBotBridge {
  // 宿主注入的名字有两个，取不到任何一个都没法调后端
  const bridge = window.AstrBotPluginView || window.AstrBotPluginPage;
  if (!bridge) {
    throw new Error("页面桥接未就绪，请刷新后重试。");
  }
  return bridge;
}

export async function apiGet<T>(endpoint: string, params?: Record<string, unknown>): Promise<T> {
  // 先等 bridge 就绪，避免宿主还没注入就发请求
  const bridge = getBridge();
  await bridge.ready();
  return bridge.apiGet<T>(endpoint, params);
}

export async function apiPost<T>(endpoint: string, body?: unknown): Promise<T> {
  // 写操作同样先等 bridge
  const bridge = getBridge();
  await bridge.ready();
  return bridge.apiPost<T>(endpoint, body);
}

export function readError(error: unknown): string {
  // 后端用 error_response 时 bridge 抛 Error，message 就是中文原因
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return String(error);
}
