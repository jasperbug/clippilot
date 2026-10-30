import type { Env, NormalizedEvent } from "./relay.js";
import type { TestEvent } from "./relay.js";
import { ConfigError, empty, forwardOr5xx, hmacHex, markSeen, safeEqual, seenRecently, text, webhookUrl } from "./relay.js";

const MAX_AGE_MS = 10 * 60 * 1000;

export async function handleTwitch(req: Request, env: Env = process.env, f: typeof fetch = fetch, now = Date.now()): Promise<Response> {
  if (req.method !== "POST") return empty(405);
  try { webhookUrl(env); } catch (e) { console.error("config error:", (e as Error).message); return text("relay misconfigured: " + (e as ConfigError).message, 500); }
  const secret = env.TWITCH_EVENTSUB_SECRET;
  if (!secret) return text("secret not configured", 500);
  const h = req.headers;
  const id = h.get("twitch-eventsub-message-id"), ts = h.get("twitch-eventsub-message-timestamp");
  const sig = h.get("twitch-eventsub-message-signature"), type = h.get("twitch-eventsub-message-type");
  const body = await req.text();
  if (!id || !ts || !sig) return empty(403);
  if (!safeEqual("sha256=" + hmacHex("sha256", secret, id + ts + body), sig)) return text("bad signature", 403);
  if (Math.abs(now - Date.parse(ts)) > MAX_AGE_MS) return text("stale", 403);

  const msg = JSON.parse(body);
  if (type === "webhook_callback_verification") return text(String(msg.challenge));
  if (type === "revocation") { console.warn("eventsub revoked:", msg.subscription?.status); return empty(); }
  if (type !== "notification") return empty();
  if (seenRecently(id, now)) { console.log("duplicate message_id dropped", id); return empty(); }

  // 受保護測試路徑：HMAC 已驗證，body 帶 grokbot_test 標記 → 只轉發測試事件，不觸發回放處理。
  if (typeof msg.grokbot_test === "string" && msg.grokbot_test) {
    const t: TestEvent = { test: true, test_id: msg.grokbot_test.slice(0, 100), source: "twitch", message_id: id, received_at: new Date(now).toISOString() };
    const fail = await forwardOr5xx(t, env, f); if (fail) return fail;
    markSeen(id, now); return empty();
  }
  if (msg.subscription?.type !== "stream.offline") return empty();
  const allowed = env.TWITCH_BROADCASTER_ID;
  if (allowed && msg.event?.broadcaster_user_id !== allowed) return empty();

  const ev: NormalizedEvent = {
    source: "twitch", event: "stream.offline", event_id: id, received_at: new Date(now).toISOString(),
    channel: { id: msg.event?.broadcaster_user_id ?? null, login: msg.event?.broadcaster_user_login ?? null, name: msg.event?.broadcaster_user_name ?? null },
    video: null, relay_guard: "unchecked_bot_must_verify", message_id: id,
  };
  const fail = await forwardOr5xx(ev, env, f); if (fail) return fail;
  markSeen(id, now); return empty();
}
