// 全部為假資料（FAKE）
import { test } from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { handleTwitch } from "../lib/twitch.js";
import { handleYouTube } from "../lib/youtube.js";
import { _resetSeen, webhookUrl } from "../lib/relay.js";

const env = { TWITCH_EVENTSUB_SECRET: "FAKE_SECRET_123", YOUTUBE_WEBSUB_SECRET: "FAKE_YT", YOUTUBE_CHANNEL_ID: "UCfake",
  TWITCH_BROADCASTER_ID: "111", GROKBOT_WEBHOOK_URL: "https://fake.invalid/hook", GROKBOT_WEBHOOK_AUTH: "FAKE_AUTH_VALUE" };
function spy() { const calls: { url: string; init: RequestInit }[] = []; const f = (async (url: any, init: any) => { calls.push({ url, init }); return new Response(null, { status: 200 }); }) as typeof fetch; return { calls, f }; }
const now = Date.parse("2026-10-30T05:00:00Z"), ts = new Date(now).toISOString();
function tw(type: string, body: object, id = "m1", sig?: string) {
  const b = JSON.stringify(body);
  const s = sig ?? "sha256=" + crypto.createHmac("sha256", env.TWITCH_EVENTSUB_SECRET).update(id + ts + b).digest("hex");
  return new Request("https://x/api/twitch", { method: "POST", body: b, headers: { "twitch-eventsub-message-id": id,
    "twitch-eventsub-message-timestamp": ts, "twitch-eventsub-message-signature": s, "twitch-eventsub-message-type": type } });
}
const offline = { subscription: { type: "stream.offline" }, event: { broadcaster_user_id: "111", broadcaster_user_login: "fake_streamer", broadcaster_user_name: "Fake" } };

test("twitch challenge", async () => {
  const r = await handleTwitch(tw("webhook_callback_verification", { challenge: "FAKE-CH" }), env, spy().f, now);
  assert.equal(r.status, 200); assert.equal(await r.text(), "FAKE-CH");
});
test("twitch bad signature", async () => {
  const s = spy(); const r = await handleTwitch(tw("notification", offline, "m1", "sha256=bad"), env, s.f, now);
  assert.equal(r.status, 403); assert.equal(s.calls.length, 0);
});
test("twitch stale", async () => {
  const r = await handleTwitch(tw("notification", offline), env, spy().f, now + 11 * 60 * 1000); assert.equal(r.status, 403);
});
test("twitch offline forwards with Authorization", async () => {
  const s = spy(); const r = await handleTwitch(tw("notification", offline, "m2"), env, s.f, now);
  assert.equal(r.status, 204); assert.equal(s.calls.length, 1);
  assert.equal((s.calls[0].init.headers as any).authorization, "FAKE_AUTH_VALUE");
  const p = JSON.parse(String(s.calls[0].init.body)); assert.equal(p.channel.login, "fake_streamer"); assert.equal(p.video, null);
});
test("twitch other broadcaster ignored", async () => {
  const s = spy(); await handleTwitch(tw("notification", { ...offline, event: { broadcaster_user_id: "999" } }), env, s.f, now);
  assert.equal(s.calls.length, 0);
});
test("youtube challenge + topic check", async () => {
  const ok = await handleYouTube(new Request("https://x/api/youtube?hub.challenge=YT-FAKE&hub.topic=" + encodeURIComponent("https://www.youtube.com/xml/feeds/videos.xml?channel_id=UCfake")), env);
  assert.equal(ok.status, 200); assert.equal(await ok.text(), "YT-FAKE");
  const bad = await handleYouTube(new Request("https://x/api/youtube?hub.challenge=1&hub.topic=channel_id=UCother"), env);
  assert.equal(bad.status, 404);
});
const atom = `<feed><entry><yt:videoId>FAKEvid0001</yt:videoId><yt:channelId>UCfake</yt:channelId><title>FAKE</title><published>2026-10-30T00:00:00Z</published><updated>2026-10-30T01:00:00Z</updated></entry></feed>`;
test("youtube signed notification forwards", async () => {
  const s = spy(); const sig = "sha1=" + crypto.createHmac("sha1", "FAKE_YT").update(atom).digest("hex");
  const r = await handleYouTube(new Request("https://x/api/youtube", { method: "POST", body: atom, headers: { "x-hub-signature": sig } }), env, s.f, now);
  assert.equal(r.status, 204); assert.equal(s.calls.length, 1);
  assert.equal(JSON.parse(String(s.calls[0].init.body)).video.id, "FAKEvid0001");
});
test("youtube bad signature dropped with 2xx", async () => {
  const s = spy(); const r = await handleYouTube(new Request("https://x/api/youtube", { method: "POST", body: atom, headers: { "x-hub-signature": "sha1=00" } }), env, s.f, now);
  assert.equal(r.status, 204); assert.equal(s.calls.length, 0);
});

