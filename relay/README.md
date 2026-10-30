# streamer-relay（Vercel Functions, TypeScript）

Twitch EventSub `stream.offline` 與 YouTube WebSub 的中繼站：處理握手、驗簽，轉發正規化 JSON 到 Grok Bot routine webhook。不查 VOD、不查直播狀態，回放判斷由 bot 端負責（`relay_guard: "unchecked_bot_must_verify"`）。

- `api/twitch.ts` → `/api/twitch`：HMAC-SHA256（message_id + timestamp + raw body）、10 分鐘防重放、challenge 回應、revocation 記錄。
- `api/youtube.ts` → `/api/youtube`：GET 回 `hub.challenge`（可限定頻道）；POST 驗 `X-Hub-Signature`，不符回 204 並丟棄。
- `lib/`：共用邏輯（`relay.ts`、`twitch.ts`、`youtube.ts`）；`test/`：node:test 假資料測試。

## 環境變數
| 變數 | 必要 | 說明 |
|---|---|---|
| `GROKBOT_WEBHOOK_URL` | 是 | routine 面板的 Webhook URL |
| `GROKBOT_WEBHOOK_AUTH` | 是 | routine 面板的 Authorization 值，原樣送出為 `Authorization` 標頭 |
| `TWITCH_EVENTSUB_SECRET` | 是 | 10–100 字元隨機字串；建立訂閱時同值 |
| `TWITCH_BROADCASTER_ID` | 建議 | 只轉發此頻道的事件 |
| `YOUTUBE_WEBSUB_SECRET` | 建議 | 訂閱時的 `hub.secret` |
| `YOUTUBE_CHANNEL_ID` | 建議 | 只接受此頻道（UC…）的訂閱與通知 |

## 本機
```
npm install
npm test          # 假資料測試
npm run typecheck
```

## 部署
```
npm i -g vercel
vercel login                     # 使用者本人登入
vercel link                      # 建立／連結專案
for v in GROKBOT_WEBHOOK_URL GROKBOT_WEBHOOK_AUTH TWITCH_EVENTSUB_SECRET TWITCH_BROADCASTER_ID YOUTUBE_WEBSUB_SECRET YOUTUBE_CHANNEL_ID; do vercel env add $v production; done
vercel deploy --prod
```
部署後確認 Deployment Protection 只保護 Preview、不擋 production 的 `/api/*`。注意：不要用 Vercel connector／API 工具寫密鑰類環境變數（值會變成 `[REDACTED]`），請用 Vercel 設定頁或 `vercel env add`（stdin）。完整設定與訂閱步驟見 ClipPilot 的 `clippilot-setup` 技能。

## 簽章測試
```
RELAY_URL=https://<your-relay>/api/twitch ./test/send_signed_test.sh <message_id> <test_id>
```
需要同目錄的 `.relay_secrets.env`（權限 600）。relay 只轉發 `{test: true, test_id}`，不觸發回放處理。
