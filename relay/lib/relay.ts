import crypto from "node:crypto";

export type Env = Record<string, string | undefined>;

export interface NormalizedEvent {
  source: "twitch" | "youtube";
  event: "stream.offline" | "upload_feed";
  event_id: string;
  received_at: string;
  channel: { id: string | null; login?: string | null; name?: string | null };
  video: { id: string; url: string; title: string | null; published: string | null; updated: string | null } | null;
  /** 中繼站不查 VOD／直播狀態；bot 端必須自行檢查是否為直播回放。 */
  relay_guard: "unchecked_bot_must_verify";
  /** Twitch-Eventsub-Message-Id（僅 Twitch）；routine 以此去重。 */
  message_id?: string;
}

export interface TestEvent { test: true; test_id: string; source: "twitch"; message_id: string; received_at: string }

/** 讀取並驗證 GROKBOT_WEBHOOK_URL（去除前後空白與引號）；格式錯誤丟出不含網址內容的錯誤。 */
export function webhookUrl(env: Env = process.env): string {
  const raw = env.GROKBOT_WEBHOOK_URL;
  if (!raw) throw new ConfigError("GROKBOT_WEBHOOK_URL not set");
  const v = raw.trim().replace(/^["']+|["']+$/g, "").trim();
  let u: URL;
  try { u = new URL(v); } catch { throw new ConfigError(`GROKBOT_WEBHOOK_URL is not a valid URL (length ${raw.length})`); }
  if (u.protocol !== "https:" && u.protocol !== "http:") throw new ConfigError("GROKBOT_WEBHOOK_URL must be http(s)");
  return u.toString();
}
export class ConfigError extends Error { name = "ConfigError"; }
export class ForwardError extends Error { name = "ForwardError"; constructor(public status: number) { super(`forward failed: HTTP ${status}`); } }

/** 盡力去重（同一個 function instance 內）；跨 instance 交給 routine 的 seen_messages.json。 */
const seen = new Map<string, number>();
export function seenRecently(id: string, now = Date.now()): boolean {
  for (const [k, t] of seen) if (now - t > 15 * 60 * 1000) seen.delete(k);
  return seen.has(id);
}
export function markSeen(id: string, now = Date.now()) { seen.set(id, now); }
export function _resetSeen() { seen.clear(); }

export function safeEqual(a: string, b: string): boolean {
  const A = Buffer.from(a), B = Buffer.from(b);
  return A.length === B.length && crypto.timingSafeEqual(A, B);
}

export function hmacHex(algo: string, secret: string, data: string | Buffer): string {
  return crypto.createHmac(algo, secret).update(data).digest("hex");
}

/** 轉發到 Grok Bot routine webhook；GROKBOT_WEBHOOK_AUTH 原樣放進 Authorization 標頭。 */
export async function forward(ev: NormalizedEvent | TestEvent, env: Env = process.env, f: typeof fetch = fetch): Promise<number> {
  const url = webhookUrl(env);
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (env.GROKBOT_WEBHOOK_AUTH) headers.authorization = env.GROKBOT_WEBHOOK_AUTH.trim();
  const r = await f(url, { method: "POST", headers, body: JSON.stringify(ev) });
  if (!r.ok) throw new ForwardError(r.status);
  console.log("forward ok", r.status, "test" in ev ? `test_id=${ev.test_id}` : `event_id=${ev.event_id}`);
  return r.status;
}

/** 轉發並把失敗轉成 5xx，讓上游（Twitch／WebSub）重送。 */
export async function forwardOr5xx(ev: NormalizedEvent | TestEvent, env: Env, f: typeof fetch): Promise<Response | null> {
  try { await forward(ev, env, f); return null; }
  catch (e) {
    if (e instanceof ConfigError) { console.error("config error:", e.message); return text("relay misconfigured: " + e.message, 500); }
    if (e instanceof ForwardError) { console.error(e.message); return text(e.message, 502); }
    console.error("forward error:", (e as Error)?.message); return text("forward error", 502);
  }
}

export const text = (body: string, status = 200) => new Response(body, { status, headers: { "content-type": "text/plain" } });
export const empty = (status = 204) => new Response(null, { status });
