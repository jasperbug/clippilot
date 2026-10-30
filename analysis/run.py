#!/usr/bin/env python3
"""單一入口：列出候選 → 守門（直播回放／非 bot 自產／未處理）→ 抓聊天 → 分析 → 印 JSON。
  python3 run.py --platform youtube --id <videoId>
  python3 run.py --platform twitch  --id <vodId>
  python3 run.py --platform twitch  --channel <login>  [--initial-wait 300 --retries 4]   # 收台 webhook 用
  python3 run.py --platform twitch  --channel <login>  --poll                            # 定時輪詢
  python3 run.py --platform youtube --channel <@handle|URL|UC…> --poll
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re
import fetch
from filters import ProcessedStore, poll_gate, should_process
from peaks import analyze

FAIL_REPORT_AT = 2

def log(*a): print(*a, file=sys.stderr, flush=True)

class FailureCounter:
    """連續抓取失敗計數（每平台），成功歸零；達 2 次才 report_failure。"""
    def __init__(self, state_dir, platform, dry_run=False):
        self.path, self.p, self.dry = os.path.join(state_dir, "fetch_failures.json"), platform, dry_run
        self.d = json.load(open(self.path)) if os.path.exists(self.path) else {}
    def _save(self):
        if not self.dry: json.dump(self.d, open(self.path, "w"), indent=1)
    def fail(self, err):
        self.d[self.p] = {"count": self.d.get(self.p, {}).get("count", 0) + 1, "last_error": str(err)[-300:], "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        self._save(); return self.d[self.p]["count"]
    def ok(self):
        if self.d.get(self.p, {}).get("count"): self.d[self.p] = {"count": 0}; self._save()

def process(a, vid, store, own, extra):
    """回傳 (result_dict, processed_bool)。守門未過回傳 skipped。"""
    meta = fetch.video_meta(a.platform, vid)
    if a.poll and not a.force:
        ok, why = poll_gate(meta, time.time())
        if not ok: return {"status": "skipped", "reason": why, "video": meta["id"]}, False  # 不寫 processed，下輪再看
    ok, why = (True, "forced") if a.force else should_process(a.platform, meta, store, own)
    if not ok: return {"status": "skipped", "reason": why, "video": meta["id"]}, False
    if getattr(a, "check_only", False): return {"status": "would_process", "video": meta["id"]}, True
    cache = os.path.join(a.state_dir, "cache")
    msgs = fetch.twitch_chat(vid, cache) if a.platform == "twitch" else fetch.youtube_chat(vid, cache)
    res = analyze(msgs, a.platform, meta["url"], a.top, meta.get("duration"), extra)
    res["video"] = {k: meta.get(k) for k in ("id", "url", "title", "live_status")}
    if not a.dry_run: store.add(f"{a.platform}:{vid}")
    return res, True

def log_youtube_failure(a, vid, err):
    """YouTube 單支影片抓取失敗：逐筆附加到 <state-dir>/youtube_failures.log。--dry-run／--check-only 不寫。"""
    if a.platform != "youtube" or a.dry_run: return
    msg = " ".join(str(err).split())[-200:]
    with open(os.path.join(a.state_dir, "youtube_failures.log"), "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')}\t{vid}\t{msg}\n")

def normalize_id(platform, raw):
    """接受純 ID 或完整網址（twitch.tv/videos/<id>、youtube.com/watch?v=、youtu.be/、/live/、/shorts/）。"""
    r = raw.strip()
    if platform == "twitch":
        m = re.search(r"twitch\.tv/(?:[^/]+/)?videos?/v?(\d+)", r) or re.fullmatch(r"v?(\d+)", r)
    else:
        m = (re.search(r"[?&]v=([\w-]{11})", r) or re.search(r"youtu\.be/([\w-]{11})", r)
             or re.search(r"youtube\.com/(?:live|shorts|embed)/([\w-]{11})", r) or re.fullmatch(r"([\w-]{11})", r))
    if not m: raise ValueError(f"無法辨識的 {platform} 影片 ID／網址: {raw}")
    return m.group(1)

def init_channel(a, store, own):
    """把目前頻道上合格的回放標成已處理（不分析），避免第一次輪詢補跑舊場次。"""
    marked, skipped = [], []
    for vid in list_candidates(a):
        if store.seen(f"{a.platform}:{vid}"): continue
        ok, why = should_process(a.platform, fetch.video_meta(a.platform, vid), store, own)
        if ok:
            marked.append(vid)
            if not a.dry_run: store.add(f"{a.platform}:{vid}")
        else: skipped.append({"video": vid, "reason": why})
    return {"status": "initialized", "platform": a.platform, "channel": a.channel, "marked_count": len(marked),
            "marked": marked, "skipped": skipped, "dry_run": a.dry_run}

def list_candidates(a):
    if a.platform == "twitch": return fetch.list_twitch_archives(a.channel, a.recent)
    return fetch.list_youtube_streams(a.channel, a.recent)

def run(a):
    os.makedirs(os.path.join(a.state_dir, "cache"), exist_ok=True)
    own_path = a.own_uploads or os.path.join(a.state_dir, "own_uploads.json")
    own = json.load(open(own_path)) if os.path.exists(own_path) else []
    rw_path = os.path.join(a.state_dir, "reaction_words.json")
    extra = [w for w in a.reaction_words.split(",") if w] + (json.load(open(rw_path)) if os.path.exists(rw_path) else [])
    store = ProcessedStore(os.path.join(a.state_dir, "processed.json"))
    if a.id:
        vid = normalize_id(a.platform, a.id)
        try: return process(a, vid, store, own, extra)[0]
        except Exception as e: log_youtube_failure(a, vid, e); raise
    if a.init: return init_channel(a, store, own)

    if a.initial_wait: time.sleep(a.initial_wait)
    results, errors = [], []
    for i in range(a.retries + 1):
        for vid in list_candidates(a):
            if store.seen(f"{a.platform}:{vid}"): continue  # 便宜的預先去重；should_process 仍會再檢查
            try: res, done = process(a, vid, store, own, extra)
            except Exception as e:  # 單支失敗不中斷整批；下次輪詢會再試（未寫入 processed）
                log_youtube_failure(a, vid, e)
                errors.append({"video": vid, "error": str(e)[-300:]}); log("error", vid, str(e)[-200:]); continue
            if done:
                results.append(res)
                if not a.poll: break
            else: log("skip", vid, res["reason"])
        if results or i == a.retries: break
        log(f"沒有新的回放，{a.retry_wait}s 後重試（{i+1}/{a.retries}）"); time.sleep(a.retry_wait)
    if errors and not results:
        raise RuntimeError(f"{len(errors)} video(s) failed: " + errors[0]["error"])
    if not results: return {"status": "no_new_video", "platform": a.platform, "channel": a.channel}
    if errors: results.append({"status": "partial_errors", "errors": errors})
    return results if a.poll else results[0]

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True, choices=["twitch", "youtube"])
    ap.add_argument("--id"); ap.add_argument("--channel", help="Twitch login，或 YouTube @handle／URL／UC 頻道 ID")
    ap.add_argument("--init", action="store_true", help="搭配 --channel：把現有合格回放記為已處理，不分析")
    ap.add_argument("--poll", action="store_true", help="處理所有新的合格影片，輸出 JSON 陣列")
    ap.add_argument("--recent", type=int, default=5, help="每次檢查最近幾支")
    ap.add_argument("--retries", type=int, default=0); ap.add_argument("--retry-wait", type=int, default=300)
    ap.add_argument("--initial-wait", type=int, default=0)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--state-dir", default=os.path.expanduser("~/.streamer-copilot"))
    ap.add_argument("--own-uploads"); ap.add_argument("--reaction-words", default="")
    ap.add_argument("--dry-run", action="store_true", help="不寫入 processed.json／fetch_failures.json")
    ap.add_argument("--check-only", action="store_true", help="只列出會處理哪些影片，不抓聊天、不分析；隱含 --dry-run")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.check_only: a.dry_run = True
    if not a.id and not a.channel: ap.error("需要 --id 或 --channel")
    if a.init and (a.id or not a.channel): ap.error("--init 需要 --channel，且不能和 --id 一起用")
    os.makedirs(a.state_dir, exist_ok=True)
    fc = FailureCounter(a.state_dir, a.platform, a.dry_run)
    try:
        out = run(a); fc.ok()
    except ValueError as e:  # 使用者給錯 ID／網址，不算抓取失敗
        out = {"status": "invalid_id", "error": str(e)}
    except Exception as e:  # 抓取／解析失敗
        n = fc.fail(e)
        out = {"status": "fetch_error", "platform": a.platform, "consecutive_failures": n,
               "report_failure": n >= FAIL_REPORT_AT, "error": str(e)[-300:]}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return out

if __name__ == "__main__": main()
