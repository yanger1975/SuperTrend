# GitHub Actions 外部精準排程觸發指南 (External Precision Trigger Guide)

> **建立日期**：2026-10-20
> **更新日期**：2026-11-07
> **適用目標**：
> 1. 台股盤中 13:10 即時訊號掃描 (`intraday_tw_signals.yml`) —— **已於 cron-job.org 設定完成**
> 2. SuperTrend AI 全市場每日訊號掃描與批次優化 (`daily_supertrend_ai_signals.yml`) —— **台灣時間每日早上 07:00（含美股、台股、國內基金與 ETF）**
> 3. （選用備用）傳統版 SuperTrend 每日訊號掃描 (`daily_signals.yml`)

---

## 1. 背景與排程架構說明

GitHub Actions 內建的 `schedule`（Cron）機制具有以下已知限制：
1. **非保證精準時間**：GitHub 官方文件明定排程屬於盡力而為（Best-effort），在公共隊列資源有限時會產生排隊延遲（Queue Delay）。
2. **延遲可能達數小時**：在尖峰時段或特定整點，延遲常達 30 分鐘至數小時，導致盤中訊號無法在收盤前送達，或每日清晨結算延宕。
3. **已全面解除 GitHub Cron 依賴**：專案中所有工作流的 `schedule` 觸發器皆已停用，全面改由外部高可靠排程平台（[cron-job.org](https://cron-job.org/)）在指定時間準時透過 GitHub REST API 發送 `workflow_dispatch` 請求觸發。此方式直接跳過排程等待隊列，能在秒級內啟動 Runner 執行。

---

## 2. 準備工作：取得 GitHub Personal Access Token (PAT)

呼叫 GitHub Actions API 觸發工作流需帶入授權 Token。多個 cron-job 工作可共用同一個 PAT。

### 申請步驟：
1. 登入 GitHub，點擊右上角個人頭像 ➔ **Settings**。
2. 於左側選單最下方點擊 **Developer Settings**。
3. 選擇 **Personal access tokens** ➔ **Fine-grained tokens**（推薦）或 **Tokens (classic)**。
4. 點擊 **Generate new token** 填寫下列資訊：
   * **Token name**：`cronjob-supertrend-scheduler`
   * **Expiration**：依需求設定（例如 90 天，或 Classic token 選擇 No expiration）
   * **Repository access**：選擇 **Only select repositories** ➔ 勾選 `yanger1975/SuperTrend`
   * **Permissions**：
     * **Actions**：設定為 **Read and write**
5. 點擊 **Generate token**，複製並妥善保管該 Token（以下代稱 `<YOUR_GITHUB_PAT>`）。

---

## 3. 工作任務設定清單 (cron-job.org)

### 【工作 1】台股盤中即時訊號掃描（13:10） —— 已完成設定
* **工作名稱**：`SuperTrend TW Intraday Scanner (13:10)`
* **目標工作流**：[`intraday_tw_signals.yml`](file:///.github/workflows/intraday_tw_signals.yml)
* **API URL**：
  ```text
  https://api.github.com/repos/yanger1975/SuperTrend/actions/workflows/intraday_tw_signals.yml/dispatches
  ```
* **執行時間**：台灣時間週一至週五 13:10（台股收盤前 20 分鐘）

---

### 【工作 2】SuperTrend AI 全市場每日訊號掃描與優化（早上 07:00） —— 新增設定步驟

本工作涵蓋美股（`data/must_have.json`）以及台股與國內基金/ETF（`data/must_have_tw.json`）的全市場 SuperTrend AI 策略掃描、回測與報告產出。

#### cron-job.org 詳細設定步驟：
1. 登入 [cron-job.org](https://cron-job.org/) 控制台。
2. 點擊右上角 **CREATE CRONJOB**。
3. **Common Settings（基本設定）**：
   * **Title**：`SuperTrend AI Daily Full Market (07:00)`
   * **URL**：
     ```text
     https://api.github.com/repos/yanger1975/SuperTrend/actions/workflows/daily_supertrend_ai_signals.yml/dispatches
     ```
   * **Execution schedule**：選擇 **User-defined**：
     * **Timezone**：`Asia/Taipei (GMT+08:00)`
     * **Days of month**：全選（Every day）
     * **Days of week**：全選（Monday ~ Sunday，每日執行）
     * **Hours**：`07`
     * **Minutes**：`00`
4. **Advanced Settings（進階設定）**：
   * **Request method**：改為 `POST`
   * **Request headers**：新增 4 組鍵值對：
     | Key | Value |
     | :--- | :--- |
     | `Accept` | `application/vnd.github+json` |
     | `Authorization` | `Bearer <YOUR_GITHUB_PAT>` |
     | `X-GitHub-Api-Version` | `2022-11-28` |
     | `User-Agent` | `SuperTrend-Cron-Scheduler` |
   * **Request body**：
     ```json
     {"ref": "main"}
     ```
5. **通知與錯誤警報（可選）**：
   * 勾選 **Failure notifications**，當外部觸發連續失敗時會寄信通知。
6. 點擊 **CREATE** 儲存。
7. **測試驗證**：
   * 點擊該任務右側的 **Run now** 測試按鈕。
   * 查看 GitHub 倉庫的 **Actions** 頁面，確認 `Daily SuperTrend AI Signal Scanner & Telegram Notifier` 立即啟動運行。

#### 運作機制與特點說明：
* **資料最新與最完整**：台灣時間早上 07:00 執行時，美股已於清晨收盤（夏令 04:00 / 冬令 05:00），且 Yahoo Finance / 國內基金數據已完全結算封存，是產出每日策略訊號與儀表板報告的最佳時機。
* **週末全自動重新優化**：
  * 平日（週一至週六早上 07:00）：執行每日最新價格更新、訊號推播與 GitHub Pages 發布。
  * 週日（台灣時間週日早上 07:00，對應 UTC 週六 23:00）：工作流自動判斷並帶入 `--force` 參數，對全市場標的進行每週網格參數重新尋優。
* ** Telegram 與 Pages 整合**：完成後會將即時買賣訊號推播至 Telegram 群組，並自動發布最新互動報表至 GitHub Pages。

---

### 【工作 3】傳統版 SuperTrend 每日訊號掃描（選用參考）
若您同時需要定時執行非 AI 版本的傳統 SuperTrend 指標掃描：
* **Title**：`SuperTrend Classic Daily Scanner`
* **URL**：
  ```text
  https://api.github.com/repos/yanger1975/SuperTrend/actions/workflows/daily_signals.yml/dispatches
  ```
* **建議時間**：台灣時間早上 08:30
* **Request Method、Headers 與 Body**：與工作 2 完全相同。

---

## 4. 本機終端機快速測試指令

您可使用以下指令於本機電腦終端機直接測試 API 觸發是否成功：

### 測試觸發工作 2（SuperTrend AI 每日工作流）

#### PowerShell：
```powershell
$token = "<YOUR_GITHUB_PAT>"
$headers = @{
    "Accept"               = "application/vnd.github+json"
    "Authorization"        = "Bearer $token"
    "X-GitHub-Api-Version" = "2022-11-28"
    "User-Agent"           = "SuperTrend-Cron-Scheduler"
}
$body = '{"ref":"main"}'

Invoke-RestMethod -Uri "https://api.github.com/repos/yanger1975/SuperTrend/actions/workflows/daily_supertrend_ai_signals.yml/dispatches" `
    -Method Post `
    -Headers $headers `
    -Body $body `
    -ContentType "application/json"
```

#### Bash / Linux / macOS：
```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR_GITHUB_PAT>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "User-Agent: SuperTrend-Cron-Scheduler" \
  https://api.github.com/repos/yanger1975/SuperTrend/actions/workflows/daily_supertrend_ai_signals.yml/dispatches \
  -d '{"ref":"main"}'
```
> **預期結果**：HTTP 狀態碼為 `204 No Content`（無錯誤訊息），即代表成功觸發 GitHub Actions。

---

## 5. 工作流狀態與參數設定對照表

目前倉庫中三個工作流的排程狀態如下：

| 工作流檔案 | 涵蓋市場與功能 | 原始 GitHub Cron | 現行觸發方式 | 排程建議時間 (台灣時間) |
| :--- | :--- | :--- | :--- | :--- |
| [`intraday_tw_signals.yml`](file:///.github/workflows/intraday_tw_signals.yml) | 台股 ETF / 基金盤中掃描 | `10 5 * * 1-5` *(已停用)* | cron-job.org API | **週一至週五 13:10** *(已就緒)* |
| [`daily_supertrend_ai_signals.yml`](file:///.github/workflows/daily_supertrend_ai_signals.yml) | **SuperTrend AI 全市場** (美股 + 台股/基金 ETF 每日掃描與週日優化) | `30 23 * * 1-5`<br>`30 23 * * 6` *(已停用)* | cron-job.org API | **每日 07:00** *(本次新增)* |
| [`daily_signals.yml`](file:///.github/workflows/daily_signals.yml) | 傳統版 SuperTrend 每日掃描與週末優化 | `30 0 * * 2-6`<br>`30 0 * * 0` *(已停用)* | cron-job.org API / 手動 | 每日 08:30 *(選用)* |
