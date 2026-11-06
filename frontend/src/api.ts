// Thin API client. Every state-changing request carries the x-audienceos header (CSRF guard on the server).
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function handle(res: Response): Promise<any> {
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await res.json().catch(() => null) : await res.text();
  if (!res.ok) {
    let msg = "Something went wrong.";
    if (body && typeof body === "object" && "detail" in body) {
      const d = (body as any).detail;
      msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x: any) => `${(x.loc || []).slice(1).join(".")}: ${x.msg}`).join("; ") : JSON.stringify(d);
    } else if (typeof body === "string" && body) msg = body.slice(0, 300);
    throw new ApiError(msg, res.status);
  }
  return body;
}

export async function get<T = any>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path);
  } catch {
    throw new ApiError("Can't reach the AudienceOS engine. Is it still running?", 0);
  }
  return handle(res);
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: { "x-audienceos": "1", ...(body !== undefined ? { "content-type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Can't reach the AudienceOS engine. Is it still running?", 0);
  }
  return handle(res);
}

export const post = <T = any>(p: string, b?: unknown) => send<T>("POST", p, b ?? {});
export const put = <T = any>(p: string, b?: unknown) => send<T>("PUT", p, b ?? {});
export const patch = <T = any>(p: string, b?: unknown) => send<T>("PATCH", p, b ?? {});
export const del = <T = any>(p: string) => send<T>("DELETE", p);

export async function upload<T = any>(path: string, form: FormData): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { method: "POST", headers: { "x-audienceos": "1" }, body: form });
  } catch {
    throw new ApiError("Can't reach the AudienceOS engine. Is it still running?", 0);
  }
  return handle(res);
}

export function errText(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}
