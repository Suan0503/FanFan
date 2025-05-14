from flask import Flask, request, send_from_directory
import os
import sys
import requests
import json
import time
import threading
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextSendMessage, ImageSendMessage

app = Flask(__name__)
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
data = {"user_whitelist": [], "user_prefs": {}, "voice_translation": {}}

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
                    "voice_translation":
                    loaded_data.get("voice_translation", {})
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
        "voice_translation": data["voice_translation"]
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
        print("💾 資料已儲存！")


load_data()

LANGUAGE_MAP = {
    '🇹🇼 中文': 'zh-TW',
    '🇺🇸 英文': 'en',
    '🇹🇭 泰文': 'th',
    '🇻🇳 越南文': 'vi',
    '🇲🇲 緬甸文': 'my',
    '🇰🇷 韓文': 'ko',
    '🇮🇩 印尼文': 'id',
    '🇯🇵 日語': 'ja',
    '🇷🇺 俄羅斯': 'ru'
}


def create_command_menu():
    """創建指令選單"""
    return {
        "type": "flex",
        "altText": "⚡ 系統管理選單",
        "contents": {
            "type": "bubble",
            "header": {
                "type":
                "box",
                "layout":
                "vertical",
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
                "backgroundColor":
                "#FFFFFF"
            },
            "body": {
                "type":
                "box",
                "layout":
                "vertical",
                "spacing":
                "md",
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
                "type":
                "box",
                "layout":
                "vertical",
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


def language_selection_message():
    contents = [{
        "type": "button",
        "style": "primary",
        "color": "#0099FF",
        "action": {
            "type": "postback",
            "label": label,
            "data": f"lang:{code}"
        }
    } for label, code in LANGUAGE_MAP.items()]
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
                "type":
                "box",
                "layout":
                "vertical",
                "contents": [{
                    "type": "text",
                    "text": "🌍 翻譯小精靈選單",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#0099FF"
                }, {
                    "type": "text",
                    "text": "請選擇你要翻譯的語言 ✈️",
                    "size": "sm",
                    "color": "#555555"
                }]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": contents
            },
            "footer": {
                "type":
                "box",
                "layout":
                "horizontal",
                "contents": [{
                    "type": "text",
                    "text": "🏝️",
                    "align": "end",
                    "size": "lg"
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


# 移除語音處理功能


def process_image(image_path):
    from PIL import Image
    import pytesseract
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text.strip() or "無法識別圖片中的文字"
    except:
        return "圖片處理失敗"


def suggest_languages(user_id):
    user_history = data.get('translation_history', {}).get(user_id, [])
    if not user_history:
        return ['en']  # 默認英文
    from collections import Counter
    counts = Counter(lang for _, lang in user_history)
    return [lang for lang, _ in counts.most_common(2)]


def translate_text(text, target_lang):
    global translate_counter, translate_char_counter
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={text}"
    res = requests.get(url)
    if res.status_code == 200:
        translate_counter += 1
        translate_char_counter += len(text)
        return res.json()[0][0][0]
    else:
        return "翻譯失敗QQ"


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

        # 處理加入群組事件
        if event_type == 'join':
            reply(event['replyToken'], language_selection_message())
            continue

        if event_type == 'postback':
            data_post = event['postback']['data']
            if user_id not in MASTER_USER_IDS and user_id not in data[
                    'user_whitelist']:
                reply(event['replyToken'], {
                    "type": "text",
                    "text": "❌ 只有授權使用者可以更改翻譯設定喲～"
                })
                continue
            if data_post == 'reset':
                data['user_prefs'].pop(group_id, None)
                save_data()
                reply(event['replyToken'], {
                    "type": "text",
                    "text": "✅ 已清除翻譯語言設定！"
                })
            elif data_post.startswith('lang:'):
                code = data_post.split(':')[1]
                if group_id not in data['user_prefs']:
                    data['user_prefs'][group_id] = set()
                if isinstance(data['user_prefs'][group_id], list):
                    data['user_prefs'][group_id] = set(
                        data['user_prefs'][group_id])
                if code in data['user_prefs'][group_id]:
                    data['user_prefs'][group_id].remove(code)
                else:
                    data['user_prefs'][group_id].add(code)
                save_data()
                langs = [
                    f"{label} ({code})"
                    for label, code in LANGUAGE_MAP.items()
                    if code in data['user_prefs'][group_id]
                ]
                langs_str = '\n'.join(langs) if langs else '(無)'
                reply_text = f"✅ 已更新翻譯語言！\n\n目前設定語言：\n{langs_str}"
                reply(event['replyToken'], {
                    "type": "text",
                    "text": f"目前設定語言：{langs}"
                })

        elif event_type == 'message':
            msg_type = event['message']['type']
            if msg_type == 'text':
                text = event['message']['text'].strip()
            else:
                continue
            lower = text.lower()

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

            if lower in ['/選單', '/menu', 'menu']:
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist']:
                    reply(event['replyToken'], language_selection_message())
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
            if lower == '/狀態':
                uptime = time.time() - start_time
                uptime_str = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m"
                reply(
                    event['replyToken'], {
                        "type":
                        "text",
                        "text":
                        f"⏰ 運行時間：{uptime_str}\n📚 翻譯次數：{translate_counter}\n🔠 累積字元：{translate_char_counter}\n👥 群組/用戶數量：{len(data['user_prefs'])}"
                    })
                continue
            if lower == '/流量':
                reply(
                    event['replyToken'], {
                        "type": "text",
                        "text": f"🔢 今日翻譯總字元數：{translate_char_counter} 個字元"
                    })
                continue
            # 圖片相關功能已移除
            if lower == '/統計':
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist']:
                    group_count = len(data['user_prefs'])
                    total_langs = sum(
                        len(langs) for langs in data['user_prefs'].values())
                    avg_langs = total_langs / group_count if group_count > 0 else 0
                    most_used = max(
                        set(lang for langs in data['user_prefs'].values()
                            for lang in langs),
                        key=lambda x: sum(1 for langs in data['user_prefs'].
                                          values() if x in langs),
                        default="無")
                    stats = f"📊 群組統計\n\n👥 總群組數：{group_count}\n🌐 平均語言數：{avg_langs:.1f}\n⭐️ 最常用語言：{most_used}\n💬 總翻譯次數：{translate_counter}\n📝 總字元數：{translate_char_counter}"
                    reply(event['replyToken'], {"type": "text", "text": stats})
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限查看統計資料喲～"
                    })
                continue
            if lower in ['/選單', '選單', 'menu']:
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist']:
                    reply(event['replyToken'], language_selection_message())
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限設定翻譯語言喲～"
                    })
                continue
            if lower == '語音翻譯':
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist']:
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
                        'user_whitelist']:
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

            if lower == '重設':
                if user_id in MASTER_USER_IDS or user_id in data[
                        'user_whitelist']:
                    data['user_prefs'].pop(group_id, None)
                    save_data()
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
                langs = data['user_prefs'].get(group_id, {'en'})
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
                    langs = data['user_prefs'].get(group_id, {'en'})
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


