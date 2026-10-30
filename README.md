# ClipPilot

直播回放「聊天反應」剪輯候選工具。分析 Twitch／YouTube 直播回放的聊天紀錄，找出觀眾反應最熱烈的時間點，列出剪輯候選。只讀取公開聊天資料，不下載影片、不自動發文。

*English: ClipPilot finds clip candidates in Twitch / YouTube live replays by analyzing chat reaction peaks. It reads chat only — no video download, no auto-posting.*

## 需求 Requirements
- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)（YouTube 聊天回放；部分影片可能需要 cookies）
- [TwitchDownloaderCLI](https://github.com/lay295/TwitchDownloader)（Twitch 聊天）：放在 PATH，或設定環境變數 `TWITCH_DOWNLOADER_CLI`

## 用法 Usage
```bash
cd analysis
# 第一次：把頻道現有回放標記為已處理（不分析）
python3 run.py --platform twitch --channel <twitch_login> --init
python3 run.py --platform youtube --channel <@handle 或 UC 頻道 ID> --init

# 只列出會處理哪些影片，不寫任何狀態
python3 run.py --platform twitch --channel <twitch_login> --poll --check-only

# 處理所有新的合格回放，輸出 JSON
python3 run.py --platform twitch --channel <twitch_login> --poll
```
狀態預設存在 `~/.streamer-copilot/`（`--state-dir` 可改）。只處理已結束的直播回放；仍在直播或剛結束不到 10 分鐘的會等下一輪。YouTube 抓取失敗會記在 `youtube_failures.log`。

測試：`cd analysis && python3 tests/test_all.py && python3 tests/test_run.py`

## 進階：webhook relay（選用）
`relay/` 是部署在 Vercel 的 Twitch EventSub／YouTube WebSub 接收器，直播結束時即時通知。設定需要 Twitch app、密鑰與部署，工作量較大；一般建議用每日定時檢查即可。詳見 `relay/README.md`。

*Advanced, optional: `relay/` is a Vercel webhook relay for near-real-time notifications. Daily polling is recommended for most users.*

## License
MIT
