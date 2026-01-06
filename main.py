from flask import Flask, request, send_from_directory
import os
import sys
import requests
import json
import time
import threading
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage

app = Flask(__name__)

# 資料庫設定（參考 web 專案的 DATABASE_URL）
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

db = None
if DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db = SQLAlchemy(app)

line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))

# --- 永久儲存 MASTER USER 功能 ---
MASTER_USER_FILE = "master_user_ids.json"
DEFAULT_MASTER_USER_IDS = {
    'U5ce6c382d12eaea28d98f2d48673b4b8', 'U2bcd63000805da076721eb62872bc39f',
    'Uea1646aa1a57861c85270d846aaee0eb', 'U8f3cc921a9dd18d3e257008a34dd07c1'
}

def load_master_users():
    if os.path.exists(MASTER_USER_FILE):
        with open(MASTER_USER_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    else:
        save_master_users(DEFAULT_MASTER_USER_IDS)
        return DEFAULT_MASTER_USER_IDS.copy()

def save_master_users(master_set):
    with open(MASTER_USER_FILE, "w", encoding="utf-8") as f:
        json.dump(list(master_set), f, ensure_ascii=False, indent=2)
        print("💾 主人列表已更新！")

MASTER_USER_IDS = load_master_users()

# --- 資料儲存相關 ---
data = {
    "user_whitelist": [],
    "user_prefs": {},
    "voice_translation": {},
    "group_admin": {}  # 新增：儲存群組暫時管理員
}

start_time = time.time()
translate_counter = 0
translate_char_counter = 0

def load_data():
    global data
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            try:
                loaded_data = json.load(f)
                data = {
                    "user_whitelist": loaded_data.get("user_whitelist", []),
                    "user_prefs": {
                        k: set(v) if isinstance(v, list) else v
                        for k, v in loaded_data.get("user_prefs", {}).items()
                    },
                    "voice_translation": loaded_data.get("voice_translation", {}),
                    "group_admin": loaded_data.get("group_admin", {})  # 新增
                }
                print("✅ 成功讀取資料！")
            except Exception as e:
                print("❌ 讀取 data.json 出錯，使用預設資料")
    else:
        print("🆕 沒找到資料，創建新的 data.json")
        save_data()

def save_data():
    save_data = {
        "user_whitelist": data["user_whitelist"],
        "user_prefs": {
            k: list(v) if isinstance(v, set) else v
            for k, v in data["user_prefs"].items()
        },
        "voice_translation": data["voice_translation"],
        "group_admin": data.get("group_admin", {})  # 新增
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
        print("💾 資料已儲存！")

load_data()


# --- 群組翻譯設定（資料庫 + 舊 data.json 並存） ---
if db:
    class GroupTranslateSetting(db.Model):  # type: ignore[misc]
        """群組翻譯設定：每個群組選擇的目標語言清單。"""

        __tablename__ = "group_translate_setting"

        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        group_id = db.Column(db.String(255), unique=True, nullable=False)
        # 以逗號分隔的語言代碼，例如："en,zh-TW,ja"
        languages = db.Column(db.String(255), nullable=False, default="en")
        created_at = db.Column(db.DateTime,
                               default=datetime.utcnow,
                               nullable=False)
        updated_at = db.Column(db.DateTime,
                               default=datetime.utcnow,
                               onupdate=datetime.utcnow,
                               nullable=False)


    with app.app_context():
        db.create_all()
else:
    # 沒有設定資料庫時提供一個空的 placeholder 類別，避免型別檢查錯誤
    class GroupTranslateSetting:  # type: ignore[misc]
        pass


def _load_group_langs_from_db(group_id):
    """從資料庫取得群組語言設定（set），若沒有設定則回傳 None。"""

    if not db or not group_id:
        return None
    try:
        setting = GroupTranslateSetting.query.filter_by(
            group_id=group_id).first()
        if not setting or not setting.languages:
            return None
        langs = [c.strip() for c in setting.languages.split(',') if c.strip()]
        return set(langs) if langs else None
    except Exception:
        return None


def _save_group_langs_to_db(group_id, langs):
    """儲存群組語言設定到資料庫，同時維持舊有 data.json 結構。"""

    # 先更新記憶體與 data.json（舊機制仍保留，作為 fallback 與統計用）
    if 'user_prefs' not in data:
        data['user_prefs'] = {}
    data['user_prefs'][group_id] = set(langs)
    save_data()

    if not db or not group_id:
        return
    try:
        setting = GroupTranslateSetting.query.filter_by(
            group_id=group_id).first()
        if not setting:
            setting = GroupTranslateSetting(group_id=group_id)
            db.session.add(setting)
        setting.languages = ','.join(sorted(langs)) if langs else ''
        db.session.commit()
    except Exception:
        db.session.rollback()


def _delete_group_langs_from_db(group_id):
    """刪除群組的資料庫設定（重設用）。"""

    if 'user_prefs' in data:
        data['user_prefs'].pop(group_id, None)
        save_data()

    if not db or not group_id:
        return
    try:
        setting = GroupTranslateSetting.query.filter_by(
            group_id=group_id).first()
        if setting:
            db.session.delete(setting)
            db.session.commit()
    except Exception:
        db.session.rollback()


def get_group_langs(group_id):
    """對外統一取得群組語言設定，優先使用資料庫，否則退回 data.json。"""

    langs = _load_group_langs_from_db(group_id)
    if langs is not None:
        return langs
    return data.get('user_prefs', {}).get(group_id, {'en'})


def set_group_langs(group_id, langs):
    """對外統一設定群組語言。"""

    _save_group_langs_to_db(group_id, langs)


def get_group_stats_for_status():
    """給 /狀態 與 /統計 用的群組統計資訊。"""

    if db:
        try:
            settings = GroupTranslateSetting.query.all()
            lang_sets = []
            for s in settings:
                if s.languages:
                    lang_sets.append(
                        set([c.strip() for c in s.languages.split(',')
                             if c.strip()]))
            return lang_sets
        except Exception:
            pass

    return list(data.get('user_prefs', {}).values())


LANGUAGE_MAP = {
    '🇹🇼 中文(台灣)': 'zh-TW',
    '🇺🇸 英文': 'en',
    '🇹🇭 泰文': 'th',
    '🇻🇳 越南文': 'vi',
    '🇲🇲 緬甸文': 'my',
    '🇰🇷 韓文': 'ko',
    '🇮🇩 印尼文': 'id',
    '🇯🇵 日文': 'ja',
    '🇷🇺 俄文': 'ru'
}

def create_command_menu():
    """創建指令選單"""
    return {
        "type": "flex",
        "altText": "⚡ 系統管理選單",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": "⚡ 系統管理面板",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#1DB446"
                }, {
                    "type": "text",
                    "text": "請選擇要執行的操作",
                    "size": "sm",
                    "color": "#666666"
                }],
                "backgroundColor": "#FFFFFF"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [{
                    "type": "button",
                    "style": "primary",
                    "color": "#1DB446",
                    "action": {
                        "type": "message",
                        "label": "📊 系統狀態",
                        "text": "/狀態"
                    },
                    "height": "sm"
                }, {
                    "type": "button",
                    "style": "primary",
                    "color": "#4A90E2",
                    "action": {
                        "type": "message",
                        "label": "💾 記憶體使用",
                        "text": "/記憶體"
                    },
                    "height": "sm"
                }, {
                    "type": "button",
                    "style": "primary",
                    "color": "#FF6B6B",
                    "action": {
                        "type": "message",
                        "label": "🔄 重啟系統",
                        "text": "/重啟"
                    },
                    "height": "sm"
                }, {
                    "type": "button",
                    "style": "primary",
                    "color": "#6B7280",
                    "action": {
                        "type": "message",
                        "label": "📝 今日流量",
                        "text": "/流量"
                    },
                    "height": "sm"
                }, {
                    "type": "button",
                    "style": "primary",
                    "color": "#805AD5",
                    "action": {
                        "type": "message",
                        "label": "👥 管理員列表",
                        "text": "/管理員列表"
                    },
                    "height": "sm"
                }]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": "🔒 系統管理專用",
                    "size": "sm",
                    "color": "#666666",
                    "align": "center"
                }]
            },
            "styles": {
                "header": {
                    "backgroundColor": "#F9FAFB"
                },
                "body": {
                    "backgroundColor": "#FFFFFF"
                },
                "footer": {
                    "separator": True
                }
            }
        }
    }

