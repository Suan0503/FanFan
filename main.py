"""
FanFan LINE Bot - 主程式入口
應用架構：
- config.py: 環境變數與常數
- services/: 業務邏輯服務層
  - translation.py: 翻譯服務 (Google, DeepL)
  - tenant.py: 租戶管理
  - group.py: 群組設定
  - engine.py: 翻譯引擎偏好
  - activity.py: 活動追蹤
- handlers/: 事件處理層
  - events.py: Webhook 事件處理
- utils/: 工具函數層
  - data.py: 資料持久化
  - master_users.py: 主人列表管理
  - monitoring.py: 系統監控
"""
import os
import sys
import threading
import time
import hmac
import hashlib
import base64
import json
import requests
from datetime import datetime

from flask import Flask, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage, FlexSendMessage

# 導入配置和模組
import config
from utils import get_data, save_data, load_data, load_master_users
from services import (
    translate_text, _format_translation_results, translation_semaphore,
    _load_deepl_supported_languages, create_tenant, get_tenant_by_group,
    is_tenant_valid, add_group_to_tenant, update_tenant_stats,
    get_group_langs, set_group_langs, get_group_stats_for_status,
    get_engine_pref, set_engine_pref, touch_group_activity, check_inactive_groups
)
from handlers import handle_webhook_events

# ============================================================================
# Flask 應用初始化
# ============================================================================
app = Flask(__name__)

# 資料庫設定
db = None
if config.DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db = SQLAlchemy(app)

# LINE Bot 初始化
line_bot_api = LineBotApi(config.CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(config.CHANNEL_SECRET.decode('utf-8'))

# 全域變數
start_time = time.time()
MASTER_USER_IDS = load_master_users()

# ============================================================================
# 資料庫模型（如果使用資料庫）
# ============================================================================
if db:
    class GroupTranslateSetting(db.Model):
        """群組翻譯設定"""
        __tablename__ = "group_translate_setting"
        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        group_id = db.Column(db.String(255), unique=True, nullable=False)
        languages = db.Column(db.String(255), nullable=False, default="en")
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    class GroupActivity(db.Model):
        """群組活動記錄"""
        __tablename__ = "group_activity"
        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        group_id = db.Column(db.String(255), unique=True, nullable=False)
        last_active_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    class GroupEnginePreference(db.Model):
        """群組翻譯引擎偏好"""
        __tablename__ = "group_engine_preference"
        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        group_id = db.Column(db.String(255), unique=True, nullable=False)
        engine = db.Column(db.String(20), nullable=False, default="google")
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    with app.app_context():
        db.create_all()

else:
    # 無資料庫時的 placeholder
    class GroupTranslateSetting:
        pass
    class GroupActivity:
        pass
    class GroupEnginePreference:
        pass

# ============================================================================
# 啟動初期化
# ============================================================================
try:
    load_data()
except Exception as e:
    print(f"Warning: Failed to load data: {e}")

if config.DEEPL_API_KEY:
    try:
        _load_deepl_supported_languages()
    except Exception as e:
        print(f"Warning: Failed to load DeepL languages: {e}")



# ============================================================================
# 輔助函數
# ============================================================================
def reply(token, message_content):
    """回覆 LINE 訊息"""
    if isinstance(message_content, dict):
        if message_content.get("type") == "flex":
            message = FlexSendMessage(alt_text=message_content["altText"],
                                      contents=message_content["contents"])
        else:
            message = TextSendMessage(text=message_content.get("text", ""))
    elif isinstance(message_content, list):
        converted = []
        for m in message_content:
            if isinstance(m, (TextSendMessage, FlexSendMessage)):
                converted.append(m)
            elif isinstance(m, dict):
                if m.get("type") == "flex":
                    converted.append(FlexSendMessage(alt_text=m["altText"],
                                                     contents=m["contents"]))
                else:
                    converted.append(TextSendMessage(text=m.get("text", "")))
        message = converted
    else:
        message = TextSendMessage(text=str(message_content))
    
    line_bot_api.reply_message(token, message)


def is_group_admin(user_id, group_id):
    """檢查是否為群組管理員"""
    data = get_data()
    return data.get('group_admin', {}).get(group_id) == user_id


def _async_translate_and_reply(reply_token, text, langs, prefer_deepl_first=False, group_id=None):
    """背景執行緒翻譯並回覆"""
    acquired = translation_semaphore.acquire(blocking=False)
    if not acquired:
        print(f"[Translation] Thread pool exhausted, rejecting request")
        try:
            line_bot_api.reply_message(reply_token,
                                       TextSendMessage(text="Translation service is busy, please try again later"))
        except:
            pass
        return

    try:
        lang_list = list(langs)
        result_text = _format_translation_results(text, lang_list, prefer_deepl_first=prefer_deepl_first, group_id=group_id)
        line_bot_api.reply_message(reply_token,
                                   TextSendMessage(text=result_text))
    except Exception as e:
        print(f"[Translation] Async reply failed: {type(e).__name__}: {e}")
    finally:
        translation_semaphore.release()


def create_command_menu():
    """建立指令選單"""
    return {
        "type": "flex",
        "altText": "🎊 管理選單",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": "🎊 管理面板",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#FF0000"
                }],
                "backgroundColor": "#FFF5F5"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [{
                    "type": "button",
                    "style": "primary",
                    "color": "#DC143C",
                    "action": {
                        "type": "message",
                        "label": "📊 系統狀態",
                        "text": "/狀態"
                    }
                }, {
                    "type": "button",
                    "style": "primary",
                    "color": "#FF6347",
                    "action": {
                        "type": "message",
                        "label": "📝 翻譯設定",
                        "text": "/選單"
                    }
                }]
            }
        }
    }


