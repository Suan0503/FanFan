"""
FanFan LINE Bot - 主入口文件 (模組化版本)

專案結構:
├── main.py (本檔)
├── config.py (配置常數)
├── models.py (資料庫模型)
├── translations/ (翻譯引擎)
│   ├── deepl_translator.py
│   └── google_translator.py
├── services/ (業務邏輯)
│   ├── translation_service.py (翻譯協調)
│   ├── tenant_service.py (租戶管理)
│   └── group_service.py (群組設定)
├── utils/ (工具函數)
│   ├── file_utils.py (檔案操作)
│   ├── system_utils.py (系統監控)
│   └── line_utils.py (LINE API)
└── handlers/ (事件處理)

功能:
- 群組翻譯（Google + DeepL）
- 租戶訂閱管理
- 群組活躍監控
- 自動語言檢測
- 記憶體監控
"""

from flask import Flask, request
import os
import sys
import json
import time
import threading
import hmac
import hashlib
import base64

# 導入配置
import config

# 導入資料庫模型
from models import db, init_db, GroupTranslateSetting, GroupActivity, GroupEnginePreference

# 導入服務
from services import translation_service, tenant_service, group_service
from translations import deepl_translator

# 導入工具
from utils import file_utils, system_utils, line_utils

# 導入 LINE Bot
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage

# ============== Flask 應用初始化 ==============
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL or "sqlite:///fanfan.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 初始化資料庫
init_db(app)

# 初始化 LINE Bot API
line_bot_api = LineBotApi(config.CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(config.CHANNEL_SECRET.decode('utf-8') if isinstance(config.CHANNEL_SECRET, bytes) else config.CHANNEL_SECRET)

# 翻譯執行緒限制
translation_semaphore = threading.Semaphore(config.MAX_CONCURRENT_TRANSLATIONS)

# 啟動時間
start_time = time.time()

# ============== 啟動時初始化 ==============
def init_app():
    """應用啟動初始化"""
    print("🚀 應用啟動中...")
    
    # 載入主人列表
    load_master_users()
    
    # 載入資料
    load_data()
    
    # 載入 DeepL 支援語言
    deepl_translator.load_deepl_supported_languages()
    
    print("✅ 應用啟動完成！")


# ============== 主人和授權管理 ==============
MASTER_USER_IDS = set()

def load_master_users():
    """載入主人列表"""
    global MASTER_USER_IDS
    if os.path.exists(config.MASTER_USER_FILE):
        with open(config.MASTER_USER_FILE, "r", encoding="utf-8") as f:
            MASTER_USER_IDS = set(json.load(f))
    else:
        MASTER_USER_IDS = config.DEFAULT_MASTER_USER_IDS.copy()
        save_master_users(MASTER_USER_IDS)

def save_master_users(master_set):
    """保存主人列表"""
    with open(config.MASTER_USER_FILE, "w", encoding="utf-8") as f:
        json.dump(list(master_set), f, ensure_ascii=False, indent=2)
        print("💾 主人列表已更新！")

# ============== 資料持久化 ==============
data = {
    "user_whitelist": [],
    "user_prefs": {},
    "voice_translation": {},
    "group_admin": {},
    "translate_engine_pref": {},
    "tenants": {}
}

def load_data():
    """載入資料"""
    global data
    data = file_utils.load_json(config.DATA_FILE)
    if not data:
        data = {
            "user_whitelist": [],
            "user_prefs": {},
            "voice_translation": {},
            "group_admin": {},
            "translate_engine_pref": {},
            "tenants": {}
        }
        save_data()
    print("✅ 資料已載入")

def save_data():
    """保存資料"""
    file_utils.save_json(config.DATA_FILE, data)

# ============== 語言選單 ==============
def language_selection_message(group_id):
    """建立語言選擇選單"""
    current_langs = group_service.get_group_langs(group_id)

    contents = []
    for label, code in config.LANGUAGE_MAP.items():
        selected = code in current_langs
        button_label = f"✅ {label}" if selected else label
        contents.append({
            "type": "button",
            "style": "primary",
            "color": "#DC143C" if selected else "#FF6347",
            "action": {
                "type": "postback",
                "label": button_label,
                "data": f"lang:{code}"
            }
        })

    contents.append({
        "type": "button",
        "style": "secondary",
        "action": {
            "type": "postback",
            "label": "🔄 重設翻譯設定",
            "data": "reset"
        }
    })

    return {
        "type": "flex",
        "altText": "🎊 新春翻譯設定",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": "🎊 群組翻譯設定",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#DC143C"
                }, {
                    "type": "text",
                    "text": "請加上 / 取消要翻譯成的語言，可複選。",
                    "size": "sm",
                    "color": "#555555",
                    "wrap": True
                }]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": contents
            }
        }
    }