# 移除圖片相關功能


def monitor_memory():
    """監控系統記憶體使用情況"""
    import psutil
    import gc
    process = psutil.Process()
    memory_info = process.memory_info()
    memory_usage_mb = memory_info.rss / 1024 / 1024

    # 強制進行垃圾回收
    gc.collect()

    # 清理未使用的變數
    process.memory_percent()

    return memory_usage_mb


def log_error(error_msg, exc_info=None):
    """詳細的錯誤日誌記錄"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    memory_usage = monitor_memory()
    error_log = f"[{timestamp}] 錯誤: {error_msg}\n"
    error_log += f"記憶體使用: {memory_usage:.2f} MB\n"
    if exc_info:
        import traceback
        error_log += f"詳細錯誤:\n{traceback.format_exc()}\n"
    print(error_log)
    with open("error.log", "a", encoding="utf-8") as f:
        f.write(error_log + "\n")


def clean_files():
    """清理系統檔案"""
    # 清理錯誤日誌
    if os.path.exists("error.log") and os.path.getsize("error.log") > 1024 * 1024:  # 1MB
        with open("error.log", "w") as f:
            f.write("")
        print("🧹 已清理錯誤日誌")

    # 清理圖片資料夾
    if os.path.exists("images"):
        for file in os.listdir("images"):
            if time.time() - os.path.getctime(f"images/{file}") > 86400:  # 24小時
                os.remove(f"images/{file}")

import psutil  # 添加 psutil 導入

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

        time.sleep(900)  # 15分鐘檢查一次


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
