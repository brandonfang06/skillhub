# 多技能安裝：Generic 目錄模式

使用者要求：在現有安裝 UI 加入 Generic，透過 OSS CLI 的 `--dir` 實現，不修改或發布 CLI。這取代舊 spec 的「不提供 --dir」限制，其餘決策維持。

## 實作與驗證計畫

1. 查驗已發布 npm artifact（目前 latest 為 0.1.12），不是僅依 repo source 推論；確認 `--dir` 的互斥參數與實際安裝子目錄。
2. Direct Agent 選項增加 Generic。User scope 使用 `--dir "$HOME/.agents/skills"`；Project scope 使用 `--dir "./.agents/skills"`。Generic 不附加 `--scope` 或 `--agent`；保留 `--force`、registry 與每 skill 獨立命令。上述路徑已經 npm 0.1.12 實際安裝驗證。
3. 沿用已核准 test seams：command renderer、user/tab-bound store、搜尋選取與安裝頁、真 CLI download／PostgreSQL event。TDD 驗證 Generic 命令、scope 切換、persist／logout 與其他 target 不退化。
4. 本機 Windows PowerShell 與 Linux Bash 實際驗證；macOS 的 Bash/Zsh 路徑相容性依 shell／CLI 契約驗證，若無 macOS 主機不得宣稱原生 macOS E2E。
5. 同步現有 feature manual 與各支援語系、驗證 root／subpath、小螢幕及登入追蹤。不 commit/push。

## 邊界

瀏覽器驗收補充：既有靜態 `install/skillhub.md` 目錄導致 `/install` 重載被 Nginx 301 到丟失 port／prefix 的 `/install/`。以 exact `/install` location 回傳 SPA 首頁，僅修正本功能入口；保留文件端點。以真 Nginx 重載 E2E 驗證，不改其他路由／API。

Generic 是安裝至通用 `.agents/skills` 目錄，不保證每種 Agent 都讀取該目錄，不自動複製至所有 Agent 專屬目錄。不加入任意路徑輸入，不支援 Windows CMD 的 `$HOME` 語法。保留終端互動模式。

不改 backend、下載事件定義、CLI 認證、npm 套件或既有 RBAC。命令不嵌入 token；以真正執行下載的 CLI 使用者追蹤，不以複製命令的 web 使用者推測。

## 上游證據

- `npm view @astron-team/skillhub version dist.tarball repository.url --json`：latest 為 `0.1.12`，來源 `https://github.com/iflytek/skillhub`。
- 實際驗證 [npm 0.1.12 artifact](https://registry.npmjs.org/@astron-team/skillhub/-/skillhub-0.1.12.tgz)，SHA-1 `195ca114be6088a13be813a944c93cc0999c2ce9`；未修改 package bundle。
- Bundle 的目標解析明確拒絕 `--dir` 與 `--scope`／`--agent` 混用，並將 explicit directory 記錄為 `custom`。沒有以「所有 Agent」取代目錄語意。