def language_selection_message(group_id):
    """群組翻譯語言選單，會依目前設定在按鈕前顯示 ✅。"""

    current_langs = get_group_langs(group_id)

    contents = []
    for label, code in LANGUAGE_MAP.items():
        selected = code in current_langs
        button_label = f"✅ {label}" if selected else label
        contents.append({
            "type": "button",
            "style": "primary",
            "color": "#1DB446" if selected else "#0099FF",
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
        "altText": "🌍 請選擇翻譯語言",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": "🌍 群組翻譯設定",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#0099FF"
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
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "contents": [{
                    "type": "text",
                    "text": "✅ 標記代表目前已啟用的翻譯語言。",
                    "align": "start",
                    "size": "xxs",
                    "wrap": True,
                    "color": "#666666"
                }]
            },
            "styles": {
                "body": {
                    "backgroundColor": "#E0F7FF"
                },
                "footer": {
                    "separator": True
                }
            }
        }
    }

DEEPL_API_KEY = os.getenv('DEEPL_API_KEY', '')
DEEPL_API_BASE_URL = os.getenv('DEEPL_API_BASE_URL', 'https://api-free.deepl.com')


def _translate_with_deepl(text, target_lang):
    """使用 DeepL API 翻譯，若語言不支援或錯誤則回傳 None。"""

    if not DEEPL_API_KEY:
        return None

    # 將本服務語言代碼轉成 DeepL 語言代碼
    deepl_lang_map = {
        'en': 'EN',
        'ja': 'JA',
        'ru': 'RU',
        'zh-TW': 'ZH-HANT',  # 傳統中文
    }
    deepl_target = deepl_lang_map.get(target_lang)
    if not deepl_target:
        return None

    url = f"{DEEPL_API_BASE_URL.rstrip('/')}/v2/translate"
    try:
        resp = requests.post(
            url,
            data={
                'auth_key': DEEPL_API_KEY,
                'text': text,
                'target_lang': deepl_target,
            },
            timeout=5,
        )
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None

    try:
        data_json = resp.json()
        translations = data_json.get('translations') or []
        if not translations:
            return None
        return translations[0].get('text')
    except Exception:
        return None


