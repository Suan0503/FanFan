from flask import Flask, request
import os, json, time, requests
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage, FlexSendMessage

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))

MASTER_USER_FILE = "master_user_ids.json"
DEFAULT_MASTER_USER_IDS = {
    'U5ce6c382d12eaea28d98f2d48673b4b8',
    'U2bcd63000805da076721eb62872bc39f'
}

data = {"user_prefs": {}, "user_whitelist": []}
LANGUAGE_MAP = {
    '🇹🇼 中文': 'zh-TW', '🇺🇸 英文': 'en', '🇹🇭 泰文': 'th',
    '🇻🇳 越南文': 'vi', '🇲🇲 緬甸文': 'my', '🇰🇷 韓文': 'ko',
    '🇮🇩 印尼文': 'id', '🇯🇵 日語': 'ja', '🇷🇺 俄羅斯': 'ru'
}

def load_master_users():
    if os.path.exists(MASTER_USER_FILE):
        return set(json.load(open(MASTER_USER_FILE, encoding='utf-8')))
    json.dump(list(DEFAULT_MASTER_USER_IDS), open(MASTER_USER_FILE, 'w', encoding='utf-8'), indent=2)
    return DEFAULT_MASTER_USER_IDS.copy()
MASTER_USER_IDS = load_master_users()

def save_data():
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def language_selection_message():
    buttons = [{
        "type": "button", "style": "primary", "color": "#7BD3EA",
        "action": {"type": "postback", "label": label, "data": f"lang:{code}"}
    } for label, code in LANGUAGE_MAP.items()]
    buttons.append({
        "type": "button", "style": "secondary",
        "action": {"type": "postback", "label": "🔄 重設翻譯設定", "data": "reset"}
    })
    return {
        "type": "flex", "altText": "🌍 請選擇翻譯語言", "contents": {
            "type": "bubble", "header": {
                "type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": "🌍 翻譯選單", "weight": "bold", "size": "lg", "color": "#0099FF"},
                    {"type": "text", "text": "請選擇你要翻譯的語言 ✈️", "size": "sm", "color": "#555555"}
                ]
            },
            "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": buttons},
            "styles": {"body": {"backgroundColor": "#E0F7FF"}}
        }
    }

def translate_text(text, target_lang):
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={text}"
    res = requests.get(url)
    return res.json()[0][0][0] if res.status_code == 200 else "翻譯失敗QQ"

def reply(token, content):
    if isinstance(content, dict) and content.get("type") == "flex":
        msg = FlexSendMessage(alt_text=content["altText"], contents=content["contents"])
    else:
        msg = TextSendMessage(text=content if isinstance(content, str) else content.get("text", ""))
    line_bot_api.reply_message(token, msg)

@app.route("/webhook", methods=['POST'])
def webhook():
    body = request.get_json()
    for event in body.get("events", []):
        user_id = event.get("source", {}).get("userId")
        group_id = event.get("source", {}).get("groupId") or user_id
        event_type = event.get("type")

        if event_type == 'join':
            reply(event['replyToken'], language_selection_message())
            continue

        if event_type == 'postback':
            data_post = event['postback']['data']
            if user_id not in MASTER_USER_IDS and user_id not in data['user_whitelist']:
                reply(event['replyToken'], "❌ 無權限設定翻譯")
                continue
            if data_post == 'reset':
                data['user_prefs'].pop(group_id, None)
                save_data()
                reply(event['replyToken'], "✅ 已清除翻譯語言設定！")
            elif data_post.startswith('lang:'):
                code = data_post.split(':')[1]
                data['user_prefs'].setdefault(group_id, set()).symmetric_difference_update({code})
                save_data()
                reply(event['replyToken'], f"✅ 語言設定：{'、'.join(data['user_prefs'][group_id])}")

        elif event_type == 'message' and event['message']['type'] == 'text':
            text = event['message']['text'].strip()
            if group_id not in data['user_prefs']:
                reply(event['replyToken'], language_selection_message())
                continue
            results = [f"[{lang}] {translate_text(text, lang)}" for lang in data['user_prefs'][group_id]]
            reply(event['replyToken'], "\n".join(results))
    return 'OK'

@app.route("/")
def home():
    return "🎉 翻譯小精靈啟動成功 ✨"

def keep_alive():
    while True:
        try:
            time.sleep(1200)  # 每20分鐘
            print("🔄 KeepAlive 正常")
        except Exception as e:
            print("❌ KeepAlive 錯誤", e)

if __name__ == '__main__':
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
