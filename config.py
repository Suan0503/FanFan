"""
FanFan LINE Bot - 環境變數與常數設定
"""
import os
from dotenv import load_dotenv

# 載入 .env 檔案
load_dotenv()

# === LINE Bot 設定 ===
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN', '')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET', '').encode('utf-8')

# === 資料庫設定 ===
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# === 翻譯 API 設定 ===
DEEPL_API_KEY = os.getenv('DEEPL_API_KEY', '')
DEEPL_API_BASE_URL = os.getenv('DEEPL_API_BASE_URL', 'https://api-free.deepl.com')

# === 系統設定 ===
MAX_CONCURRENT_TRANSLATIONS = 4  # 最多同時進行的翻譯數
INACTIVE_GROUP_DAYS = 20  # 多少天未使用自動退出群組
RESTART_INTERVAL = 10800  # 定時重啟間隔（秒）

# === 資料檔案 ===
DATA_FILE = "data.json"
MASTER_USER_FILE = "master_user_ids.json"

# === 預設主人 ID ===
DEFAULT_MASTER_USER_IDS = {
    'U5ce6c382d12eaea28d98f2d48673b4b8',
    'U2bcd63000805da076721eb62872bc39f',
    'Uea1646aa1a57861c85270d846aaee0eb',
    'U8f3cc921a9dd18d3e257008a34dd07c1'
}

# === 語言映射表 ===
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

# === 預設翻譯語言 ===
DEFAULT_TRANSLATE_LANGS = {'zh-TW'}

# === 日誌設定 ===
LOG_FORMAT = '[%(asctime)s] %(levelname)s: %(message)s'
