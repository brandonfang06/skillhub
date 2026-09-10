# Namespace 可審核人員

Publisher 可以查看目前有哪些 Namespace ADMIN 可協助處理送審，不必猜測該找誰。

## 從哪裡查看

1. **Skill detail**：授權的 skill 管理者可直接看到「Namespace 可審核人員」卡片。若已有上架版、另有新版待審，卡片優先顯示 owner preview 的版本，並清楚標示版本號。
2. **儀表板 → 我的審核進度**（`/dashboard/review-progress`）：在待審項目展開同名卡片。OSS 匯入者即使不是 skill owner，也可在自己的送審進度查看；不因此取得其他版本的私有內容。
3. 已完成的項目可以展開「提交歷史」，查看實際審核人員、時間與意見。

以上路徑會沿用部署的 base path；部署在 `/skillhub` 時不需要另設本功能的環境變數。

## 名單與狀態的意思

- 名單列出該 namespace **帳號為 ACTIVE、membership 為 ADMIN** 的人，顯示姓名，以及可用且與姓名不同的 Keycloak login name。每頁 5 人，可用上一頁／下一頁查看完整清單。
- 「等待 Namespace 人工審核」代表以下任一位 Namespace ADMIN 可以處理；**不是指定給某個人，也不需要每個人都同意**。
- 安全掃描中、掃描失敗、掃描未完整完成、namespace 非 ACTIVE 時，會顯示相應阻塞原因。名單中的人有 namespace 審核角色，不代表可以略過這些限制。
- 掃描未完整完成時，仍適用原本的平台例外核准條件與確認程序，不會因為列在名單就取得 scanner override 權限。
- 尚未送審的版本不會顯示成正在等人核准。GLOBAL 顯示既有平台審核流程提示，不公開全平台管理員名單。
- 送審時間旁的等待分鐘數代表目前送審經過的時間，包含掃描等待；不是人工審核 SLA。

## 重要邊界

此功能**只調整資訊顯示，不修改權限**。OWNER、SKILL_ADMIN、SUPER_ADMIN 原有的核准權限與自審規則都保留；僅持有這些角色不會自動列入 Namespace ADMIN 名單。SUPER_ADMIN 若同時具有該 namespace ADMIN membership，仍會列入。

清單為空時請聯絡平台管理員；空清單不代表無人有權審核。載入失敗則顯示錯誤與重試按鈕，不會偽裝成空名單。展開的卡片約每 30 秒及返回視窗時更新，正式核准仍由後端重新檢查當下權限及狀態。

訪客、普通 catalog 使用者及不相關 namespace 的一般成員不能查看這份私有審核資訊；卡片不提供 email、OAuth claims、token 或原始掃描 findings。

OSS import 的 skill owner、version submitter、service account 與 namespace membership 是不同概念。本功能直接依 namespace membership 列名單，不依來源路徑或 slug 推測審核人員，也不更改匯入判重或歸屬。