const status = (n: number) => (async () => new Response(null, { status: n })) as typeof fetch;
test("bad webhook url -> 500, no fetch", async () => {
  _resetSeen(); const s = spy();
  const r = await handleTwitch(tw("notification", offline, "u1"), { ...env, GROKBOT_WEBHOOK_URL: "not a url" }, s.f, now);
  assert.equal(r.status, 500); assert.equal(s.calls.length, 0); assert.doesNotMatch(await r.text(), /not a url/);
});
test("webhook url trimmed / unquoted", () => {
  assert.equal(webhookUrl({ GROKBOT_WEBHOOK_URL: '  "https://fake.invalid/hook"\n' }), "https://fake.invalid/hook");
  assert.throws(() => webhookUrl({}));
});
test("routine non-2xx -> 502 so Twitch retries; retry then succeeds", async () => {
  _resetSeen();
  assert.equal((await handleTwitch(tw("notification", offline, "r1"), env, status(500), now)).status, 502);
  const s = spy(); assert.equal((await handleTwitch(tw("notification", offline, "r1"), env, s.f, now)).status, 204);
  assert.equal(s.calls.length, 1);
});
test("fetch throws -> 502", async () => {
  _resetSeen(); const f = (async () => { throw new Error("boom"); }) as typeof fetch;
  assert.equal((await handleTwitch(tw("notification", offline, "r2"), env, f, now)).status, 502);
});
test("payload carries message_id; duplicate dropped", async () => {
  _resetSeen(); const s = spy();
  await handleTwitch(tw("notification", offline, "d1"), env, s.f, now);
  const r2 = await handleTwitch(tw("notification", offline, "d1"), env, s.f, now);
  assert.equal(r2.status, 204); assert.equal(s.calls.length, 1);
  assert.equal(JSON.parse(String(s.calls[0].init.body)).message_id, "d1");
});
test("signed test marker forwards test event only", async () => {
  _resetSeen(); const s = spy();
  const r = await handleTwitch(tw("notification", { grokbot_test: "T-123", subscription: { type: "stream.offline" }, event: offline.event }, "t1"), env, s.f, now);
  assert.equal(r.status, 204); assert.equal(s.calls.length, 1);
  const p = JSON.parse(String(s.calls[0].init.body));
  assert.deepEqual([p.test, p.test_id, p.message_id], [true, "T-123", "t1"]); assert.equal(p.event, undefined);
});
test("unsigned test marker rejected", async () => {
  _resetSeen(); const s = spy();
  const r = await handleTwitch(tw("notification", { grokbot_test: "X" }, "t2", "sha256=bad"), env, s.f, now);
  assert.equal(r.status, 403); assert.equal(s.calls.length, 0);
});
test("youtube forward failure -> 502", async () => {
  const sig = "sha1=" + crypto.createHmac("sha1", "FAKE_YT").update(atom).digest("hex");
  const r = await handleYouTube(new Request("https://x/api/youtube", { method: "POST", body: atom, headers: { "x-hub-signature": sig } }), env, status(503), now);
  assert.equal(r.status, 502);
});