def _translate_with_google(text, target_lang):
    """使用 Google Translate 非官方 API，加入 timeout 與錯誤處理。"""

    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        'client': 'gtx',
        'sl': 'auto',
        'tl': target_lang,
        'dt': 't',
        'q': text,
    }
    try:
        res = requests.get(url, params=params, timeout=4)
    except requests.RequestException:
        return None

    if res.status_code != 200:
        return None

    try:
        return res.json()[0][0][0]
    except Exception:
        return None


def translate_text(text, target_lang):
    """統一翻譯入口：優先使用 DeepL，其次使用 Google。"""

    global translate_counter, translate_char_counter

    translated = _translate_with_deepl(text, target_lang)
    if translated is None:
        translated = _translate_with_google(text, target_lang)

    if translated is None:
        return "翻譯失敗QQ"

    translate_counter += 1
    translate_char_counter += len(text)
    return translated

def reply(token, message_content):
    if isinstance(message_content, dict):
        if message_content.get("type") == "flex":
            from linebot.models import FlexSendMessage
            message = FlexSendMessage(alt_text=message_content["altText"],
                                      contents=message_content["contents"])
        else:
            message = TextSendMessage(text=message_content["text"])
    elif isinstance(message_content, list):
        message = [
            TextSendMessage(text=m["text"]) if m["type"] == "text" else m
            for m in message_content
        ]
    line_bot_api.reply_message(token, message)

def is_group_admin(user_id, group_id):
    return data.get('group_admin', {}).get(group_id) == user_id