# ============== 非同步翻譯 ==============
def _async_translate_and_reply(reply_token, text, langs, group_id=None):
    """在背景執行緒中翻譯並回覆"""
    
    acquired = translation_semaphore.acquire(blocking=False)
    if not acquired:
        print(f"⚠️ 翻譯執行緒已滿，拒絕新翻譯請求")
        try:
            line_bot_api.reply_message(reply_token, TextSendMessage(text="⏳ 翻譯忙碌中，請稍後再試"))
        except:
            pass
        return

    try:
        lang_list = list(langs)
        result_text = translation_service.format_translation_results(text, lang_list, group_id=group_id)
        line_bot_api.reply_message(reply_token, TextSendMessage(text=result_text))
    except Exception as e:
        print(f"❌ 非同步翻譯回覆失敗: {type(e).__name__}: {e}")
    finally:
        translation_semaphore.release()

# ============== Webhook 路由 ==============
@app.route("/webhook", methods=['POST'])
def webhook():
    """LINE Webhook 入口"""
    # LINE Webhook 簽名驗證
    signature = request.headers.get('X-Line-Signature', '')
    body_text = request.get_data(as_text=True)
    
    # 手動驗證簽名
    if config.CHANNEL_SECRET:
        hash_obj = hmac.new(config.CHANNEL_SECRET, body_text.encode('utf-8'), hashlib.sha256)
        expected_signature = base64.b64encode(hash_obj.digest()).decode('utf-8')
        if signature != expected_signature:
            print(f"❌ Webhook 簽名驗證失敗")
            return 'Invalid signature', 400
    
    # 解析 events
    try:
        body = json.loads(body_text)
    except:
        return 'Invalid JSON', 400
    
    events = body.get("events", [])
    for event in events:
        try:
            handle_event(event)
        except Exception as e:
            print(f"❌ 處理事件失敗: {type(e).__name__}: {e}")
    
    return 'OK'


def handle_event(event):
    """處理 LINE 事件"""
    source = event.get("source", {})
    group_id = source.get("groupId") or source.get("userId")
    user_id = source.get("userId")
    event_type = event.get("type")

    if not group_id or not user_id:
        return

    # 更新群組活躍時間
    raw_group_id = source.get("groupId")
    if raw_group_id:
        group_service.touch_group_activity(raw_group_id)

    # 機器人被加進群組
    if event_type == 'join':
        line_utils.create_reply_message(line_bot_api, event['replyToken'], [
            {"type": "text", "text": "👋 歡迎邀請翻譯小精靈！"},
            language_selection_message(group_id)
        ])
        return

    # 處理 postback（語言選擇）
    if event_type == 'postback':
        handle_postback(event, user_id, group_id)
        return

    # 處理訊息
    if event_type == 'message':
        handle_message(event, user_id, group_id)
        return


