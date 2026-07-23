# Telegram 雙向互動機器人架構設計與實作方案

本文件記錄將本專案 (`SuperTrend`) 擴充為具備**雙向對話能力**之 Telegram 機器人的技術選型、架構設計、對話指令定義與雲端部署規劃。本功能規劃在後續階段進一步實作。

---

## 1. 系統目標 (System Goals)

將目前單向推播的 `run_daily_scanner.py` 升級或補充「**雙向互動對話機器人 (`run_bot_listener.py`)**」，使使用者能隨時透過 Telegram 手機 app 進行以下操作：
1. **即時持倉查詢**：輸入 `/status` 即可查詢當前 SQLite 資料庫記錄的所有多頭持倉標的與止損/出場參考價。
2. **個股即時診斷**：輸入 `/scan TSLA`，機器人即時下載 TSLA 最新 K 線，計算最適 SuperTrend/HMA 指標並回覆診斷報告與建議買賣區間。
3. **手動觸發重優化**：輸入 `/reoptimize` 觸發全標的網格參數重新優化。
4. **系統說明與選單**：輸入 `/help` 顯示可用命令選單。

---

## 2. 技術選型與架構 (Technology Selection)

### 2.1 接收訊息技術途徑對比

| 比較項目 | 長輪詢 (Long Polling) 🌟 **[推薦首選]** | 網頁鉤子 (Webhook) |
| :--- | :--- | :--- |
| **運作原理** | 程式以常駐迴圈 (Loop) 主動向 Telegram API 請求 `getUpdates` 最新訊息。 | Telegram 伺服器在有新訊息時，主動發送 HTTP POST 請求至您的 Server。 |
| **網路與憑證需求** | **完全不需要**固定 IP、公網網址或 HTTPS SSL 憑證。本機連外網即可運作。 | 必須具備公網 IP、網域名稱，且必須設定 HTTPS SSL 憑證。 |
| **部署適合度** | 適用於本機電腦、家中 NAS、舊筆電或雲端免費 Background Worker (如 Render.com)。 | 適用於雲端 Serverless (如 Cloudflare Workers, AWS Lambda)。 |

### 2.2 核心 Python 框架選型
採用 Python 社群成熟穩定且高擴充性的套件：
- **`pyTelegramBotAPI` (`telebot`)** 或 **`python-telegram-bot`**。
- 與現有模組高度整合：
  - `src/storage.py` (SQLite 讀寫)
  - `src/data_loader.py` (yfinance K 線下載與快取)
  - `src/indicators.py` (SuperTrend 與 HMA 運算)
  - `src/telegram_notifier.py` (Telegram 憑證讀取與 .env 支援)

---

## 3. 擬定對話指令與回覆格式 (Interactive Commands)

### A. `/start` 或 `/help` (說明選單)
**機器人回覆：**
```html
🤖 <b>SuperTrend 互動式交易助手</b>

您可以發送以下指令進行即時查詢：
• <code>/status</code> - 查詢當前資料庫持倉標的與止損參考價
• <code>/scan TICKER</code> - 即時診斷指定個股 (例如 <code>/scan TSLA</code>)
• <code>/reoptimize</code> - 手動觸發全標的參數重新優化
• <code>/help</code> - 顯示此說明選單
```

### B. `/status` (當前持倉狀態)
**機器人回覆：**
```html
📊 <b>【當前持倉部位報告】</b>
📅 資料庫最新紀錄日期: 2026-07-24

🟢 <b>持倉中標的 (4 支):</b>
• <b>SPY</b> | 收盤: $627.17 | 出場參考價: $619.16
• <b>QQQM</b> | 收盤: $236.43 | 出場參考價: $231.25
• <b>NVDA</b> | 收盤: $174.52 | 出場參考價: $168.10
• <b>TSLA</b> | 收盤: $254.89 | 出場參考價: $243.32

⚪ 觀望中標的: 11 支
```

