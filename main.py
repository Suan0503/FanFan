from flask import Flask, request
import os, json, time, threading, requests
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage, FlexSendMessage

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))

data = {"user_prefs": {}}
LANGUAGE_MAP = {
    '🇹🇼 中文': 'zh-TW', '🇺🇸 英文': 'en', '🇹🇭 泰文': 'th',
    '🇻🇳 越南文': 'vi', '🇲🇲 緬甸文': 'my', '🇰🇷 韓文': 'ko',
    '🇮🇩 印尼文': 'id', '🇯🇵 日語': 'ja', '🇷🇺 俄羅斯': 'ru'
}

def save_data():
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_data():
    global data
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            data = json.load(f)

def translate_text(text, target_lang):
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={text}"
    res = requests.get(url)
    return res.json()[0][0][0] if res.status_code == 200 else "翻譯失敗QQ"

def language_selection_message():
    buttons = [{
        "type": "button", "style": "primary", "color": "#0099FF",
        "action": {"type": "postback", "label": label, "data": f"lang:{code}"}
    } for label, code in LANGUAGE_MAP.items()]
    return {
        "type": "flex", "altText": "🌍 請選擇翻譯語言",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "🌍 翻譯語言選單", "weight": "bold", "size": "lg"}]
            },
            "body": {"type": "box", "layout": "vertical", "contents": buttons},
            "footer": {"type": "box", "layout": "vertical", "contents": []}
        }
    }

def reply(token, content):
    if isinstance(content, dict) and content.get("type") == "flex":
        msg = FlexSendMessage(alt_text=content["altText"], contents=content["contents"])
    else:
        msg = TextSendMessage(text=content if isinstance(content, str) else content.get("text"))
    line_bot_api.reply_message(token, msg)

@app.route("/webhook", methods=['POST'])
def webhook():
    body = request.get_json()
    for event in body.get("events", []):
        user_id = event["source"].get("userId")
        group_id = event["source"].get("groupId") or user_id
        if not user_id: continue

        if event["type"] == "join":
            reply(event["replyToken"], language_selection_message())
            continue

        if event["type"] == "postback":
            code = event["postback"]["data"].split(":")[1]
            data["user_prefs"].setdefault(group_id, []).append(code)
            save_data()
            reply(event["replyToken"], f"✅ 加入語言：{code}")
            continue

        if event["type"] == "message" and event["message"]["type"] == "text":
            if group_id not in data["user_prefs"]:
                reply(event["replyToken"], language_selection_message())
                data["user_prefs"][group_id] = []
                save_data()
                continue
            text = event["message"]["text"]
            langs = data["user_prefs"].get(group_id, ['en'])
            translated = [f"[{lang}] {translate_text(text, lang)}" for lang in langs]
            reply(event["replyToken"], "\n".join(translated))

    return 'OK'

@app.route("/")
def home():
    return "🎉 翻譯小精靈運行中！"

def keep_alive():
    while True:
        try:
            res = requests.get("http://0.0.0.0:5000/")
            print("🔄 Keep-Alive 成功" if res.status_code == 200 else "⚠️ Keep-Alive 失敗")
        except: print("❌ Keep-Alive 錯誤")
        time.sleep(900)  # 每15分鐘

if __name__ == '__main__':
    load_data()
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
