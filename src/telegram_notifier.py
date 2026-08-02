import os
import time
import logging
import html
from typing import List, Optional
import requests

logger = logging.getLogger(__name__)

# 嘗試載入 python-dotenv (若環境有安裝)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _read_env_file(env_path: str = ".env") -> dict:
    """
    自訂 .env 檔案解析器（無需依賴外部套件）。
    支援讀取執行目錄下 .env 中的 KEY=VALUE 設定。
    """
    env_vars = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env_vars[key] = value
        except Exception as e:
            logger.warning("讀取 .env 檔案時發生錯誤: %s", e)
    return env_vars


def escape_html(text: str) -> str:
    """
    對動態插入 Telegram HTML 訊息中的文字進行轉義，防止 HTML 標籤注入。
    """
    return html.escape(str(text))


class TelegramNotifier:
    """
    Telegram Bot 通知發送模組
    支援 HTML 格式排版、訊息切分（長度限制）與重試機制。
    支援自動從系統環境變數與執行目錄下的 .env 檔案讀取憑證。
    """
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        env_path: str = ".env"
    ):
        # 1. 優先使用帶入參數
        self.bot_token = bot_token
        self.chat_id = chat_id

        # 2. 次要從系統環境變數讀取
        if not self.bot_token:
            self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not self.chat_id:
            self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")

        # 3. 再次從執行目錄下 .env 檔案讀取
        if not self.bot_token or not self.chat_id:
            env_file_vars = _read_env_file(env_path)
            if not self.bot_token:
                self.bot_token = env_file_vars.get("TELEGRAM_BOT_TOKEN")
            if not self.chat_id:
                self.chat_id = env_file_vars.get("TELEGRAM_CHAT_ID")

    @property
    def api_url(self) -> str:
        """動態生成 API URL，避免直接儲存 Token 在公開屬性或 traceback 中。"""
        if not self.bot_token:
            return ""
        return f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def is_configured(self) -> bool:
        """檢查是否有設定必要的 Token 與 Chat ID。"""
        return bool(self.bot_token and self.chat_id)

    def split_message(self, text: str, max_length: int = 3500) -> List[str]:
        """
        將長訊息切分成多個小段落，避免超過 Telegram 4096 字元限制。
        按換行符優先切分，維護 HTML 標籤開閉完整性。
        """
        if len(text) <= max_length:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1  # 包含 \n
            if current_len + line_len > max_length and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_len = line_len
            else:
                current_chunk.append(line)
                current_len += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
        max_retries: int = 3
    ) -> bool:
        """
        發送 Telegram 訊息。若長度超過上限會自動切分批發送。

        Args:
            text: 訊息內文 (支援 HTML)
            parse_mode: "HTML" 或 "Markdown"
            disable_web_page_preview: 是否關閉網頁預覽
            max_retries: 失敗重試次數

        Returns:
            bool: 是否全數成功發送
        """
        if not self.is_configured():
            logger.warning("Telegram Bot Token 或 Chat ID 未設定，無法發送訊息。")
            return False

        url = self.api_url
        chunks = self.split_message(text)
        all_success = True

        for idx, chunk in enumerate(chunks):
            payload = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_web_page_preview
            }

            sent = False
            for attempt in range(1, max_retries + 1):
                try:
                    resp = requests.post(url, json=payload, timeout=10)
                    if resp.status_code == 200 and resp.json().get("ok"):
                        sent = True
                        break
                    else:
                        logger.warning(
                            "Telegram API 回應失敗 [Attempt %d/%d]: HTTP %d",
                            attempt, max_retries, resp.status_code
                        )
                except requests.RequestException as e:
                    logger.warning("Telegram API 呼叫例外 [Attempt %d/%d]: %s", attempt, max_retries, e)

                time.sleep(attempt * 2)

            if not sent:
                all_success = False
                logger.error("Telegram 訊息 Chunk [%d/%d] 發送失敗。", idx + 1, len(chunks))

        return all_success
