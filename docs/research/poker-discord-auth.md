# 德州撲克：Discord 登入與每日資格複查

查證日期：2026-09-15。對應 [德州撲克：Discord 登入與每日資格複查可行性](https://github.com/icez114514/icez-discord-bot/issues/15)。本文為研究與實作建議，不代表已實作或已完成真實 API 驗證。

## 結論與既定範圍

可行。建議瀏覽器採 Discord authorization code 登入，以 `identify` 取得不可變的 Discord user ID；伺服器用已加入指定 guild 的 Bot 逐人查資格。每日複查不必依賴每位使用者仍有效的 OAuth token。第一版由 Bot 提供網頁連結，不使用 Activity。

既定規則：登入時驗資格；其餘時間不因離群事件即時登出；每日 Asia/Taipei 04:00 掃描有有效本地登入的帳戶。正在打牌者整次跳過，當手結束後不補查，隔日再檢查。合格者保留登入；確認不合格者撤銷所有本地登入。玩家帳戶、獨立德撲籌碼及戰績不刪除。「正在打牌」的完整狀態邊界由牌局決策定義。

## API 選擇

| 方案 | 身分與資格查詢 | 權限與取捨 |
| --- | --- | --- |
| 建議：OAuth 身分＋Bot 查單一成員 | `GET /users/@me` 使用使用者 Bearer；`GET /guilds/{guild.id}/members/{user.id}` 使用 Bot token | 登入只需 `identify`；Bot 部署前須加入目標 guild，避免儲存所有玩家 refresh token。逐人查詢端點未列 `GUILD_MEMBERS` 要求；不要誤用 SDK 的全員 fetch。 |
| 替代：全程使用使用者 OAuth | `GET /users/@me/guilds/{guild.id}/member` | 需 `identify guilds.members.read`；可讀該使用者成員資料，端點未列 Bot 入群要求。每日檢查需要保留並更新 OAuth token。 |
| 全員名單比對 | `GET /guilds/{guild.id}/members`，完整分頁 | 官方明示需要 `GUILD_MEMBERS` privileged intent，單頁上限 1,000。此專案只需查已登入玩家，第一版不建議抓整個伺服器名單。 |

API 與 scope 來源：[User Resource](https://docs.discord.com/developers/resources/user#get-current-user-guild-member)、[Guild Resource](https://docs.discord.com/developers/resources/guild#get-guild-member)、[List Guild Members](https://docs.discord.com/developers/resources/guild#list-guild-members)。單人成員端點未列 privileged intent 是依官方端點規格的判讀；上線前須以實際 Bot 關閉該 intent 驗證，不能以本地 cache 查不到當作離群。

## OAuth 與本地登入分工

官方 code flow 可取得 access token、`expires_in`、refresh token；`expires_in` 以回應值為準，不把範例期限寫死。refresh 仍可能失敗，不能保證永久有效。OAuth 撤銷會使同一 authorization 的相關 token 失效。登入 callback 應驗證一次性 `state`，由後端換 token；Bot 安裝 scope 與玩家登入 scope 分開。[Discord OAuth2](https://docs.discord.com/developers/topics/oauth2)

以下為本系統設計建議：

- 資料庫保存 Discord user ID、顯示資料與本地 session；不保存 Discord 密碼。以 HttpOnly、Secure cookie 持有不透明 session ID，後端保存雜湊。OAuth／Bot token 不交給網頁或寫入記錄。
- 採 Bot 複查後，不需要為每日掃描長期保存使用者 OAuth token；完成登入身分讀取後即可丟棄。若選 OAuth 複查方案，token 須加密保存，refresh 更新採每帳戶互斥並原子替換回傳 token。
- 本地 session 與 Discord access token 的期限分離；token 到期不能當作離群。通過日查不更換或刪除 session。本地登入的閒置／最長期限須在 session 設計中明文定義，不用 Discord token 期限代替，也不宣稱能跨瀏覽器清理永遠保留登入。
- 撤銷登入採帳戶 `session_version` 遞增及 session revoke；HTTP 與 WebSocket 命令都驗證此版本。登出只撤銷本系統登入，不是把玩家踢出 Discord server，也不必撤銷整個 OAuth authorization。

## 日查與錯誤分類

| 結果 | 系統行為 |
| --- | --- |
| 成功取得對應 user／guild 的 member | 記錄 passed，保留 session |
| 單人成員查詢明確回應 `Unknown member`（10007） | 確認 Bot／目標 guild 存取正常後，進入原子撤銷流程 |
| 401、403、Unknown guild、Unknown token、非預期 404 | 判為基礎設施／憑證／存取問題，保留 session；修復或重試，不當作離群 |
| 429、5xx、逾時或無法解析 | 保留 session，依限速或退避重試 |
| OAuth refresh 已失效 | 無法以此證明離群；採 Bot 查詢或標記待恢復驗證，不因這個錯誤踢出登入 |

Discord 將 10007 定義為 Unknown member，10004 為 Unknown guild，10012 為 Unknown token；只有 HTTP 404 不足以識別原因。[官方錯誤碼](https://docs.discord.com/developers/topics/opcodes-and-status-codes#json-json-error-codes)

限速佇列應與同 Bot 的既有 API 用量協調，遵守 bucket／remaining／reset headers，429 遵守 `Retry-After` 或 `retry_after`；不要硬編碼單路由頻率或在 04:00 同時發送所有請求。官方目前列一般 Bot global 上限 50 requests/s，但也明示限制可能變動。401／403 應停止故障範圍的大量重試並通知管理員，避免累積無效請求。[Discord Rate Limits](https://docs.discord.com/developers/topics/rate-limits)

以下為本系統排程建議：

1. 以 Asia/Taipei 日期建立唯一 `(guild_id, audit_date, user_id)` 工作；工作保存排程時間、實際檢查時間、狀態、重試次數及憑證配置版本。04:00 啟動掃描，不宣稱所有 API 於同一瞬間完成。
2. 檢查前在與開手共用的帳戶／牌局同步邊界判定 playing；若成立，寫入 `skipped_playing` 終態。相同日期重跑不可重新檢查該玩家。
3. 非 playing 才向 Discord 查詢；不持有資料庫鎖等待網路。保存查詢開始時的 session version 與牌局版本。
4. 收到明確非成員結果後，再於開手使用的同一鎖／交易邊界驗證 playing 與版本。若玩家已開始手牌，改為 `skipped_playing`，不撤銷、不在結束後補查；若中間曾開手且已結束，採同樣保守跳過，避免競態。
5. 若非 playing 且版本吻合，同一交易撤銷所有本地 session、寫 audit 結果；開手流程亦須在相同邊界驗 session version，防止撤銷與下一手同時成功。若玩家已重新登入造成版本更新，丟棄舊結果並重新判定，不用舊查詢撤銷新登入。
6. 重試只處理可重試失敗；每次重試仍先判 playing。跨到次日則結束前日未完成工作，由新日期工作接手。多 worker 以 lease／唯一鍵防重；停機後補跑只查可恢復的當日工作，不能事後猜測玩家在錯過的 04:00 是否正在打牌。

持續在每日檢查時打牌者可能無限次跳過，這是已選產品規則的結果；此研究不增加手後補查或即時離群踢出。

## 實作驗收清單

- 測試 guild：會員／非會員、Bot 被移除、OAuth 到期、Bot 401、403、429、5xx，只有確定非會員撤銷登入。
- playing 初次檢查與回應提交兩個時點各插入開手，均可跳過且當日不補查；重新登入不得被舊查詢結果撤銷。
- 多 session 撤銷後既有 WebSocket 亦不能操作；合格／跳過／暫時失敗者保留 session 與帳戶資產。
- 同日重跑、多 worker、重啟恢復、跨日重試與時區測試；playing 邊界（棄牌、全下、斷線）依牌局規格補測。
