#!/usr/bin/env python3
"""聊天室反應剪輯偵測。輸入 JSON/JSONL：[{"t": 秒數, "user": "...", "text": "..."}]
用法：python peaks.py chat.json --vod-url URL --platform twitch --top 8"""
import argparse, json, math, re, statistics
from collections import Counter, defaultdict

BIN = 20; WIN = 60; LEAD = 45; OPENING = 15 * 60
OPENING_WEIGHT = 0.5; DOMINANCE = 0.5; MIN_RATE = 1.0; SPAM_MIN_MSGS = 8
SEED_WORDS = {"twitch": ["笑死", "幹", "LUL", "cmonBruh", "草", "哈哈"],
              "youtube": ["好", ":face-blue-smiling:", "888", "幹", "哈哈", "笑死", "草"]}
SEVEN = re.compile(r"^7{1,}$|^7+[!！]*$")
EMOTE = re.compile(r":[\w-]+:|\b[A-Z][a-z]+[A-Z]\w*\b")  # :yt-emote: 或 Twitch 駝峰表情

def fmt(s): s = int(max(0, s)); return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"

def link(url, s, platform):
    if not url: return None
    s = int(max(0, s))
    if platform == "twitch": return f"{url}?t={s//3600}h{s%3600//60}m{s%60}s"
    return f"{url}{'&' if '?' in url else '?'}t={s}s"

def tokens(text):
    t = text.strip()
    if SEVEN.match(t): return ["7"]
    out = EMOTE.findall(t)
    out += re.findall(r"[\u4e00-\u9fff]{1,2}|[A-Za-z]+|\d+|[?？!！]", EMOTE.sub(" ", t))
    return out

def learn_reaction_words(msgs, platform, k=15, extra=()):
    """反應詞 = 種子詞 + 本場高頻短 token（短訊息、多人使用）。"""
    users_by_tok = defaultdict(set)
    for m in msgs:
        if len(m["text"]) <= 8:
            for tk in set(tokens(m["text"])): users_by_tok[tk].add(m["user"])
    learned = [tk for tk, us in sorted(users_by_tok.items(), key=lambda x: -len(x[1])) if len(us) >= 3][:k]
    return set(SEED_WORDS.get(platform, [])) | set(extra) | set(learned) | {"7"}

def is_reaction(text, words):
    t = text.strip()
    return bool(SEVEN.match(t)) or any(w in t for w in words)

def spam_warnings(msgs, window=WIN):
    """單一觀眾在任一 60 秒視窗佔 ≥50% 且 ≥8 則 → 只提醒，不處罰。"""
    warns, msgs = {}, sorted(msgs, key=lambda m: m["t"])
    j = 0
    for i, m in enumerate(msgs):
        while msgs[j]["t"] < m["t"] - window: j += 1
        c = Counter(x["user"] for x in msgs[j:i+1]); u, n = c.most_common(1)[0]
        tot = i + 1 - j
        if n >= SPAM_MIN_MSGS and n / tot >= DOMINANCE:
            w = warns.setdefault(u, {"user": u, "first": m["t"], "max_share": 0, "max_count": 0})
            w["max_share"] = max(w["max_share"], round(n / tot, 2)); w["max_count"] = max(w["max_count"], n)
    return [dict(w, first=fmt(w["first"])) for w in warns.values()]

def analyze(msgs, platform="twitch", vod_url=None, top=8, duration=None, extra_words=()):
    msgs = sorted(msgs, key=lambda m: m["t"])
    if not msgs: return {"status": "聊天反應不足", "reason": "no messages", "spam_warnings": []}
    dur = duration or (msgs[-1]["t"] + 1)
    rate = len(msgs) / (dur / 60)
    base = {"platform": platform, "messages": len(msgs), "unique_users": len({m['user'] for m in msgs}),
            "duration": fmt(dur), "msgs_per_min": round(rate, 2), "spam_warnings": spam_warnings(msgs)}
    if rate < MIN_RATE:
        return {**base, "status": "聊天反應不足", "candidates": []}
    words = learn_reaction_words(msgs, platform, extra=extra_words)
    nb = int(math.ceil(dur / BIN)); bins = [[] for _ in range(nb)]
    for m in msgs: bins[min(int(m["t"] // BIN), nb - 1)].append(m)
    per = WIN // BIN  # 3 個 20 秒格 = 60 秒滑動視窗（步進 20 秒）
    scores = []
    for i in range(nb):
        win = [m for b in bins[i:i+per] for m in b]
        if not win: scores.append((0, {})); continue
        users = Counter(m["user"] for m in win)
        react = sum(1 for m in win if is_reaction(m["text"], words))
        top_share = users.most_common(1)[0][1] / len(win)
        raw = len(users) * (1 + react / len(win))  # 以不重複發言人數為主，反應詞比例加成
        w = OPENING_WEIGHT if i * BIN < OPENING else 1.0
        if top_share >= DOMINANCE: w *= 0.2  # 單一觀眾主導 → 強烈降權
        scores.append((raw * w, {"n": len(win), "uniq": len(users), "react": react, "top_share": round(top_share, 2), "opening": i * BIN < OPENING}))
    vals = [s for s, _ in scores]
    mu = statistics.mean(vals); sd = statistics.pstdev(vals) or 1
    order = sorted(range(nb), key=lambda i: -vals[i]); picked = []
    for i in order:
        if vals[i] <= mu or len(picked) >= top: break
        if any(abs(i - p) < per * 2 for p in picked): continue  # 相鄰峰值合併（2 分鐘內）
        picked.append(i)
    cands = []
    for i in picked:
        s, info = scores[i]; t0 = i * BIN
        win = [m for b in bins[i:i+per] for m in b]
        rep, seen = [], set()
        for m in sorted(win, key=lambda m: (not is_reaction(m["text"], words), m["t"])):
            if m["user"] in seen: continue
            seen.add(m["user"]); rep.append(f"[{fmt(m['t'])}] {m['user']}: {m['text']}")
            if len(rep) >= 6: break
        start = t0 - LEAD
        cands.append({"peak_time": fmt(t0), "clip_start": fmt(start), "clip_end": fmt(t0 + WIN + 15),
                      "link": link(vod_url, start, platform), "score": round(s, 2), "z": round((s - mu) / sd, 2),
                      **info, "flags": (["single_viewer_dominated"] if info["top_share"] >= DOMINANCE else []) + (["opening_15min"] if info["opening"] else []),
                      "type": "TODO_AI", "music_copyright_risk": "TODO_AI", "representative_messages": rep})
    return {**base, "status": "ok", "reaction_words": sorted(words), "candidates": cands}

def load(path):
    txt = open(path, encoding="utf-8").read().strip()
    return json.loads(txt) if txt.startswith("[") else [json.loads(l) for l in txt.splitlines() if l.strip()]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("chat"); ap.add_argument("--platform", default="twitch", choices=["twitch", "youtube"])
    ap.add_argument("--vod-url"); ap.add_argument("--top", type=int, default=8); ap.add_argument("--duration", type=float)
    a = ap.parse_args()
    print(json.dumps(analyze(load(a.chat), a.platform, a.vod_url, a.top, a.duration), ensure_ascii=False, indent=1))
