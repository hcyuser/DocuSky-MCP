# DocuSky MCP

<img width="1178" height="787" alt="Screenshot 2026-09-12 at 2 17 19 AM" src="https://github.com/user-attachments/assets/8d3dc48e-1d22-46d6-a779-282f38b301d5" />

讓 Claude 直接查詢 **[DocuSky 數位人文學術研究平台](https://docusky.org.tw)** 的資料庫。

打包成 `.mcpb` 之後，使用者**雙擊就能安裝**，不需要碰終端機。裝好就可以用日常語言問問題：

> 「DocuSky 上有哪些公開資料庫？」
>
> 「在 DaoBudMed6D 裡查『針灸』，看它在佛、道、醫三類文獻的分布」
>
> 「把《真誥》那一筆的全文調出來」

---
<img width="883" height="781" alt="Screenshot 2026-09-12 at 2 17 00 AM" src="https://github.com/user-attachments/assets/9b260acb-3558-4d9d-af55-220f8235c498" />
<img width="985" height="598" alt="Screenshot 2026-09-12 at 2 56 56 AM" src="https://github.com/user-attachments/assets/f434839e-5c03-4e27-9224-d1c222fb337e" />


## 給使用者

### 需要準備什麼

- **Claude Desktop**（macOS 或 Windows 桌面應用程式）
- 不需要 DocuSky 帳號，也不需要會寫程式

> 網頁版（claude.ai）和手機 App **不支援**擴充功能，必須用桌面版。
> 沒裝的話可以到 [claude.ai/download](https://claude.ai/download) 下載。

---

### 步驟一：下載

**[⬇️ 點此下載 docusky.mcpb](https://github.com/hcyuser/DocuSky-MCP/releases/latest/download/docusky.mcpb)**

這個連結永遠指向最新版。想看歷史版本或更新說明，到
[Releases 頁面](https://github.com/hcyuser/DocuSky-MCP/releases)。

檔案大約 75 KB，副檔名是 `.mcpb`。瀏覽器可能會提示「不常下載的檔案類型」，選擇保留即可。

---

### 步驟二：安裝

三種方式擇一：

- **雙擊**下載好的 `docusky.mcpb`
- 把檔案**拖進** Claude Desktop 視窗
- Claude Desktop 選單：**設定 → 擴充功能 → 進階設定 → 安裝擴充功能…**

會跳出安裝畫面，上面列出這個擴充功能的名稱、說明，以及它提供的七個工具。確認後點安裝。

**接著會看到兩個欄位：DocuSky 帳號、DocuSky 密碼。**

| 你的情況 | 怎麼填 |
| --- | --- |
| 只想查公開資料庫（大多數人） | **兩個都留空**，直接完成安裝 |
| 想查自己在 DocuSky 建的資料庫 | 填入你的 DocuSky 帳號與密碼 |

帳密之後隨時可以補填或修改，不必重裝。

---

### 步驟三：確認可以用了

到 **設定 → 擴充功能**，應該會看到 **DocuSky** 且開關是開啟狀態。

然後開一個新對話，試著問：

> DocuSky 上有哪些公開資料庫？

第一次使用時，Claude 會詢問你是否允許它使用這個擴充功能的工具，選擇允許即可。

如果它列出了正統道藏、大明一統志、淡新檔案那些資料庫，就代表一切正常。

---

### 實際用起來是什麼樣子

你不需要記任何指令，直接用日常語言描述你想找什麼。

**你問：**

> 在 DaoBudMed6D 裡查「針灸」，看它在佛、道、醫三類文獻的分布

**Claude 會去 DocuSky 查完，然後回給你：**

| 文獻集 | 文件數 |
| --- | --- |
| Medical 醫書 | 14 |
| Buddhist 佛典 | 10 |
| Daoist 道藏 | 8 |

> 共 32 筆。值得注意的是佛道兩家加起來（18）比醫書（14）還多——針灸的討論並不侷限在醫學文本裡。前幾筆命中的是《太上洞淵神咒經》《真誥》《抱朴子》，年代集中在 363–420 年間。

**接著你可以繼續問：**

> 把《真誥》那一筆的全文調出來

它就會把整篇文獻讀出來給你。文章很長的話會分段，你說「繼續」就好。

其他可以這樣問的例子：

> - 宋會要輯稿裡關於「市舶司」的記載有哪些？
> - 淡新檔案有沒有提到樟腦的案件？
> - 幫我比較「疫」和「癘」在道藏裡的分布差異

---

### 日後管理

| 你想做什麼 | 怎麼做 |
| --- | --- |
| 填入或修改 DocuSky 帳密 | 設定 → 擴充功能 → DocuSky → 設定 |
| 暫時停用 | 設定 → 擴充功能 → 把開關關掉 |
| 更新到新版 | 下載新的 `.mcpb` 再安裝一次，會直接覆蓋 |
| 移除 | 設定 → 擴充功能 → 解除安裝 |

---

### 它能做什麼

- **全文檢索** —— 38 個公開資料庫（正統道藏、大明一統志、宋會要輯稿、朝鮮王朝實錄、淡新檔案、馬偕日記……）
- **分布統計** —— 一個詞在不同文獻集、時代、地點的出現分布
- **取全文** —— 單篇文獻完整讀出，長文自動分段
- **標記分析** —— 統計文本裡的人名、地名、時間等標記
- **私人資料庫** —— 填入帳密後也能查自己在 DocuSky 建的資料庫

---

### 檢索語法

平常用日常語言就好，需要精確控制時可以這樣講：

| 寫法 | 意思 |
| --- | --- |
| `針灸` | 全文檢索這個詞 |
| `醫 +方` | 必須同時包含「醫」和「方」 |
| `醫 -註` | 包含「醫」但排除「註」 |
| `.all` | 整個文獻集全部 |

---

### ⚠️ 不要把密碼貼在對話裡

對話內容會被保存。密碼請一律填在**擴充功能的設定欄位**，那是專門為此設計的，會經過安全儲存且不進入對話紀錄。

如果不小心貼了，建議去 DocuSky 改密碼。

---

### 遇到問題

**設定裡找不到「擴充功能」**

確認你用的是桌面版 Claude，不是瀏覽器開的 claude.ai。

**裝好了但 Claude 說查不到 DocuSky**

先重新啟動 Claude Desktop。再到設定 → 擴充功能確認 DocuSky 是開啟狀態。

**擴充功能顯示啟動失敗**

這個擴充功能以 Python 執行，需要系統上有 [uv](https://docs.astral.sh/uv/)。
多數情況下 Claude Desktop 會自行處理，若確實失敗，可在終端機安裝後重啟 Claude：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**查不到東西**

古籍常有異體字。試試換字（「醫」vs「毉」）、拆成單字，或換一個資料庫。也可以直接請 Claude 幫你想替代詞。

**查詢很慢**

DocuSky 的全文檢索本來就需要時間，跨大型資料庫時等十幾秒是正常的。

---

## 給開發者：怎麼打包

```bash
npm install -g @anthropic-ai/mcpb
mcpb pack . docusky.mcpb
```

產出約 75 KB。驗證 manifest：

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
