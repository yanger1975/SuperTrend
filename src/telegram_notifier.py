import os
import time
import logging
from typing import List, Optional
import requests

logger = logging.getLogger(__name__)

# 嘗試載入 python-dotenv (若環境有安裝)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class TelegramNotifier:
    """
    Telegram Bot 通知發送模組
    支援 HTML 格式排版、訊息切分（長度限制）與重試機制。
    """
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage" if self.bot_token else ""

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
                    resp = requests.post(self.api_url, json=payload, timeout=10)
                    if resp.status_code == 200 and resp.json().get("ok"):
                        sent = True
                        break
                    else:
                        logger.warning(
                            f"Telegram API 回應失敗 [Attempt {attempt}/{max_retries}]: "
                            f"HTTP {resp.status_code} - {resp.text}"
                        )
                except Exception as e:
                    logger.warning(f"Telegram API 呼叫例外 [Attempt {attempt}/{max_retries}]: {e}")

                time.sleep(attempt * 2)

            if not sent:
                all_success = False
                logger.error(f"Telegram 訊息 Chunk [{idx+1}/{len(chunks)}] 發送失敗。")

        return all_success