@app.route("/webhook", methods=['POST'])
def webhook():
    body = request.get_json()
    events = body.get("events", [])
    for event in events:
        source = event.get("source", {})
        group_id = source.get("groupId") or source.get("userId")
        user_id = source.get("userId")
        if not group_id or not user_id:
            continue
        event_type = event.get("type")

        # --- 機器人被加進群組時公告 + 自動跳出語言選單 ---
        if event_type == 'join':
            reply(event['replyToken'], [
                {
                    "type": "text",
                    "text": "👋 歡迎邀請翻譯小精靈進入群組！\n\n請本群管理員或群主按下下面的「翻譯設定」，選擇要翻譯成哪些語言，之後群組內的訊息就會自動翻譯。"
                },
                language_selection_message(group_id)
            ])
            continue

        # --- 處理 postback 設定語言 ---
        if event_type == 'postback':
            data_post = event['postback']['data']
            if user_id not in MASTER_USER_IDS and \
               user_id not in data['user_whitelist'] and \
               not is_group_admin(user_id, group_id):
                reply(event['replyToken'], {
                    "type": "text",
                    "text": "❌ 只有授權使用者可以更改翻譯設定喲～"
                })
                continue
            if data_post == 'reset':
                _delete_group_langs_from_db(group_id)
                reply(event['replyToken'], {
                    "type": "text",
                    "text": "✅ 已清除翻譯語言設定！"
                })
            elif data_post.startswith('lang:'):
                code = data_post.split(':')[1]
                current_langs = get_group_langs(group_id)
                if code in current_langs:
                    current_langs.remove(code)
                else:
                    current_langs.add(code)
                set_group_langs(group_id, current_langs)
                langs = [
                    f"{label} ({code})"
                    for label, code in LANGUAGE_MAP.items()
                    if code in get_group_langs(group_id)
                ]
                langs_str = '\n'.join(langs) if langs else '(無)'
                reply(event['replyToken'], {
                    "type": "text",
                    "text": f"✅ 已更新翻譯語言！\n\n目前設定語言：\n{langs_str}"
                })

        elif event_type == 'message':
            msg_type = event['message']['type']
            if msg_type != 'text':
                continue
            text = event['message']['text'].strip()
            lower = text.lower()

            # --- 認證暫時管理員 ---
            if text == "管理員認證":
                if group_id and group_id not in data.get('group_admin', {}):
                    data.setdefault('group_admin', {})
                    data['group_admin'][group_id] = user_id
                    save_data()
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "✅ 已設為本群暫時管理員，可以設定翻譯語言！"
                    })
                else:
                    if is_group_admin(user_id, group_id):
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "你已是本群的暫時管理員！"
                        })
                    else:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "本群已有暫時管理員，如需更換請聯絡主人。"
                        })
                continue

            # --- 主人換管理員 ---
            if (lower.startswith('/換管理員') or lower.startswith('換管理員')) and user_id in MASTER_USER_IDS:
                parts = text.replace('　', ' ').split()
                if len(parts) == 2:
                    new_admin = parts[1]
                    data.setdefault('group_admin', {})
                    data['group_admin'][group_id] = new_admin
                    save_data()
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": f"✅ 已將本群暫時管理員更換為 {new_admin[-5:]}"
                    })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 格式錯誤，請使用 `/換管理員 [USER_ID]`"
                    })
                continue

            # --- 查詢群組管理員 ---
            if lower in ['/查群管理員', '查群管理員']:
                admin_id = data.get('group_admin', {}).get(group_id)
                if user_id in MASTER_USER_IDS or is_group_admin(user_id, group_id):
                    if admin_id:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": f"本群暫時管理員為：{admin_id}"
                        })
                    else:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "本群尚未設定暫時管理員。"
                        })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限查詢本群管理員喲～"
                    })
                continue

            # 只有主人可以用系統管理（指令權限不變）
            if '我的id' in lower:
                reply(event['replyToken'], {
                    "type": "text",
                    "text": f"🪪 你的 ID 是：{user_id}"
                })
                continue
            if lower.startswith('/增加主人 id') and user_id in MASTER_USER_IDS:
                parts = text.split()
                if len(parts) == 3:
                    new_master = parts[2]
                    MASTER_USER_IDS.add(new_master)
                    save_master_users(MASTER_USER_IDS)
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": f"✅ 已新增新的主人：{new_master[-5:]}"
                    })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 格式錯誤，請使用 `/增加主人 ID [UID]`"
                    })
                continue
            if lower == '/管理員列表':
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist']:
                    masters = '\n'.join(
                        [f'👑 {uid[-5:]}' for uid in MASTER_USER_IDS])
                    whitelist = '\n'.join([
                        f'👤 {uid[-5:]}' for uid in data['user_whitelist']
                    ]) if data['user_whitelist'] else '（無）'
                    reply(
                        event['replyToken'], {
                            "type":
                            "text",
                            "text":
                            f"📋 【主人列表】\n{masters}\n\n📋 【授權管理員】\n{whitelist}"
                        })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限查看管理員列表喲～"
                    })
                continue
            if lower in ['/指令']:
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist']:
                    reply(event['replyToken'], create_command_menu())
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限查看管理選單喲～"
                    })
                continue

            # --- 語言選單（中文化，保留舊指令） ---
            if lower in ['/選單', '/menu', 'menu', '翻譯選單', '/翻譯選單']:
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist'] or is_group_admin(user_id, group_id):
                    reply(event['replyToken'], language_selection_message(group_id))
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限設定翻譯語言喲～"
                    })
                continue

            if lower == '/記憶體':
                if user_id in MASTER_USER_IDS:
                    memory_usage = monitor_memory()
                    reply(
                        event['replyToken'], {
                            "type":
                            "text",
                            "text":
                            f"💾 系統記憶體使用狀況\n\n"
                            f"當前使用：{memory_usage:.2f} MB\n"
                            f"使用比例：{psutil.Process().memory_percent():.1f}%\n"
                            f"系統總計：{psutil.virtual_memory().total / (1024*1024):.0f} MB"
                        })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 只有主人可以查看記憶體使用狀況喲～"
                    })
                continue

            if lower in ['/重啟', '/restart', 'restart']:
                if user_id in MASTER_USER_IDS:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "⚡ 系統即將重新啟動...\n請稍候約10秒鐘..."
                    })
                    print("🔄 執行手動重啟...")
                    time.sleep(1)
                    try:
                        # 關閉 Flask server
                        func = request.environ.get('werkzeug.server.shutdown')
                        if func is not None:
                            func()
                        time.sleep(2)  # 等待port釋放
                        os.execv(sys.executable, ['python'] + sys.argv)
                    except:
                        os._exit(1)
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 只有主人可以重啟系統喲～"
                    })
                continue
            if lower in ['/狀態', '系統狀態']:
                uptime = time.time() - start_time
                uptime_str = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m"
                lang_sets = get_group_stats_for_status()
                group_count = len(lang_sets)
                reply(
                    event['replyToken'], {
                        "type":
                        "text",
                        "text":
                        f"⏰ 運行時間：{uptime_str}\n📚 翻譯次數：{translate_counter}\n🔠 累積字元：{translate_char_counter}\n👥 群組/用戶數量：{group_count}"
                    })
                continue
            if lower == '/流量':
                reply(
                    event['replyToken'], {
                        "type": "text",
                        "text": f"🔢 今日翻譯總字元數：{translate_char_counter} 個字元"
                    })
                continue
            if lower in ['/統計', '翻譯統計']:
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist']:
                    lang_sets = get_group_stats_for_status()
                    group_count = len(lang_sets)
                    total_langs = sum(len(langs) for langs in lang_sets)
                    avg_langs = total_langs / group_count if group_count > 0 else 0
                    all_langs = set(lang for langs in lang_sets for lang in langs)
                    most_used = max(
                        all_langs,
                        key=lambda x: sum(1 for langs in lang_sets if x in langs),
                        default="無")
                    stats = f"📊 群組統計\n\n👥 總群組數：{group_count}\n🌐 平均語言數：{avg_langs:.1f}\n⭐️ 最常用語言：{most_used}\n💬 總翻譯次數：{translate_counter}\n📝 總字元數：{translate_char_counter}"
                    reply(event['replyToken'], {"type": "text", "text": stats})
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限查看統計資料喲～"
                    })
                continue
            if lower in ['/選單', '選單', 'menu', '翻譯選單', '/翻譯選單']:
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist'] or is_group_admin(user_id, group_id):
                    reply(event['replyToken'], language_selection_message(group_id))
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限設定翻譯語言喲～"
                    })
                continue
            if lower == '語音翻譯':
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist'] or is_group_admin(user_id, group_id):
                    current_status = data['voice_translation'].get(
                        group_id, True)
                    data['voice_translation'][group_id] = not current_status
                    status_text = "開啟" if not current_status else "關閉"
                    save_data()
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": f"✅ 語音翻譯已{status_text}！"
                    })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限設定語音翻譯喲～"
                    })
                continue

            if lower == '自動翻譯':
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist'] or is_group_admin(user_id, group_id):
                    if 'auto_translate' not in data:
                        data['auto_translate'] = {}
                    current_status = data['auto_translate'].get(group_id, True)
                    data['auto_translate'][group_id] = not current_status
                    status_text = "開啟" if not current_status else "關閉"
                    save_data()
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": f"✅ 自動翻譯已{status_text}！"
                    })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限設定自動翻譯喲～"
                    })
                continue

            if lower in ['重設', '重設翻譯設定']:
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist'] or is_group_admin(user_id, group_id):
                    _delete_group_langs_from_db(group_id)
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "✅ 翻譯設定已重設！"
                    })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限重設翻譯設定喲～"
                    })
                continue

            # 檢查是否開啟自動翻譯
            auto_translate = data.get('auto_translate', {}).get(group_id, True)
            if auto_translate:
                langs = get_group_langs(group_id)
                results = [
                    f"[{lang}] {translate_text(text, lang)}" for lang in langs
                ]
                reply(event['replyToken'], {
                    "type": "text",
                    "text": '\n'.join(results)
                })
            elif text.startswith('!翻譯'):  # 手動翻譯指令
                text_to_translate = text[3:].strip()
                if text_to_translate:
                    langs = get_group_langs(group_id)
                    results = [
                        f"[{lang}] {translate_text(text_to_translate, lang)}"
                        for lang in langs
                    ]
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": '\n'.join(results)
                    })
    return 'OK'

