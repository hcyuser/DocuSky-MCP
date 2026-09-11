# DocuSky MCP

讓 Claude 直接查詢 **[DocuSky 數位人文學術研究平台](https://docusky.org.tw)** 的資料庫。

打包成 `.mcpb` 之後，使用者**雙擊就能安裝**，不需要碰終端機。裝好就可以用日常語言問問題：

> 「DocuSky 上有哪些公開資料庫？」
>
> 「在 DaoBudMed6D 裡查『針灸』，看它在佛、道、醫三類文獻的分布」
>
> 「把《真誥》那一筆的全文調出來」

---

## 給使用者：怎麼安裝

**[⬇️ 下載最新版 docusky.mcpb](https://github.com/hcyuser/DocuSky-MCP/releases/latest/download/docusky.mcpb)**

1. 下載 `docusky.mcpb`
2. **雙擊**（或拖進 Claude Desktop 視窗）
3. 在安裝畫面按確認
4. 要查自己的私人資料庫才需要填 DocuSky 帳號密碼；只用公開資料庫的話**留空即可**

密碼由 Claude Desktop 自己的設定介面收集並安全儲存，不會出現在對話裡。

之後想修改帳號密碼：**設定 → 擴充功能 → DocuSky**。

### 它能做什麼

- **全文檢索** —— 38 個公開資料庫（正統道藏、大明一統志、宋會要輯稿、朝鮮王朝實錄、淡新檔案、馬偕日記……）
- **分布統計** —— 一個詞在不同文獻集、時代、地點的出現分布
- **取全文** —— 單篇文獻完整讀出，長文自動分段
- **標記分析** —— 統計文本裡的人名、地名、時間等標記
- **私人資料庫** —— 填入帳密後也能查自己在 DocuSky 建的資料庫

### 檢索語法

平常用日常語言就好，需要精確控制時可以這樣講：

| 寫法 | 意思 |
| --- | --- |
| `針灸` | 全文檢索這個詞 |
| `醫 +方` | 必須同時包含「醫」和「方」 |
| `醫 -註` | 包含「醫」但排除「註」 |
| `.all` | 整個文獻集全部 |

### ⚠️ 不要把密碼貼在對話裡

對話內容會被保存。密碼請一律填在**擴充功能的設定欄位**，那是專門為此設計的，會經過安全儲存且不進入對話紀錄。

如果不小心貼了，建議去 DocuSky 改密碼。

---

## 給開發者：怎麼打包

```bash
npm install -g @anthropic-ai/mcpb
mcpb pack . docusky.mcpb
```

產出約 73 KB。驗證 manifest：

```bash
mcpb validate manifest.json
```

### 自動建置

`.github/workflows/build-mcpb.yml` 會在 **push 到 `main`** 或**手動觸發**時：

1. 驗證 `manifest.json`
2. 打包 `docusky.mcpb`
3. 解開並實際啟動一次，確認七個工具都在（不會連到 DocuSky）
4. 上傳為 workflow artifact
5. 發布 GitHub Release，tag 取自 `manifest.json` 的 `version`

Release 讓沒有 GitHub 帳號的人也能直接下載。版本號沒變而重跑時，會覆蓋既有的附件而不是失敗。

要發新版本就改 `manifest.json` 裡的 `version`，push 之後會自動建立對應的 Release。

### 專案結構

```
manifest.json           MCPB manifest（宣告工具、user_config、啟動方式）
server.py               進入點 shim
docusky_mcp/client.py   DocuSky Web API client
docusky_mcp/server.py   MCP 工具層
docusky_mcp/credentials.py  憑證讀取（環境變數優先）
pyproject.toml          相依套件定義
uv.lock                 鎖定版本，啟動時用 --frozen 安裝
.mcpbignore             打包時排除的檔案
```

`server.py` 存在的理由：`uv` 型別的 host 會直接執行進入點檔案，而 `docusky_mcp/server.py`
用的是相對匯入，直接跑會 `ImportError`。這個 shim 透過已安裝的套件轉一手。

### 執行環境

`manifest.json` 宣告 `server.type: "uv"`，啟動指令是：

```
uv run --frozen --directory ${__dirname} server.py
```

依 MCPB 規格，`uv` 型別由 host 管理 Python 與相依套件。`manifest_version` 必須是
`0.4` —— `0.3` 的 schema 只接受 `python | node | binary`。

### 憑證

`user_config` 的兩個欄位會被注入成環境變數：

| 欄位 | 環境變數 |
| --- | --- |
| DocuSky 帳號 | `DOCUSKY_USERNAME` |
| DocuSky 密碼（`sensitive: true`） | `DOCUSKY_PASSWORD` |

留空時兩者皆為空字串，`credentials.py` 會判定為未登入並退回公開模式。

其他可用的環境變數：

| 變數 | 預設值 | 用途 |
| --- | --- | --- |
| `DOCUSKY_CREDENTIALS` | `~/.docusky/credentials.json` | 憑證檔位置（給非 Claude Desktop 的 MCP 客戶端用的後備） |
| `DOCUSKY_BASE_URL` | `https://docusky.org.tw/DocuSky/webApi` | API 根路徑 |
| `DOCUSKY_TIMEOUT` | `120` | 單次請求逾時（秒） |

### 提供的工具

| 工具 | 用途 |
| --- | --- |
| `list_databases` | 列出可用資料庫 |
| `list_corpora` | 某資料庫下的文獻集與篇數 |
| `search_documents` | 全文檢索，回傳書目與摘錄 |
| `get_document` | 取單篇全文 |
| `post_classification` | 分布統計 |
| `tag_analysis` | 標記統計 |
| `check_login` | 檢查登入狀態 |

`search_documents` 刻意不回全文——DocuSky 單篇動輒六千字以上，一次二十筆會塞爆
context。要讀全文請用 `get_document`，帶入該筆的 `n`，並沿用同一組
`db` / `query` / `corpus` / `page_size`。

---

## 注意事項

- 本專案使用 DocuSky 的 Web API（`docusky.org.tw/DocuSky/webApi/`）。該 API 沒有公開文件也沒有版本號，DocuSky 改版時可能需要跟著更新。
- 部分端點會在 JSON 前面夾帶 PHP 警告訊息，client 有做容錯。
- 命中數是**文件數**，不是詞頻。
- 少數資料庫的「分類」欄位在 DocuSky 端本身就是亂碼，不要據以推論。
- 部分資料庫仍在建構中，查不到內容是正常的。
- 請遵守 [DocuSky 服務與使用規範](https://hackmd.io/@DocuSky/rJqemuiFQ)，並節制查詢頻率。
