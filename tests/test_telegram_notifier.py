import pytest
from unittest.mock import patch, MagicMock
from src.telegram_notifier import TelegramNotifier


def test_telegram_notifier_configured():
    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    assert notifier.is_configured() is True

    with patch.dict("os.environ", {}, clear=True):
        notifier_empty = TelegramNotifier(bot_token="", chat_id="", env_path="")
        assert notifier_empty.is_configured() is False


def test_split_message():
    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    short_msg = "Hello World"
    assert notifier.split_message(short_msg, max_length=100) == [short_msg]

    lines = [f"Line {i}: Some detail content for stock signals." for i in range(50)]
    long_msg = "\n".join(lines)

    chunks = notifier.split_message(long_msg, max_length=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 200


@patch("src.telegram_notifier.requests.post")
def test_send_message_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}
    mock_post.return_value = mock_resp

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    success = notifier.send_message("<b>Test Report</b>")

    assert success is True
    assert mock_post.call_count == 1
    args, kwargs = mock_post.call_args
    assert kwargs["json"]["chat_id"] == "12345"
    assert kwargs["json"]["text"] == "<b>Test Report</b>"
    assert kwargs["json"]["parse_mode"] == "HTML"


@patch("src.telegram_notifier.requests.post")
def test_send_message_failure_retry(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_post.return_value = mock_resp

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    with patch("time.sleep", return_value=None):
        success = notifier.send_message("Test Error Handling", max_retries=2)

    assert success is False
    assert mock_post.call_count == 2


def test_telegram_notifier_read_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'TELEGRAM_BOT_TOKEN="token_from_env_file"\nTELEGRAM_CHAT_ID=\'chat_id_from_env_file\'\n',
        encoding="utf-8"
    )

    with patch.dict("os.environ", {}, clear=True):
        notifier = TelegramNotifier(env_path=str(env_file))
        assert notifier.is_configured() is True
        assert notifier.bot_token == "token_from_env_file"
        assert notifier.chat_id == "chat_id_from_env_file"

