from flask import Flask, request
import os, json, time, threading
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage, FlexSendMessage

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

MASTER_IDS = {"U5ce6c382d12eaea28d98f2d48673b4b8"}  # 主人 ID
data = {"group_admins": {}, "user_prefs": {}, "user_whitelist": []}
LANGUAGE_MAP = {'🇹🇼 中文': 'zh-TW', '🇺🇸 英文': 'en', '🇹🇭 泰文': 'th'}

def save_data():
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_data():
    global data
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            data = json.load(f)

def reply(token, message):
    if isinstance(message, dict):
        msg = FlexSendMessage(alt_text=message["altText"], contents=message["contents"])
    else:
        msg = TextSendMessage(text=message)
    line_bot_api.reply_message(token, msg)

def menu():
    return {
        "type": "flex",
        "altText": "🌿 翻譯設定選單",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "🌍 請選擇翻譯語言", "weight": "bold", "size": "lg"},
                    *[{
                        "type": "button",
                        "action": {"type": "postback", "label": name, "data": f"lang:{code}"},
                        "style": "primary"
                    } for name, code in LANGUAGE_MAP.items()],
                    {"type": "button", "style": "secondary",
                     "action": {"type": "postback", "label": "🔄 重設", "data": "reset"}}
                ]
            }
        }
    }

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    for event in body.get("events", []):
        uid = event["source"].get("userId")
        gid = event["source"].get("groupId")
        token = event.get("replyToken")

        if event["type"] == "join" and gid:
            data["group_admins"][gid] = uid
            reply(token, menu())
            save_data()
            continue

        if event["type"] == "postback":
            if gid not in data["group_admins"] or uid != data["group_admins"][gid]:
                reply(token, "❌ 只有本群管理員可設定翻譯語言喲～")
                continue
            key = event["postback"]["data"]
            if key == "reset":
                data["user_prefs"].pop(gid, None)
            elif key.startswith("lang:"):
                lang = key.split(":")[1]
                prefs = data["user_prefs"].setdefault(gid, [])
                if lang in prefs:
                    prefs.remove(lang)
                else:
                    prefs.append(lang)
            save_data()
            reply(token, f"✅ 已更新語言：{data['user_prefs'].get(gid, [])}")
            continue

        if event["type"] == "message" and event["message"]["type"] == "text":
            txt = event["message"]["text"].lower()
            if txt == "/指令":
                if uid in MASTER_IDS:
                    reply(token, "👑 系統指令：/狀態 /管理員")
                else:
                    reply(token, "❌ 你不是系統管理員")
    return "OK"

@app.route("/")
def index():
    return "🌿 FanFan 機器人啟動囉！"

load_data()

def keep_alive():
    while True:
        try:
            requests.get("http://0.0.0.0:5000/")
            print("💚 Ping 成功")
        except:
            print("❌ Ping 失敗")
        time.sleep(1200)

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
