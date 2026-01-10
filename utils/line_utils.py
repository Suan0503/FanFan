"""
LINE API utilities - LINE Bot 相關工具
"""
from linebot.models import TextSendMessage, FlexSendMessage
from linebot import LineBotApi
import config


def create_reply_message(line_bot_api, token, message_content):
    """
    統一的訊息回覆函數
    
    Args:
        line_bot_api: LINE Bot API 實例
        token: reply token
        message_content: 訊息內容（dict、list 或其他）
    """
    # 單一訊息
    if isinstance(message_content, dict):
        if message_content.get("type") == "flex":
            message = FlexSendMessage(alt_text=message_content["altText"],
                                      contents=message_content["contents"])
        else:
            message = TextSendMessage(text=message_content.get("text", ""))

    # 多則訊息
    elif isinstance(message_content, list):
        converted = []
        for m in message_content:
            # 已經是 LINE Message 物件的，直接使用
            if isinstance(m, (TextSendMessage, FlexSendMessage)):
                converted.append(m)
                continue

            # dict 轉換為對應訊息物件
            if isinstance(m, dict):
                if m.get("type") == "flex":
                    converted.append(
                        FlexSendMessage(alt_text=m["altText"],
                                        contents=m["contents"]))
                else:
                    converted.append(
                        TextSendMessage(text=m.get("text", "")))
            else:
                converted.append(m)

        message = converted
    else:
        # fallback：當成純文字
        message = TextSendMessage(text=str(message_content))

    try:
        line_bot_api.reply_message(token, message)
    except Exception as e:
        print(f"❌ 回覆訊息失敗: {type(e).__name__}: {e}")


def is_group_admin(user_id, group_id, data):
    """檢查用戶是否為群組管理員"""
    return data.get('group_admin', {}).get(group_id) == user_id
