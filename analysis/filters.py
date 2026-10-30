"""Bot 層守門：只處理直播回放 + 去重 + 排除 bot 自產影片。"""
import json, os, tempfile

BOT_MARKER = "#streamer-copilot-clip"  # bot 產出影片描述中加入此標記（待決：辨識方式）

def is_twitch_archive(vod: dict) -> bool:
    return (vod or {}).get("type") == "archive"

def is_youtube_live_archive(video: dict) -> bool:
    v = video or {}
    if v.get("live_status") == "was_live":  # yt-dlp 欄位
        return True
    lsd = v.get("liveStreamingDetails") or v.get("live_streaming_details")  # Data API 欄位
    return bool(lsd and lsd.get("actualEndTime"))

def is_bot_generated(video: dict, own_upload_ids=()) -> bool:
    v = video or {}
    return v.get("id") in set(own_upload_ids) or BOT_MARKER in (v.get("description") or "")

class ProcessedStore:
    def __init__(self, path):
        self.path = path
        self.ids = set(json.load(open(path))) if os.path.exists(path) else set()
    def seen(self, key): return key in self.ids
    def add(self, key):
        self.ids.add(key)
        d = os.path.dirname(os.path.abspath(self.path)); fd, tmp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "w") as f: json.dump(sorted(self.ids), f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)  # 原子寫入

def should_process(platform, video, store: ProcessedStore, own_upload_ids=()):
    """回傳 (bool, reason)。key 用 platform:video_id，WebSub 更新重送時會被擋下。"""
    ok = is_twitch_archive(video) if platform == "twitch" else is_youtube_live_archive(video) if platform == "youtube" else False
    if not ok: return False, "not_live_archive"
    if is_bot_generated(video, own_upload_ids): return False, "bot_generated"
    key = f"{platform}:{video.get('id')}"
    if store.seen(key): return False, "duplicate"
    return True, "ok"

FRESH_WAIT_S = 10 * 60
LIVE_STATES = {"is_live", "is_upcoming", "post_live"}

def poll_gate(video: dict, now: float, wait_s: int = FRESH_WAIT_S):
    """--poll 專用：直播中跳過；回放結束（開始時間+長度）不到 wait_s 秒則留到下一輪。皆不寫入 processed。
    Twitch 直播中的 VOD 長度會跟著成長，結束時間≈現在，也會被「太新」擋下。"""
    v = video or {}
    if v.get("is_live") or v.get("live_status") in LIVE_STATES: return False, "live_now"
    start = v.get("release_timestamp") or v.get("timestamp")
    if start is not None and now - (start + (v.get("duration") or 0)) < wait_s: return False, "too_fresh"
    return True, "ok"