@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory('images', filename)

@app.route("/")
def home():
    return "🎉 翻譯小精靈啟動成功 ✨"

def monitor_memory():
    """監控系統記憶體使用情況"""
    import psutil
    import gc
    process = psutil.Process()
    memory_info = process.memory_info()
    memory_usage_mb = memory_info.rss / 1024 / 1024

    # 強制進行垃圾回收
    gc.collect()
    process.memory_percent()

    return memory_usage_mb

import psutil

def keep_alive():
    """每5分鐘檢查服務狀態"""
    retry_count = 0
    max_retries = 3
    restart_interval = 10800  # 每3小時重啟一次
    last_restart = time.time()
    
    while True:
        try:
            current_time = time.time()
            
            if current_time - last_restart >= restart_interval:
                print("⏰ 執行定時重啟...")
                save_data()
                os._exit(0)

            response = requests.get('http://0.0.0.0:5000/', timeout=10)
            if response.status_code == 200:
                print("🔄 Keep-Alive請求成功")
                retry_count = 0
            else:
                raise Exception(f"請求返回狀態碼: {response.status_code}")
        except Exception as e:
            retry_count += 1
            print(f"❌ Keep-Alive請求失敗 (重試 {retry_count}/{max_retries})")
            
            if retry_count >= max_retries:
                print("🔄 重啟伺服器...")
                os._exit(1)
                
            time.sleep(30)
            continue

        time.sleep(300)  # 5分鐘檢查一次

if __name__ == '__main__':
    max_retries = 3
    retry_count = 0

    while True:
        try:
            # 啟動Keep-Alive線程
            keep_alive_thread = threading.Thread(target=keep_alive,
                                                 daemon=True)
            keep_alive_thread.start()
            print("✨ Keep-Alive機制已啟動")

            # 運行Flask應用
            app.run(host='0.0.0.0', port=5000)
        except Exception as e:
            retry_count += 1
            print(f"❌ 發生錯誤 (重試 {retry_count}/{max_retries}): {str(e)}")

            if retry_count >= max_retries:
                print("🔄 達到最大重試次數,完全重啟程序...")
                os._exit(1)

            print(f"🔄 5秒後重試...")
            time.sleep(5)
            continue
