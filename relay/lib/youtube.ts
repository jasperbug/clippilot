import type { Env, NormalizedEvent } from "./relay.js";
import { empty, forwardOr5xx, hmacHex, safeEqual, text } from "./relay.js";

export interface AtomEntry { id: string; channel_id: string | null; title: string | null; published: string | null; updated: string | null }

export function parseAtom(xml: string): AtomEntry[] {
  const out: AtomEntry[] = [];
  for (const m of xml.matchAll(/<entry>([\s\S]*?)<\/entry>/g)) {
    const g = (re: RegExp) => m[1].match(re)?.[1] ?? null;
    const id = g(/<yt:videoId>([^<]+)<\/yt:videoId>/);
    if (id) out.push({ id, channel_id: g(/<yt:channelId>([^<]+)<\/yt:channelId>/), title: g(/<title>([^<]*)<\/title>/),
      published: g(/<published>([^<]+)<\/published>/), updated: g(/<updated>([^<]+)<\/updated>/) });
  }
  return out;
}

export async function handleYouTube(req: Request, env: Env = process.env, f: typeof fetch = fetch, now = Date.now()): Promise<Response> {
  const allowed = env.YOUTUBE_CHANNEL_ID;
  if (req.method === "GET") {
    const q = new URL(req.url).searchParams;
    const challenge = q.get("hub.challenge"), topic = q.get("hub.topic") ?? "";
    if (!challenge) return empty(400);
    if (allowed && !topic.includes(`channel_id=${allowed}`)) return empty(404);
    return text(challenge);
  }
  if (req.method !== "POST") return empty(405);
  const body = await req.text();
  const secret = env.YOUTUBE_WEBSUB_SECRET;
  if (secret) {
    const [algo, hex] = (req.headers.get("x-hub-signature") ?? "").split("=");
    // WebSub 規範：簽章不符仍回 2xx，但必須丟棄
    if (!["sha1", "sha256", "sha384", "sha512"].includes(algo) || !hex || !safeEqual(hmacHex(algo, secret, body), hex)) {
      console.warn("bad websub signature, dropped"); return empty();
    }
  }
  for (const e of parseAtom(body)) {
    if (allowed && e.channel_id !== allowed) continue;
    const ev: NormalizedEvent = {
      source: "youtube", event: "upload_feed", event_id: `${e.id}:${e.updated}`, received_at: new Date(now).toISOString(),
      channel: { id: e.channel_id }, video: { id: e.id, url: `https://www.youtube.com/watch?v=${e.id}`, title: e.title, published: e.published, updated: e.updated },
      relay_guard: "unchecked_bot_must_verify",
    };
    { const fail = await forwardOr5xx(ev, env, f); if (fail) return fail; }
  }
  return empty();
}
