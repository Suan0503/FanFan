"""
FanFan LINE Bot - Webhook 事件處理
負責處理所有 LINE Bot 事件
"""


def handle_webhook_events(events, line_bot_api, data, MASTER_USER_IDS):
    """
    統一處理所有 webhook 事件
    
    Args:
        events: LINE webhook 事件列表
        line_bot_api: LINE Bot API 實例
        data: 全域資料字典
        MASTER_USER_IDS: 主人 ID 集合
    """
    # 這個函數將在 main.py 中被呼叫
    # 詳細實現將在原 main.py 的事件處理邏輯中
    for event in events:
        source = event.get("source", {})
        group_id = source.get("groupId") or source.get("userId")
        user_id = source.get("userId")
        if not group_id or not user_id:
            continue
        
        event_type = event.get("type")
        
        # 事件分發邏輯將在此處實現
        # 包括：join, postback, message 等事件的處理
        pass