def language_selection_message(group_id):
    """語言選擇訊息"""
    current_langs = get_group_langs(group_id)
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
            "label": "🔄 重設",
            "data": "reset"
        }
    })

    return {
        "type": "flex",
        "altText": "翻譯設定",
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


# ============================================================================
# Webhook 路由
# ============================================================================
@app.route("/webhook", methods=['POST'])
def webhook():
    """LINE Webhook 端點"""
    # 簽名驗證
    signature = request.headers.get('X-Line-Signature', '')
    body_text = request.get_data(as_text=True)
    
    if config.CHANNEL_SECRET:
        hash_obj = hmac.new(config.CHANNEL_SECRET, body_text.encode('utf-8'), hashlib.sha256)
        expected_signature = base64.b64encode(hash_obj.digest()).decode('utf-8')
        if signature != expected_signature:
            print(f"[Webhook] Signature verification failed")
            return 'Invalid signature', 400
    
    # 解析事件
    try:
        body = json.loads(body_text)
    except:
        return 'Invalid JSON', 400
    
    events = body.get("events", [])
    data = get_data()
    
    for event in events:
        source = event.get("source", {})
        group_id = source.get("groupId") or source.get("userId")
        user_id = source.get("userId")
        
        if not group_id or not user_id:
            continue
        
        event_type = event.get("type")
        
        # 群組事件
        if raw_group_id := source.get("groupId"):
            touch_group_activity(raw_group_id)
        
        # === 機器人加入群組 ===
        if event_type == 'join':
            reply(event['replyToken'], [
                {
                    "type": "text",
                    "text": "👋 歡迎邀請翻譯小精靈！\n\n請按下「翻譯設定」選擇要翻譯的語言。"
                },
                language_selection_message(group_id)
            ])
            continue
        
        # === Postback 事件（語言選擇） ===
        if event_type == 'postback':
            data_post = event['postback']['data']
            is_privileged = user_id in MASTER_USER_IDS or user_id in data.get('user_whitelist', []) or is_group_admin(user_id, group_id)
            
            if not is_privileged:
                reply(event['replyToken'], {"type": "text", "text": "❌ 你沒有權限設定喲～"})
                continue
            
            if data_post == 'reset':
                # 重設語言設定
                set_group_langs(group_id, config.DEFAULT_TRANSLATE_LANGS)
                reply(event['replyToken'], {"type": "text", "text": "✅ 已重設翻譯設定！"})
            elif data_post.startswith('lang:'):
                code = data_post.split(':')[1]
                current_langs = get_group_langs(group_id)
                if code in current_langs:
                    current_langs.remove(code)
                else:
                    current_langs.add(code)
                set_group_langs(group_id, current_langs)
                
                langs_str = '\n'.join([f"{label} ({code})" for label, code in config.LANGUAGE_MAP.items() if code in current_langs]) or '(無)'
                reply(event['replyToken'], {"type": "text", "text": f"✅ 已更新！\n\n{langs_str}"})
            continue
        
        # === 文字訊息 ===
        if event_type == 'message':
            msg_type = event['message']['type']
            if msg_type != 'text':
                continue
            
            text = event['message']['text'].strip()
            lower = text.lower()
            
            # 系統指令
            if lower == '/狀態':
                uptime = time.time() - start_time
                uptime_str = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m"
                reply(event['replyToken'], {
                    "type": "text",
                    "text": f"⏰ 運行時間：{uptime_str}\n👥 群組數量：{len(get_group_stats_for_status())}"
                })
                continue
            
            if lower in ['/選單', '/menu']:
                reply(event['replyToken'], language_selection_message(group_id))
                continue
            
            if lower == '/指令' and user_id in MASTER_USER_IDS:
                reply(event['replyToken'], create_command_menu())
                continue
            
            # 自動翻譯
            auto_translate = data.get('auto_translate', {}).get(group_id, True)
            if auto_translate:
                langs = get_group_langs(group_id)
                if langs:
                    threading.Thread(
                        target=_async_translate_and_reply,
                        args=(event['replyToken'], text, list(langs), False, group_id),
                        daemon=True
                    ).start()
                continue
    
    return 'OK'


# ============================================================================
# 靜態文件路由
# ============================================================================
@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory('images', filename)


@app.route("/")
def home():
    return "🎉 翻譯小精靈啟動成功 ✨"


# ============================================================================
# 背景工作
# ============================================================================
def keep_alive():
    """保活機制"""
    if os.getenv('RAILWAY_ENVIRONMENT'):
        print("[System] Railway environment detected, disabling keep_alive")
        return
    
    retry_count = 0
    max_retries = 3
    last_restart = time.time()
    
    while True:
        try:
            current_time = time.time()
            
            if current_time - last_restart >= config.RESTART_INTERVAL:
                print("[System] Executing scheduled restart...")
                save_data()
                os._exit(0)

            response = requests.get('http://0.0.0.0:5000/', timeout=10)
            if response.status_code == 200:
                print("[System] Keep-Alive request successful")
                retry_count = 0
            else:
                raise Exception(f"HTTP status code: {response.status_code}")
        except Exception as e:
            retry_count += 1
            print(f"[System] Keep-Alive failed (retry {retry_count}/{max_retries})")
            
            if retry_count >= max_retries:
                print("[System] Restarting server...")
                os._exit(1)
            
            time.sleep(30)
            continue

        time.sleep(300)  # 5 分鐘檢查一次


# ============================================================================
# 主程式入口
# ============================================================================
if __name__ == '__main__':
    if 'gunicorn' in os.getenv('SERVER_SOFTWARE', ''):
        print("[System] Gunicorn detected, not starting Flask development server")
    else:
        max_retries = 3
        retry_count = 0

        while True:
            try:
                # 啟動保活執行緒
                keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
                keep_alive_thread.start()
                print("[System] Application started")

                # 運行 Flask
                app.run(host='0.0.0.0', port=5000)
            except Exception as e:
                retry_count += 1
                print(f"[System] Error occurred (retry {retry_count}/{max_retries}): {str(e)}")

                if retry_count >= max_retries:
                    print("[System] Max retries reached, restarting process...")
                    os._exit(1)

                print(f"[System] Retrying in 5 seconds...")
                time.sleep(5)
                continue