def handle_postback(event, user_id, group_id):
    """處理 postback 事件"""
    data_post = event['postback']['data']
    
    # 檢查權限
    if user_id not in MASTER_USER_IDS and \
       user_id not in data['user_whitelist'] and \
       not line_utils.is_group_admin(user_id, group_id, data):
        line_utils.create_reply_message(line_bot_api, event['replyToken'],
                                       {"type": "text", "text": "❌ 只有授權使用者可以設定喲～"})
        return

    # 重設
    if data_post == 'reset':
        group_service._delete_group_langs_from_db(group_id)
        line_utils.create_reply_message(line_bot_api, event['replyToken'],
                                       {"type": "text", "text": "✅ 已清除翻譯語言設定！"})
        return

    # 選擇語言
    if data_post.startswith('lang:'):
        code = data_post.split(':')[1]
        current_langs = group_service.get_group_langs(group_id)
        if code in current_langs:
            current_langs.remove(code)
        else:
            current_langs.add(code)
        group_service.set_group_langs(group_id, current_langs)
        
        langs = [f"{label} ({code})" for label, code in config.LANGUAGE_MAP.items()
                 if code in group_service.get_group_langs(group_id)]
        langs_str = '\n'.join(langs) if langs else '(無)'
        
        line_utils.create_reply_message(line_bot_api, event['replyToken'],
                                       {"type": "text", "text": f"✅ 已更新翻譯語言！\n\n目前設定語言：\n{langs_str}"})
        return


def handle_message(event, user_id, group_id):
    """處理訊息事件"""
    msg_type = event['message'].get('type')
    if msg_type != 'text':
        return

    text = event['message']['text'].strip()
    lower = text.lower()

    # 自動翻譯
    auto_translate = data.get('auto_translate', {}).get(group_id, True)
    if auto_translate:
        langs = group_service.get_group_langs(group_id)
        threading.Thread(
            target=_async_translate_and_reply,
            args=(event['replyToken'], text, list(langs), group_id),
            daemon=True).start()
        return

    # 手動翻譯指令 (!翻譯)
    if text.startswith('!翻譯'):
        text_to_translate = text[3:].strip()
        if text_to_translate:
            langs = group_service.get_group_langs(group_id)
            threading.Thread(
                target=_async_translate_and_reply,
                args=(event['replyToken'], text_to_translate, list(langs), group_id),
                daemon=True).start()
        return

    # 其他指令處理（簡化版本）
    if lower in ['/狀態', '系統狀態']:
        uptime = time.time() - start_time
        uptime_str = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m"
        line_utils.create_reply_message(line_bot_api, event['replyToken'],
                                       {"type": "text", "text": f"⏰ 運行時間：{uptime_str}"})
        return

    if lower == '/選單':
        line_utils.create_reply_message(line_bot_api, event['replyToken'], language_selection_message(group_id))
        return

# ============== 其他路由 ==============
@app.route("/")
def home():
    return "🎉 FanFan LINE Bot (模組化版本) 已啟動 ✨"

@app.route("/status")
def status():
    """系統狀態檢查"""
    uptime = time.time() - start_time
    memory = system_utils.monitor_memory()
    return {
        "status": "ok",
        "uptime_seconds": int(uptime),
        "memory_mb": memory,
        "translation_queue": config.MAX_CONCURRENT_TRANSLATIONS
    }

# ============== 主程式 ==============
if __name__ == '__main__':
    try:
        # 初始化應用
        init_app()
        
        # 啟動自動檢查未使用群組
        system_utils.start_inactive_checker(app)
        
        # 啟動 Keep-Alive 線程
        keep_alive_thread = threading.Thread(target=system_utils.keep_alive, args=(app,), daemon=True)
        keep_alive_thread.start()
        print("✨ 系統初始化完成")
        
        # 檢查是否在 gunicorn 環境
        if 'gunicorn' not in os.getenv('SERVER_SOFTWARE', ''):
            # 本機開發用 Flask
            app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
        else:
            # gunicorn 環境會自動處理
            print("🦄 偵測到 gunicorn 環境，app 已就緒")
            
    except Exception as e:
        print(f"❌ 應用啟動失敗: {e}")
        sys.exit(1)
