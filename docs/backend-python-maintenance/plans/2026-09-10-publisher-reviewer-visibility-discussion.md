# 發布者可見審核人員與等待原因

狀態：已實作並完成驗證；使用者於 2026-09-10 另行批准 commit／push 到 dev，取代下方原本停在提交前的限制。結果見 `../results/2026-09-10-publisher-reviewer-visibility-verification.md`。

## 最新確認（2026-09-10）

- 使用者確認組織日常審核由 namespace ADMIN 負責，publisher 應能看到該 namespace 全部可 review 的 ADMIN，不指派單一人、不要求全員同意。
- 下方原提案中的 OWNER／平台審核者分組顯示已被此要求取代；名單聚焦 namespace ADMIN。
- 使用者確認只調整顯示，既有 OWNER／SKILL_ADMIN／SUPER_ADMIN 等審核權限全部不變。不修改 RBAC、自審、GLOBAL 或 scanner override 規則。
- UI 標為「Namespace 可審核人員」，顯示該 namespace 所有 ACTIVE ADMIN，不宣稱這是全平台唯一有 approve 權限的人員名單。SUPER_ADMIN 若同時具備該 namespace ADMIN membership，仍以 namespace ADMIN 身分列入；不單憑平台角色列入。

## 使用者背景與邊界

- 使用者內部 OSS import 已改為依 skill slug 判重，不再以 source_path 判重。這是使用者告知的內部差異，未取得部署程式，不宣稱本地已同步。
- 本功能以 namespace ID、skill/version ID、review task ID 查詢，不依賴 source_path，也不更改 OSS 判重、owner/submitter attribution 或審核規則。

## 本地現況證據

- `server-python/app/review/approval.py` 的 `_can_review`：非 GLOBAL namespace 的 OWNER/ADMIN，以及平台 SKILL_ADMIN/SUPER_ADMIN 可依現有規則審核。
- 自審有例外：SUPER_ADMIN 或非 GLOBAL 的 namespace manager 可以處理自己的提交；只有 SKILL_ADMIN 身分的自審不被這段規則允許。不得自行改成全面排除 submitter。
- approve 還檢查 review/task/version、namespace 狀態及 scanner evidence；有角色不等於此刻一定可以 approve。
- `web/src/pages/dashboard/review-progress.tsx` 已提供送審進度與歷史展開；歷史可顯示實際 reviewedBy，待審資料尚無指定 reviewer 的工作指派流程。
- `server-python/app/review/query.py` 的 my-progress 以 submitted_by 篩選。OSS skill owner 與本次 submitter 可能不同，不得只以 owner 代表所有 publisher。

## 建議第一版

1. Skill detail 的授權版本預覽區增加「審核狀態」卡片，與現有 review-progress 共用元件。依選定版本及目前有效的 review attempt 顯示，不混用已上架版本與新版本待審資料。
2. 顯示狀態、送審時間、等待時間及當前阻塞原因。SCANNING 顯示等待掃描，SCAN_FAILED 顯示需處理掃描，namespace 非 ACTIVE 顯示治理阻塞；UPLOADED/private 無 active task 不顯示等待人工 approve。
3. 待人工審核時標題使用「Namespace 可審核人員」，說明為「以下任一位皆可處理審核，尚未指定專人」。不暗示全部人都需 approve 或有人已領取工作；掃描或治理阻塞仍需先解除。
4. 只顯示該 namespace 的 ACTIVE ADMIN，呈現姓名及必要的可辨識 login name；人數多可展開／分頁查看完整清單，不用內部 user ID 當主要文字。相同使用者去重，不另列 OWNER 或平台審核者分組。
5. 清單由後端查目前 ACTIVE 人員及該 namespace 的 ADMIN membership，並對照真實 task authorization；前端不能把一般 MEMBER 或 review notification 收件者當審核名單。區分一般審核資格、此版本是否可 approve、是否需要現有平台 scan override 條件；不改既有授權判斷。
6. 審核完成顯示實際 reviewer、時間及意見，沿用既有歷史證據；不以目前角色名單重寫歷史。角色變動後重新讀取即更新待審清單，API 失敗不誤顯示無 reviewer。
7. 名單為空時顯示「目前沒有可列出的 Namespace ADMIN，請聯絡平台管理員」，不可寫成「無人可以審核」，因其他既有角色仍可能有權處理。GLOBAL 保留平台審核流程提示，不製造 namespace ADMIN 名單或展示全平台管理員姓名。

## 權限與安全

- 卡片限本次 submitter、skill owner 及已被授權管理／審核者查看；若既有版本存取不允許其中某身分，需獨立定義最小 metadata 存取，不連帶開放套件、README、scanner 原始 findings 或其他版本。
- 訪客、普通 catalog 瀏覽者、其他 namespace 的一般 MEMBER 不取得待審資訊或人員清單。
- 不公開 email、token、完整 OAuth claims。姓名／login 的顯示規則沿用已核准的人員識別投影。
- 查詢有分頁／上限、去重、批次查詢以免 progress 每列產生 N+1；名單僅提示，實際 approve 仍在交易中重新驗證授權與狀態。
- 無新環境變數、無新指派資料表或 migration 的預期；確切 API 契約待設計確認後落定。

## 實作決策補充

- 獨立唯讀 API：`GET /api/web/reviews/skills/{skill_id}/versions/{version}/context`，另有 `/api/v1` alias。使用 session／bearer 認證，再依真實 DB 帳號狀態、owner、該版最新 task submitter、namespace manager 或既有平台審核角色授權。
- 這是最小審核 metadata 存取，不連帶開放 README、套件或其他版本；無 task 時僅補上 version created_by 的查看權限。
- 以確切 skill/version 查目前有效 task，已刪除／替換版本的歷史仍由既有 attempts API／timeline 呈現。
- Detail 優先 owner preview 版本，否則 headline 版本；卡片標示版本號。Progress 僅待審項目有卡片、預設收合，展開才查詢，避免一頁 20 筆 eager fan-out；已完成項目沿用歷史。
- 每次最多 4 個 bounded SELECT（context、viewer roles、count、paged roster），不逐人查詢。UI 每頁 5 人，API 預設 20、上限 100；page 上限 10000。資料以 display name／user ID 穩定排序，不顯示內部 ID 作主要文字。
- 快取 key 包含登入 user ID、skill/version/page；登入者變更不共用私有資料。API `Cache-Control: private, no-store`，展開時 30 秒輪詢及視窗 focus 更新。
- 支援目前四種 locale：繁中、簡中、英文、俄文。無新 env、schema、migration 或 CLI build。

## 非目標（維持）

不新增 reviewer 指派／claim、多關卡簽核、全員同意、催審通知或 SLA；不改自審、scanner override、namespace membership、OSS source_path/slug 判重或 Python-only 架構；不 commit/push。

## 開發與驗收方向

1. API／policy 測試：OWNER/ADMIN/MEMBER、平台兩角色、GLOBAL、自審、停用、角色變動、owner 不等於 submitter、跨 namespace 非授權、無 task 及過期 attempt。
2. 真 PostgreSQL 執行 query／權限與現有 approve endpoint 對照，驗證候選名單和可處理條件一致；不僅靠 mock。
3. 啟動前後端與相關 PostgreSQL、Redis、storage/scanner，驗證一般與 OSS 送審 → 掃描 → 待審 → approve/reject 端到端路徑、桌面／手機、root／subpath。保留內部 slug-only 差異的適配邊界。
4. 同步 generated OpenAPI、支援中的 UI 語言、功能 manual 與驗收結果。此稿不代表以上測試已執行。
