"""取聊天記錄（不登入）。解析邏輯沿用早期已驗證原型。"""
import json, os, shutil, subprocess, time

def _tdcli():
    """TwitchDownloaderCLI 位置：環境變數 TWITCH_DOWNLOADER_CLI，否則從 PATH 找；都沒有就清楚報錯。"""
    p = os.environ.get("TWITCH_DOWNLOADER_CLI") or shutil.which("TwitchDownloaderCLI")
    if not p: raise RuntimeError("找不到 TwitchDownloaderCLI：請放進 PATH 或設定 TWITCH_DOWNLOADER_CLI")
    return p
YTDLP = os.environ.get("YTDLP") or shutil.which("yt-dlp") or "yt-dlp"

def _run(cmd, timeout=900):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0: raise RuntimeError(f"{cmd[0]} failed: {p.stderr[-500:]}")
    return p.stdout

def video_meta(platform, vid):
    """用 yt-dlp 取影片資訊（不下載）。Twitch: was_live 由 GQL broadcastType==ARCHIVE 推得。"""
    url = f"https://www.twitch.tv/videos/{vid}" if platform == "twitch" else f"https://www.youtube.com/watch?v={vid}"
    d = json.loads(_run([YTDLP, "-J", "--skip-download", "--no-warnings", url], 180))
    m = {"id": str(vid), "url": url, "title": d.get("title"), "description": d.get("description") or "",
         "duration": d.get("duration"), "live_status": d.get("live_status"), "was_live": d.get("was_live"),
         "is_live": d.get("is_live"), "timestamp": d.get("timestamp"), "release_timestamp": d.get("release_timestamp")}
    if platform == "twitch": m["type"] = "archive" if d.get("was_live") else "other"
    return m

def latest_twitch_archive(login, max_age_s=6 * 3600):
    """收台後找最新 archive VOD（不登入）。找不到回傳 None。"""
    out = _run([YTDLP, "-J", "--flat-playlist", "--playlist-end", "3", "--no-warnings",
                f"https://www.twitch.tv/{login}/videos?filter=archives&sort=time"], 120)
    for e in json.loads(out).get("entries") or []:
        vid = str(e.get("id", "")).lstrip("v")
        ts = e.get("timestamp")
        if vid and (ts is None or time.time() - ts < max_age_s): return vid
    return None

def _flat(url, n):
    out = _run([YTDLP, "-J", "--flat-playlist", "--playlist-end", str(n), "--no-warnings", url], 180)
    return json.loads(out).get("entries") or []

def channel_url_youtube(channel):
    c = channel.strip()
    if c.startswith("http"): base = c.rstrip("/").removesuffix("/streams").removesuffix("/videos")
    elif c.startswith("UC") and len(c) == 24: base = f"https://www.youtube.com/channel/{c}"
    else: base = "https://www.youtube.com/" + (c if c.startswith("@") else "@" + c)
    return base + "/streams"

def list_youtube_streams(channel, n=5):
    """頻道 /streams 分頁最近 n 支（只是候選，守門另外做）。"""
    return [str(e["id"]) for e in _flat(channel_url_youtube(channel), n) if e.get("id")]

def list_twitch_archives(login, n=5):
    return [str(e["id"]).lstrip("v") for e in _flat(f"https://www.twitch.tv/{login}/videos?filter=archives&sort=time", n) if e.get("id")]

def twitch_chat(vid, workdir):
    path = os.path.join(workdir, f"twitch_{vid}.chat.json")
    if not os.path.exists(path):
        _run([_tdcli(), "chatdownload", "--id", str(vid), "-o", path, "--banner", "false"], 1800)
    d = json.load(open(path, encoding="utf-8"))
    return [{"t": float(c["content_offset_seconds"]), "user": c["commenter"].get("display_name") or c["commenter"].get("name"),
             "text": c["message"]["body"]} for c in d["comments"]]

def youtube_chat(vid, workdir):
    base = os.path.join(workdir, f"yt_{vid}")
    path = base + ".live_chat.json"
    if not os.path.exists(path):
        _run([YTDLP, "--skip-download", "--write-subs", "--sub-langs", "live_chat", "--no-warnings",
              "-o", base + ".%(ext)s", f"https://www.youtube.com/watch?v={vid}"], 1800)
    ms = []
    for l in open(path, encoding="utf-8"):
        a = json.loads(l).get("replayChatItemAction")
        if not a: continue
        off = int(a.get("videoOffsetTimeMsec", 0)) / 1000
        for x in a.get("actions", []):
            v = x.get("addChatItemAction", {}).get("item", {}).get("liveChatTextMessageRenderer")
            if not v: continue  # 付費留言、會員等非文字項目略過
            txt = "".join(r.get("text") or (":" + r["emoji"].get("shortcuts", ["?"])[0].strip(":") + ":" if "emoji" in r else "")
                          for r in v["message"]["runs"])
            ms.append({"t": off, "user": v.get("authorName", {}).get("simpleText", v.get("authorExternalChannelId")), "text": txt})
    return ms