### C. `/scan <TICKER>` (單一標的即時診斷)
**使用者輸入：** `/scan NVDA`
**機器人回覆：**
```html
🔍 <b>[NVDA] 即時診斷報告</b>
📅 日期: 2026-07-24 | 最佳參數: ST(15, 3.5), HMA(50)

• 當前收盤價: <code>$174.52</code>
• SuperTrend 軌道價: <code>$168.10</code>
• 交易狀態: 🟢 <b>多頭持倉中 (Long)</b>
• 建議止損/平倉價: <code>$168.10</code>
```

---

## 4. 預計實作之腳本架構 (`run_bot_listener.py`)

```python
import os
import logging
import telebot
from src.storage import SQLiteStorage
from src.data_loader import DataLoader
from src.indicators import compute_supertrend
from src.telegram_notifier import TelegramNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 載入憑證 (支援環境變數與 .env)
notifier = TelegramNotifier()
if not notifier.is_configured():
    raise ValueError("未偵測到 TELEGRAM_BOT_TOKEN，請檢查環境變數或 .env 檔案")

bot = telebot.TeleBot(notifier.bot_token, parse_mode="HTML")
storage = SQLiteStorage()
data_loader = DataLoader()


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "🤖 <b>SuperTrend 互動式交易助手</b>\n\n"
        "可用指令：\n"
        "• <code>/status</code> - 查詢當前持倉與止損價\n"
        "• <code>/scan TICKER</code> - 即時診斷個股 (如 <code>/scan TSLA</code>)\n"
        "• <code>/help</code> - 說明選單"
    )
    bot.reply_to(message, help_text)


@bot.message_handler(commands=['scan'])
def handle_scan(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ 請提供股票代碼，例如：<code>/scan TSLA</code>")
            return
        ticker = args[1].upper()
        bot.reply_to(message, f"⏳ 正在下載與分析 <b>{ticker}</b> 最新數據...")

        raw_df = data_loader.fetch_data(ticker, start_date="2020-01-01", end_date="2026-07-24")
        if raw_df.empty:
            bot.reply_to(message, f"❌ 找不到 <b>{ticker}</b> 之歷史數據。")
            return

        df_st, _ = compute_supertrend(raw_df, period=10, multiplier=3.0)
        latest = df_st.iloc[-1]
        close_p, st_p = latest['Close'], latest['SuperTrend']
        is_long = close_p > st_p

        reply = (
            f"📊 <b>[{ticker}] 即時診斷</b>\n"
            f"• 收盤價: <code>${close_p:.2f}</code>\n"
            f"• SuperTrend 軌道價: <code>${st_p:.2f}</code>\n"
            f"• 狀態: {'🟢 多頭持倉' if is_long else '⚪ 觀望/空頭'}"
        )
        bot.reply_to(message, reply)
    except Exception as e:
        logger.error(f"Scan error: {e}")
        bot.reply_to(message, f"⚠️ 執行失敗: {e}")


if __name__ == "__main__":
    logger.info("🤖 Telegram 機器人長輪詢監聽啟動中...")
    bot.infinity_polling()
```

---

## 5. 部署與資料庫持久化建議 (Deployment & Persistence)

1. **免費雲端託管方案**：
   - **Render.com (Background Worker)**：可連動 GitHub，免費託管常駐 Python 監聽程式。
   - **本機電腦 / NAS / 樹莓派**：在 background 常駐執行 `python run_bot_listener.py &`。
2. **資料庫同步**：
   - 與排程工作流 (`run_daily_scanner.py`) 共享相同的 `data/market_data.db`。
   - 在 GitHub Actions 排程最後加入 `git commit` 自動將更新的 `.db` 檔存回 Git 倉庫。

---

## 6. 後續實作步驟 (Future Roadmap)

1. 安裝 `pyTelegramBotAPI` 依賴套件並加入 `requirements.txt`。
2. 建立 `run_bot_listener.py` 並實作完整指令處理器。
3. 增加單元測試驗證指令解析與回應邏輯。
4. 部署至常駐主機或 Render.com 進行雙向對話測試。
