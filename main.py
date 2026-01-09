from flask import Flask, request, send_from_directory
import os
import sys
import requests
import json
import time
import threading
from datetime import datetime, timedelta
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage
from dotenv import load_dotenv

# 先創建 app
app = Flask(__name__)

# 載入 .env 檔（若存在），讓本機開發也能讀到 DEEPL_API_KEY 等設定
load_dotenv()

# 資料庫設定（參考 web 專案的 DATABASE_URL）
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 設定資料庫 URI
if DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
else:
    # 本地開發使用 SQLite
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fanfan.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 引入資料庫模型
from models import db, Tenant, Group, UserPreference, GroupAdmin, Whitelist

# 初始化資料庫
db.init_app(app)

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
    "group_admin": {},  # 新增：儲存群組暫時管理員
    # 每個群組的翻譯引擎偏好："google" 或 "deepl"，預設為 google
    "translate_engine_pref": {},
    # 租戶管理系統 - 基於個人TOKEN的訂閱制
    "tenants": {}  # 格式: {"user_id": {"token": "xxxx", "expires_at": "2026-02-08", "groups": ["G1", "G2"], "stats": {"translate_count": 0, "char_count": 0}}}
}

start_time = time.time()
# 移除全域統計，改為 per-tenant

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
                    "group_admin": loaded_data.get("group_admin", {}),
                    "translate_engine_pref": loaded_data.get("translate_engine_pref", {}),
                    "tenants": loaded_data.get("tenants", {})  # 租戶系統
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
        "group_admin": data.get("group_admin", {}),
        "translate_engine_pref": data.get("translate_engine_pref", {}),
        "tenants": data.get("tenants", {})  # 租戶系統
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
        print("💾 資料已儲存！")

load_data()


# ===== 資料庫輔助函數 =====

def migrate_json_to_db():
    """將 data.json 的資料遷移到資料庫"""
    print("🔄 開始遷移 data.json 到資料庫...")
    
    with app.app_context():
        # 1. 遷移白名單
        for user_id in data.get('user_whitelist', []):
            if not Whitelist.query.filter_by(user_id=user_id).first():
                db.session.add(Whitelist(user_id=user_id))
        
        # 2. 遷移租戶
        tenants_data = data.get('tenants', {})
        for user_id, tenant_info in tenants_data.items():
            existing = Tenant.query.filter_by(user_id=user_id).first()
            if not existing:
                tenant = Tenant(
                    user_id=user_id,
                    token=tenant_info.get('token', ''),
                    expires_at=datetime.fromisoformat(tenant_info.get('expires_at', '2026-01-01')),
                    translate_count=tenant_info.get('stats', {}).get('translate_count', 0),
                    char_count=tenant_info.get('stats', {}).get('char_count', 0)
                )
                db.session.add(tenant)
                db.session.flush()  # 獲取 tenant.id
                
                # 3. 遷移該租戶的群組
                for group_id in tenant_info.get('groups', []):
                    if not Group.query.filter_by(group_id=group_id).first():
                        group = Group(
                            group_id=group_id,
                            tenant_id=tenant.id,
                            auto_translate=data.get('auto_translate', {}).get(group_id, True),
                            voice_translation=data.get('voice_translation', {}).get(group_id, True),
                            engine_pref=data.get('translate_engine_pref', {}).get(group_id, 'google')
                        )
                        db.session.add(group)
                        db.session.flush()
                        
                        # 4. 遷移用戶語言偏好
                        for uid, langs in data.get('user_prefs', {}).items():
                            if uid.startswith(group_id):  # user_prefs 格式: {group_id: [langs]}
                                if not UserPreference.query.filter_by(group_id=group.id, user_id=uid).first():
                                    lang_list = list(langs) if isinstance(langs, set) else langs
                                    db.session.add(UserPreference(
                                        group_id=group.id,
                                        user_id=uid,
                                        languages=lang_list
                                    ))
        
        # 5. 遷移群組管理員
        for group_id, admin_user_id in data.get('group_admin', {}).items():
            group = Group.query.filter_by(group_id=group_id).first()
            if group and admin_user_id:
                if not GroupAdmin.query.filter_by(group_id=group.id, user_id=admin_user_id).first():
                    db.session.add(GroupAdmin(group_id=group.id, user_id=admin_user_id))
        
        db.session.commit()
        print("✅ 資料遷移完成！")


def get_or_create_tenant(user_id, token=None, months=1):
    """取得或建立租戶"""
    tenant = Tenant.query.filter_by(user_id=user_id).first()
    if not tenant and token:
        expires_at = datetime.utcnow() + timedelta(days=30 * months)
        tenant = Tenant(user_id=user_id, token=token, expires_at=expires_at)
        db.session.add(tenant)
        db.session.commit()
    return tenant


def get_tenant_by_group(group_id):
    """透過群組ID查詢租戶"""
    group = Group.query.filter_by(group_id=group_id).first()
    if group:
        return group.tenant
    return None


def is_user_admin(user_id):
    """檢查是否為管理員（MASTER或白名單）"""
    return user_id in MASTER_USER_IDS or Whitelist.query.filter_by(user_id=user_id).first() is not None


def is_group_temp_admin(user_id, group_id):
    """檢查是否為群組臨時管理員"""
    group = Group.query.filter_by(group_id=group_id).first()
    if group:
        return GroupAdmin.query.filter_by(group_id=group.id, user_id=user_id).first() is not None
    return False


def check_expiration_and_remind():
    """檢查所有租戶到期狀態並發送提醒"""
    with app.app_context():
        tenants = Tenant.query.filter_by(is_active=True).all()
        
        for tenant in tenants:
            # 到期自動降級
            if tenant.is_expired() and tenant.plan != 'free':
                tenant.plan = 'free'
                db.session.commit()
                
                # 發送到期通知
                try:
                    line_bot_api.push_message(
                        tenant.user_id,
                        TextSendMessage(text=f"⚠️ 您的訂閱已到期，已自動降級為免費版。\n如需繼續使用付費功能，請聯繫管理員續費。")
                    )
                except Exception as e:
                    print(f"❌ 發送到期通知失敗: {e}")
            
            # 7天提醒
            elif tenant.should_remind_7days():
                tenant.reminded_7days = True
                db.session.commit()
                try:
                    line_bot_api.push_message(
                        tenant.user_id,
                        TextSendMessage(text=f"⏰ 提醒：您的訂閱將在 7 天後到期（{tenant.expires_at.strftime('%Y-%m-%d')}）\n請及時續費以繼續使用付費功能。")
                    )
                except Exception as e:
                    print(f"❌ 發送7天提醒失敗: {e}")
            
            # 1天提醒
            elif tenant.should_remind_1day():
                tenant.reminded_1day = True
                db.session.commit()
                try:
                    line_bot_api.push_message(
                        tenant.user_id,
                        TextSendMessage(text=f"🚨 緊急提醒：您的訂閱將在 1 天後到期（{tenant.expires_at.strftime('%Y-%m-%d')}）\n請盡快續費！")
                    )
                except Exception as e:
                    print(f"❌ 發送1天提醒失敗: {e}")


# 初始化資料庫並遷移資料
with app.app_context():
    db.create_all()
    print("✅ 資料表已建立")
    
    # 首次啟動時遷移資料
    if Tenant.query.count() == 0 and data.get('tenants'):
        migrate_json_to_db()


# 啟動定時檢查任務（每天檢查一次）
def schedule_expiration_check():
    """定時檢查到期並提醒"""
    while True:
        time.sleep(86400)  # 每24小時執行一次
        try:
            check_expiration_and_remind()
        except Exception as e:
            print(f"❌ 定時檢查失敗: {e}")

# 啟動背景執行緒
threading.Thread(target=schedule_expiration_check, daemon=True).start()
print("✅ 定時檢查任務已啟動")


# --- 保留舊的 GroupTranslateSetting等模型用於相容性 ---
class GroupTranslateSetting(db.Model):
    """群組翻譯設定：每個群組選擇的目標語言清單。"""
    __tablename__ = "group_translate_setting"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(db.String(255), unique=True, nullable=False)
    languages = db.Column(db.String(255), nullable=False, default="en")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class GroupActivity(db.Model):
    """紀錄群組最後活躍時間，用來判斷是否自動退出群組。"""
    __tablename__ = "group_activity"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(db.String(255), unique=True, nullable=False)
    last_active_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class GroupEnginePreference(db.Model):
    """每個群組的翻譯引擎偏好（google / deepl）。"""
    __tablename__ = "group_engine_preference"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(db.String(255), unique=True, nullable=False)
    engine = db.Column(db.String(20), nullable=False, default="google")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)



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


def touch_group_activity(group_id):
    """更新群組最後活躍時間（只在有資料庫時生效）。"""

    if not db or not group_id:
        return
    try:
        activity = GroupActivity.query.filter_by(group_id=group_id).first()
        now = datetime.utcnow()
        if not activity:
            activity = GroupActivity(group_id=group_id,
                                     last_active_at=now)
            db.session.add(activity)
        else:
            activity.last_active_at = now
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_engine_pref(group_id):
    """取得群組翻譯引擎偏好（google / deepl），優先使用資料庫。"""

    # 先看資料庫
    if db and group_id:
        try:
            pref = GroupEnginePreference.query.filter_by(
                group_id=group_id).first()
            if pref and pref.engine in ("google", "deepl"):
                return pref.engine
        except Exception:
            pass

    # 退回 data.json 記憶體
    engine = data.get("translate_engine_pref", {}).get(group_id)
    if engine in ("google", "deepl"):
        return engine
    return "google"


def set_engine_pref(group_id, engine):
    """設定群組翻譯引擎偏好，寫入 data.json 與資料庫。"""

    if engine not in ("google", "deepl"):
        engine = "google"

    data.setdefault("translate_engine_pref", {})
    data["translate_engine_pref"][group_id] = engine
    save_data()

    if not db or not group_id:
        return
    try:
        pref = GroupEnginePreference.query.filter_by(
            group_id=group_id).first()
        if not pref:
            pref = GroupEnginePreference(group_id=group_id,
                                         engine=engine)
            db.session.add(pref)
        else:
            pref.engine = engine
        db.session.commit()
    except Exception:
        db.session.rollback()


def check_inactive_groups():
    """檢查超過 20 天沒有任何活動的群組，自動退出群組。"""

    if not db:
        return

    try:
        threshold = datetime.utcnow() - timedelta(days=20)
        inactive = GroupActivity.query.filter(
            GroupActivity.last_active_at < threshold).all()
    except Exception:
        return

    if not inactive:
        return

    for activity in inactive:
        group_id = activity.group_id
        try:
            print(f"🚪 超過 20 天未使用，自動退出群組: {group_id}")
            line_bot_api.leave_group(group_id)
        except Exception as e:
            print(f"❌ 退出群組 {group_id} 失敗: {e}")

        # 清理記憶體中的資料
        try:
            if 'user_prefs' in data:
                data['user_prefs'].pop(group_id, None)
            if 'voice_translation' in data:
                data['voice_translation'].pop(group_id, None)
            if 'group_admin' in data:
                data['group_admin'].pop(group_id, None)
            if 'auto_translate' in data:
                data['auto_translate'].pop(group_id, None)
            save_data()
        except Exception:
            pass

        # 清理資料庫中的設定
        if not db:
            continue
        try:
            setting = GroupTranslateSetting.query.filter_by(
                group_id=group_id).first()
            if setting:
                db.session.delete(setting)
            db.session.delete(activity)
            db.session.commit()
        except Exception:
            db.session.rollback()


def start_inactive_checker():
    """啟動背景執行緒，每天檢查一次未使用群組。"""

    if not db:
        return

    def _loop():
        while True:
            try:
                with app.app_context():
                    check_inactive_groups()
            except Exception as e:
                print(f"❌ 檢查未使用群組時發生錯誤: {e}")
            time.sleep(86400)  # 每天檢查一次

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


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

# --- 租戶管理系統（使用資料庫）---
def generate_tenant_token():
    """生成唯一的租戶 TOKEN"""
    import secrets
    return secrets.token_urlsafe(16)

def create_tenant_db(user_id, months=1, name=None):
    """創建租戶訂閱（資料庫版本）"""
    with app.app_context():
        token = generate_tenant_token()
        expires_at = datetime.utcnow() + timedelta(days=30 * months)
        
        tenant = Tenant.query.filter_by(user_id=user_id).first()
        tenant_count = Tenant.query.count()
        
        if tenant:
            # 更新現有租戶
            tenant.token = token
            tenant.expires_at = expires_at
            tenant.is_active = True
            tenant.plan = 'premium'
            tenant.reminded_7days = False
            tenant.reminded_1day = False
            if name:
                tenant.name = name
        else:
            # 創建新租戶，自動命名
            if not name:
                name = f"翻翻君{tenant_count + 1}"
            
            tenant = Tenant(
                user_id=user_id,
                name=name,
                token=token,
                expires_at=expires_at,
                plan='premium'
            )
            db.session.add(tenant)
        
        db.session.commit()
        return token, expires_at.isoformat()

def get_tenant_by_group_db(group_id):
    """根據群組ID取得租戶（資料庫版本）"""
    with app.app_context():
        group = Group.query.filter_by(group_id=group_id).first()
        if group:
            return group.tenant
        return None

def is_tenant_valid_db(user_id):
    """檢查租戶是否有效（資料庫版本）"""
    with app.app_context():
        tenant = Tenant.query.filter_by(user_id=user_id).first()
        if not tenant:
            return False
        return not tenant.is_expired() and tenant.is_active

def add_group_to_tenant_db(user_id, group_id):
    """將群組加入租戶管理（資料庫版本）"""
    with app.app_context():
        tenant = Tenant.query.filter_by(user_id=user_id).first()
        if not tenant:
            return False
        
        # 檢查群組是否已存在
        existing_group = Group.query.filter_by(group_id=group_id).first()
        if existing_group:
            # 更新為新租戶
            existing_group.tenant_id = tenant.id
        else:
            # 創建新群組
            group = Group(group_id=group_id, tenant_id=tenant.id)
            db.session.add(group)
        
        db.session.commit()
        return True

def _update_stats_async(group_id, char_count, engine):
    """非阻塞方式更新統計"""
    def _do_update():
        try:
            with app.app_context():
                tenant = get_tenant_by_group_db(group_id)
                if tenant:
                    update_tenant_stats_db(tenant.user_id, translate_count=1, char_count=char_count, engine=engine)
        except Exception as e:
            print(f"⚠️ 背景更新統計失敗: {e}")
    
    # 在背景執行緒中更新，不阻塞翻譯
    threading.Thread(target=_do_update, daemon=True).start()


def update_tenant_stats_db(user_id, translate_count=0, char_count=0, engine='google'):
    """更新租戶統計資料（資料庫版本）- 必須在 app_context 中調用"""
    try:
        tenant = Tenant.query.filter_by(user_id=user_id).first()
        if tenant:
            # 重置每日統計（如果需要）
            tenant.reset_daily_stats()
            
            # 更新統計
            tenant.translate_count += translate_count
            tenant.char_count += char_count
            tenant.today_char_count += char_count
            
            # 更新引擎統計
            if engine == 'deepl':
                tenant.deepl_count += translate_count
            else:
                tenant.google_count += translate_count
            
            db.session.commit()
            print(f"✅ 統計已更新: user={user_id[-8:]}, chars={char_count}, engine={engine}")
    except Exception as e:
        print(f"❌ 更新統計錯誤: {e}")
        db.session.rollback()

def check_group_access_db(group_id):
    """檢查群組是否有有效的租戶訂閱（資料庫版本）"""
    with app.app_context():
        tenant = get_tenant_by_group_db(group_id)
        if tenant:
            return not tenant.is_expired() and tenant.is_active
        # 預設：未設定租戶的群組全功能開放
        return True

def create_command_menu():
    """創建新年風格指令選單"""
    return {
        "type": "flex",
        "altText": "🎊 新春管理選單",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": "🎊 新春管理面板",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#FF0000"
                }, {
                    "type": "text",
                    "text": "🧧 恭喜發財 萬事如意 🧧",
                    "size": "sm",
                    "color": "#FFD700",
                    "weight": "bold",
                    "align": "center"
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
                    },
                    "height": "sm"
                }, {
                    "type": "button",
                    "style": "primary",
                    "color": "#FF6347",
                    "action": {
                        "type": "message",
                        "label": "💾 記憶體使用",
                        "text": "/記憶體"
                    },
                    "height": "sm"
                }, {
                    "type": "button",
                    "style": "primary",
                    "color": "#FF4500",
                    "action": {
                        "type": "message",
                        "label": "🔄 重啟系統",
                        "text": "/重啟"
                    },
                    "height": "sm"
                }, {
                    "type": "button",
                    "style": "primary",
                    "color": "#FFD700",
                    "action": {
                        "type": "message",
                        "label": "📝 今日流量",
                        "text": "/流量"
                    },
                    "height": "sm"
                }, {
                    "type": "button",
                    "style": "primary",
                    "color": "#FF8C00",
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
                    "text": "🏮 祝您新年快樂 龍年大吉 🏮",
                    "size": "sm",
                    "color": "#DC143C",
                    "align": "center",
                    "weight": "bold"
                }]
            },
            "styles": {
                "header": {
                    "backgroundColor": "#FFF5F5"
                },
                "body": {
                    "backgroundColor": "#FFFAF0"
                },
                "footer": {
                    "separator": True,
                    "backgroundColor": "#FFF5F5"
                }
            }
        }
    }

def language_selection_message(group_id):
    """新年風格群組翻譯語言選單，會依目前設定在按鈕前顯示 ✅。"""

    current_langs = get_group_langs(group_id)

    contents = []
    for label, code in LANGUAGE_MAP.items():
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
                }, {
                    "type": "text",
                    "text": "🧧 新年快樂 🧧",
                    "size": "xs",
                    "color": "#FFD700",
                    "weight": "bold",
                    "align": "center",
                    "margin": "md"
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
                "header": {
                    "backgroundColor": "#FFF5F5"
                },
                "body": {
                    "backgroundColor": "#FFFAF0"
                },
                "footer": {
                    "separator": True
                }
            }
        }
    }

DEEPL_API_KEY = os.getenv('DEEPL_API_KEY', '')
DEEPL_API_BASE_URL = os.getenv('DEEPL_API_BASE_URL', 'https://api-free.deepl.com')

if DEEPL_API_KEY:
    # 只顯示前幾碼避免外洩完整金鑰
    print(f"✅ DEEPL_API_KEY 已載入（開頭: {DEEPL_API_KEY[:6]}...）")
else:
    print("⚠️ 未設定 DEEPL_API_KEY，將只使用 Google 翻譯作為後備。")


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
    
    # 增加 timeout 至 5 秒，並加上重試機制與 exponential backoff
    max_retries = 3
    for attempt in range(1, max_retries + 1):
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
        except requests.RequestException as e:
            print(f"❌ DeepL 請求錯誤 (第 {attempt} 次): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None
            time.sleep(0.5 * attempt)  # exponential backoff: 0.5s, 1s, 1.5s
            continue

        if resp.status_code != 200:
            preview = resp.text[:200] if hasattr(resp, 'text') else ''
            print(f"❌ DeepL 狀態碼 {resp.status_code} (第 {attempt} 次)，回應：{preview}")
            if attempt == max_retries:
                return None
            time.sleep(0.5 * attempt)
            continue

        try:
            data_json = resp.json()
            translations = data_json.get('translations') or []
            if not translations:
                print(f"❌ DeepL 回傳內容沒有 translations 欄位 (第 {attempt} 次)")
                if attempt == max_retries:
                    return None
                time.sleep(0.5 * attempt)
                continue
            return translations[0].get('text')
        except Exception as e:
            print(f"❌ 解析 DeepL 回應失敗 (第 {attempt} 次): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None
            time.sleep(0.5 * attempt)
            continue
    
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
    # 增加 timeout 至 5 秒，加上重試機制與 exponential backoff
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.get(url, params=params, timeout=5)
        except requests.RequestException as e:
            print(f"❌ Google 翻譯請求錯誤 (第 {attempt} 次): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None
            time.sleep(0.5 * attempt)  # exponential backoff: 0.5s, 1s, 1.5s
            continue

        if res.status_code != 200:
            preview = res.text[:200] if hasattr(res, 'text') else ''
            print(f"❌ Google 翻譯狀態碼 {res.status_code} (第 {attempt} 次)，回應：{preview}")
            if attempt == max_retries:
                return None
            time.sleep(0.5 * attempt)
            continue

        try:
            return res.json()[0][0][0]
        except Exception as e:
            print(f"❌ 解析 Google 翻譯回應失敗 (第 {attempt} 次): {type(e).__name__}: {e}")
            if attempt == max_retries:
                return None
            time.sleep(0.5 * attempt)
            continue

    return None


def translate_text(text, target_lang, prefer_deepl_first=False, group_id=None):
    """統一翻譯入口：只使用一種引擎，不備援"""

    try:
        # 根據偏好選擇引擎
        engine = 'deepl' if prefer_deepl_first else 'google'
        if prefer_deepl_first:
            translated = _translate_with_deepl(text, target_lang)
        else:
            translated = _translate_with_google(text, target_lang)

        if translated is None:
            print(f"⚠️ 翻譯返回 None: target={target_lang}, engine={engine}")
            return "翻譯失敗QQ"

        # 更新 per-tenant 統計（非阻塞）
        if group_id:
            try:
                _update_stats_async(group_id, len(text), engine)
            except Exception as stats_err:
                print(f"⚠️ 更新統計失敗（不影響翻譯）: {stats_err}")
        
        return translated
    except Exception as e:
        print(f"❌ 翻譯錯誤: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return "翻譯失敗QQ"


def _format_translation_results(text, langs, prefer_deepl_first=False, group_id=None):
    """將多語言翻譯結果組成一段文字。"""

    results = []
    for lang in langs:
        translated = translate_text(text, lang, prefer_deepl_first=prefer_deepl_first, group_id=group_id)
        results.append(f"[{lang}] {translated}")
    return '\n'.join(results)


def _async_translate_and_reply(reply_token, text, langs, prefer_deepl_first=False, group_id=None):
    """在背景執行緒中翻譯並用 reply_message 回覆，避免阻塞 webhook。"""

    try:
        print(f"🔄 開始翻譯: text_len={len(text)}, langs={langs}, group={group_id[-8:] if group_id else 'N/A'}")
        
        # 為了避免 set 在其他地方被修改，先轉成 list
        lang_list = list(langs)
        result_text = _format_translation_results(text, lang_list, prefer_deepl_first=prefer_deepl_first, group_id=group_id)
        
        print(f"✅ 翻譯完成，準備回覆")
        line_bot_api.reply_message(reply_token,
                                   TextSendMessage(text=result_text))
        print(f"✅ 回覆已發送")
    except Exception as e:
        print(f"❌ 非同步翻譯回覆失敗: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        try:
            line_bot_api.reply_message(reply_token,
                                     TextSendMessage(text="翻譯失敗，請稍後再試"))
        except:
            pass

def reply(token, message_content):
    from linebot.models import FlexSendMessage

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
                # 其他型別（理論上不會用到），保留原樣以避免中斷
                converted.append(m)

        message = converted
    else:
        # fallback：當成純文字
        message = TextSendMessage(text=str(message_content))

    line_bot_api.reply_message(token, message)

def is_group_admin(user_id, group_id):
    return data.get('group_admin', {}).get(group_id) == user_id

@app.route("/webhook", methods=['POST'])
def webhook():
    print(f"📥 收到 webhook 請求")
    
    # 簽名驗證
    signature = request.headers.get('X-Line-Signature')
    body_text = request.get_data(as_text=True)
    
    try:
        handler.handle(body_text, signature)
    except Exception as e:
        print(f"❌ Webhook 簽名驗證失敗: {e}")
        return 'Invalid signature', 400
    
    try:
        body = request.get_json()
        events = body.get("events", [])
        print(f"📊 處理 {len(events)} 個事件")
        
        for event in events:
            try:
                source = event.get("source", {})
                group_id = source.get("groupId") or source.get("userId")
                user_id = source.get("userId")
                if not group_id or not user_id:
                    continue
                event_type = event.get("type")
                print(f"🔄 處理事件: type={event_type}, group={group_id[-8:] if group_id else 'N/A'}, user={user_id[-8:] if user_id else 'N/A'}")

                # 若是群組事件，更新最後活躍時間
                raw_group_id = source.get("groupId")
                if raw_group_id:
                    touch_group_activity(raw_group_id)

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

        # --- 處理成員離開群組事件 ---
        if event_type == 'memberLeft':
            left_members = event.get('left', {}).get('members', [])
            for member in left_members:
                left_user_id = member.get('userId')
                
                # 檢查離開的是否為租戶管理員
                with app.app_context():
                    group = Group.query.filter_by(group_id=group_id).first()
                    if group and group.tenant:
                        # 如果租戶本人或綁定人離開，機器人也離開
                        if left_user_id == group.tenant.user_id or left_user_id == group.bound_by_user_id:
                            try:
                                # 先發送離開通知
                                line_bot_api.push_message(
                                    group_id,
                                    TextSendMessage(text=f"👋 管理員已離開群組，翻譯機器人也將退出。\n如需繼續使用，請重新綁定。")
                                )
                                # 讓機器人離開群組
                                line_bot_api.leave_group(group_id)
                                
                                # 更新資料庫狀態
                                group.is_active = False
                                db.session.commit()
                                print(f"✅ 管理員 {left_user_id[-8:]} 離開，機器人已退出群組 {group_id[-8:]}")
                            except Exception as e:
                                print(f"❌ 機器人離開群組失敗: {e}")
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

            # --- 切換本群預設翻譯引擎為 DeepL 優先 ---
            # 預設為 Google -> DeepL，若輸入 "DEEPL" 則改為 DeepL -> Google
            if lower == 'deepl':
                set_engine_pref(group_id, 'deepl')
                reply(event['replyToken'], {
                    "type": "text",
                    "text": "✅ 本群預設翻譯引擎已改為：先 DeepL，再 Google（若 DeepL 失敗會自動改用 Google）。"
                })
                continue

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

            # --- 主人設定租戶管理員（使用資料庫）---
            if (lower.startswith('/設定管理員') or lower.startswith('設定管理員')) and user_id in MASTER_USER_IDS:
                parts = text.replace('　', ' ').split()
                # 格式: /設定管理員 @某人 [1-12]
                if len(parts) >= 3:
                    # 提取 user_id 和月份
                    mentioned_users = []
                    # 從 event 中取得 mention 資訊
                    message = event.get('message', {})
                    if 'mention' in message:
                        mentions = message['mention'].get('mentionees', [])
                        for mention in mentions:
                            if mention.get('type') == 'user':
                                mentioned_users.append(mention.get('userId'))
                    
                    if not mentioned_users:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 請使用 @ 標記要設為管理員的人"
                        })
                        continue
                    
                    try:
                        months = int(parts[-1])
                        if months < 1 or months > 12:
                            raise ValueError
                    except:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 月份必須是 1-12 之間的數字"
                        })
                        continue
                    
                    tenant_user_id = mentioned_users[0]
                    
                    # 使用資料庫創建租戶
                    with app.app_context():
                        token, expires_at = create_tenant_db(tenant_user_id, months)
                        add_group_to_tenant_db(tenant_user_id, group_id)
                        
                        # 同時設為群組管理員
                        group = Group.query.filter_by(group_id=group_id).first()
                        if group:
                            existing_admin = GroupAdmin.query.filter_by(
                                group_id=group.id, user_id=tenant_user_id
                            ).first()
                            if not existing_admin:
                                db.session.add(GroupAdmin(
                                    group_id=group.id,
                                    user_id=tenant_user_id
                                ))
                                db.session.commit()
                    
                    expire_date = expires_at.split('T')[0]
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": f"✅ 已設定租戶管理員！\n\n👤 管理員：{tenant_user_id[-8:]}\n📅 有效期：{months} 個月\n⏰ 到期日：{expire_date}\n🔑 TOKEN: {token[:8]}...\n\n💡 提示：管理員可使用 /付費選單 查看詳情"
                    })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 格式錯誤，請使用：`/設定管理員 @某人 [1-12]`"
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

            # --- 管理員選單（MASTER/白名單可用） ---
            if lower in ['/管理員選單', '/admin_menu']:
                if user_id not in MASTER_USER_IDS:
                    if not Whitelist.query.filter_by(user_id=user_id).first():
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 只有管理員可以使用此功能喲～"
                        })
                        continue
                
                # 如果在群組中，顯示該群組的租戶詳細資訊
                with app.app_context():
                    tenant = get_tenant_by_group_db(group_id) if group_id else None
                    
                    if tenant:
                        # ① 租戶基本資訊
                        status = tenant.get_status()
                        expires_str = tenant.expires_at.strftime('%Y-%m-%d')
                        days_left = tenant.days_remaining()
                        
                        # ② 綁定的群組列表
                        groups_info = []
                        for g in tenant.groups:
                            auto_status = "✅" if g.auto_translate else "❌"
                            group_short_id = g.group_id[-8:] if len(g.group_id) > 8 else g.group_id
                            bound_time = g.bound_at.strftime('%m/%d') if g.bound_at else '未知'
                            groups_info.append(
                                f"  • {g.group_name} (...{group_short_id})\n"
                                f"    自動翻譯: {auto_status} | 綁定: {bound_time}"
                            )
                        groups_text = "\n".join(groups_info) if groups_info else "  無綁定群組"
                        
                        # ③ 用量摘要
                        total_engine = tenant.google_count + tenant.deepl_count
                        if total_engine > 0:
                            google_pct = (tenant.google_count / total_engine) * 100
                            deepl_pct = (tenant.deepl_count / total_engine) * 100
                            engine_ratio = f"Google {google_pct:.1f}% / DeepL {deepl_pct:.1f}%"
                        else:
                            engine_ratio = "尚無使用記錄"
                        
                        menu_text = f"""🎛️ 租戶管理面板

【租戶基本資訊】
👤 名稱: {tenant.name}
📊 狀態: {status}
📅 到期日: {expires_str}
⏰ 剩餘: {days_left} 天
🏢 群組額度: {len(tenant.groups)}/{tenant.max_groups}

【綁定的群組列表】
{groups_text}

【用量摘要（本期）】
📝 本期已翻譯: {tenant.char_count:,} 字元
📅 今日已翻譯: {tenant.today_char_count:,} 字元
🔧 引擎比例: {engine_ratio}
💬 翻譯次數: {tenant.translate_count:,} 次

💡 管理指令
/設定群組上限 @用戶 [數量] - 設定群組上限
/租戶資訊 - 查看詳細資訊
/統計 - 查看系統統計"""
                        
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": menu_text
                        })
                    else:
                        # 顯示所有租戶列表
                        all_tenants = Tenant.query.all()
                        active_count = sum(1 for t in all_tenants if not t.is_expired())
                        total_groups = Group.query.count()
                        
                        tenant_list = []
                        for tenant in all_tenants[:10]:  # 顯示前10個
                            status = tenant.get_status()
                            groups_count = len(tenant.groups)
                            tenant_list.append(
                                f"{status} {tenant.name} | "
                                f"到期:{tenant.expires_at.strftime('%Y-%m-%d')} | "
                                f"群組:{groups_count}/{tenant.max_groups}"
                            )
                        
                        tenant_text = "\n".join(tenant_list) if tenant_list else "無租戶資料"
                        
                        menu_text = f"""🎛️ 管理員控制面板

📊 系統統計
👥 總租戶數: {len(all_tenants)}
✅ 活躍租戶: {active_count}
🏢 總群組數: {total_groups}

📋 租戶列表（最近10筆）
{tenant_text}

💡 管理指令
/設定管理員 @用戶 [月數] - 新增租戶
/設定群組上限 @用戶 [數量] - 設定上限
/租戶資訊 - 查看當前群組租戶
/統計 - 查看系統統計"""
                        
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": menu_text
                        })
                continue

            # --- 付費選單（付費用戶專用） ---
            if lower in ['/付費選單', '/premium_menu', '/我的選單']:
                with app.app_context():
                    tenant = Tenant.query.filter_by(user_id=user_id).first()
                    
                    if not tenant or tenant.is_expired():
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 此功能僅限付費用戶使用\n\n您的訂閱已到期或尚未訂閱\n請聯繫管理員續費或開通服務"
                        })
                        continue
                    
                    # 計算剩餘天數
                    days_left = tenant.days_remaining()
                    
                    # 獲取管理的群組
                    groups_count = len(tenant.groups)
                    
                    menu_text = f"""💎 付費用戶選單

👤 訂閱資訊
📅 到期日: {tenant.expires_at.strftime('%Y-%m-%d')}
⏰ 剩餘天數: {days_left} 天
📦 方案: {tenant.plan.upper()}
🏢 管理群組數: {groups_count}

📊 使用統計
💬 翻譯次數: {tenant.translate_count:,}
📝 翻譯字元: {tenant.char_count:,}

🎯 可用功能
✅ 多語言翻譯（無限制）
✅ 語音訊息翻譯
✅ 自動翻譯
✅ 群組管理（最多20個）
✅ 翻譯引擎切換（Google/DeepL）
✅ 即時統計

💡 管理指令
/選單 - 設定翻譯語言
/語音翻譯 - 切換語音翻譯
/引擎 - 切換翻譯引擎
/自動翻譯 - 切換自動翻譯

⚠️ 到期後將自動降級為免費版
免費版功能受限，請及時續費"""
                    
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": menu_text
                    })
                continue

            # --- 租戶資訊查詢（主人可用） ---
            if lower in ['/租戶資訊', '/tenant_info']:
                if user_id not in MASTER_USER_IDS:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 只有主人可以查看租戶資訊喲～"
                    })
                    continue
                
                with app.app_context():
                    tenant = get_tenant_by_group_db(group_id)
                    if not tenant:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 本群組尚未設定租戶管理員"
                        })
                        continue
                    
                    is_valid = not tenant.is_expired()
                    status = "✅ 有效" if is_valid else "❌ 已過期"
                    groups_count = len(tenant.groups)
                    
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": f"📋 租戶資訊\n\n👤 User ID: {tenant.user_id[-8:]}\n🔑 TOKEN: {tenant.token[:12]}...\n📅 到期日: {tenant.expires_at.strftime('%Y-%m-%d')}\n⏰ 剩餘: {tenant.days_remaining()}天\n📊 狀態: {status}\n📦 方案: {tenant.plan.upper()}\n💬 翻譯次數: {tenant.translate_count}\n📝 字元數: {tenant.char_count}\n👥 管理群組數: {groups_count}"
                    })
                continue

            # --- 設定群組上限（僅限主人）---
            if lower.startswith('/設定群組上限') and user_id in MASTER_USER_IDS:
                parts = text.replace('　', ' ').split()
                if len(parts) >= 3:
                    # 提取被 @ 的用戶和數量
                    mentioned_users = []
                    message = event.get('message', {})
                    if 'mention' in message:
                        mentions = message['mention'].get('mentionees', [])
                        for mention in mentions:
                            if mention.get('type') == 'user':
                                mentioned_users.append(mention.get('userId'))
                    
                    if not mentioned_users:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 請使用 @ 標記要設定的用戶"
                        })
                        continue
                    
                    try:
                        max_groups = int(parts[-1])
                        if max_groups < 1 or max_groups > 999:
                            raise ValueError
                    except:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 群組數量必須是 1-999 之間的數字"
                        })
                        continue
                    
                    target_user_id = mentioned_users[0]
                    with app.app_context():
                        tenant = Tenant.query.filter_by(user_id=target_user_id).first()
                        if tenant:
                            tenant.max_groups = max_groups
                            db.session.commit()
                            reply(event['replyToken'], {
                                "type": "text",
                                "text": f"✅ 已設定群組上限！\n\n👤 用戶：{target_user_id[-8:]}\n🏢 群組上限：{max_groups} 個"
                            })
                        else:
                            reply(event['replyToken'], {
                                "type": "text",
                                "text": "❌ 該用戶不是租戶，請先使用 /設定管理員 創建租戶"
                            })
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 格式錯誤，請使用：`/設定群組上限 @用戶 [1-999]`"
                    })
                continue

            # --- 移轉權限（付費用戶/主人可用）---
            if lower.startswith('/移轉權限'):
                # 檢查權限
                with app.app_context():
                    is_master = user_id in MASTER_USER_IDS
                    tenant = Tenant.query.filter_by(user_id=user_id).first()
                    
                    if not is_master and (not tenant or tenant.is_expired()):
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 只有付費用戶或主人可以使用此功能"
                        })
                        continue
                    
                    parts = text.replace('　', ' ').split()
                    if len(parts) < 2:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 格式錯誤，請使用：`/移轉權限 @用戶`"
                        })
                        continue
                    
                    # 提取被 @ 的用戶
                    mentioned_users = []
                    message = event.get('message', {})
                    if 'mention' in message:
                        mentions = message['mention'].get('mentionees', [])
                        for mention in mentions:
                            if mention.get('type') == 'user':
                                mentioned_users.append(mention.get('userId'))
                    
                    if not mentioned_users:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 請使用 @ 標記要移轉給的用戶"
                        })
                        continue
                    
                    target_user_id = mentioned_users[0]
                    
                    # 儲存待確認的移轉資訊（簡單實作：使用 data 暫存）
                    data.setdefault('pending_transfer', {})
                    data['pending_transfer'][user_id] = {
                        'target': target_user_id,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    save_data()
                    
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": f"⚠️ 確認移轉權限\n\n移轉給：{target_user_id[-8:]}\n\n移轉後您將無法使用付費功能，訂閱期限和群組都會轉移給對方。\n\n請輸入「是」確認移轉，或「否」取消"
                    })
                continue

            # --- 處理移轉確認 ---
            if text.strip() in ['是', '確認']:
                pending = data.get('pending_transfer', {}).get(user_id)
                if pending:
                    with app.app_context():
                        tenant = Tenant.query.filter_by(user_id=user_id).first()
                        if tenant:
                            target_user_id = pending['target']
                            
                            # 檢查目標用戶是否已是租戶
                            target_tenant = Tenant.query.filter_by(user_id=target_user_id).first()
                            if target_tenant:
                                reply(event['replyToken'], {
                                    "type": "text",
                                    "text": "❌ 目標用戶已經是租戶，無法接收移轉"
                                })
                                del data['pending_transfer'][user_id]
                                save_data()
                                continue
                            
                            # 執行移轉：更改 user_id
                            old_user_id = tenant.user_id
                            tenant.user_id = target_user_id
                            tenant.reminded_7days = False
                            tenant.reminded_1day = False
                            db.session.commit()
                            
                            # 清除待確認
                            del data['pending_transfer'][user_id]
                            save_data()
                            
                            reply(event['replyToken'], {
                                "type": "text",
                                "text": f"✅ 權限移轉成功！\n\n所有訂閱和群組已轉移給：{target_user_id[-8:]}\n您的付費功能已失效。"
                            })
                            
                            # 通知新租戶（如果可以）
                            try:
                                line_bot_api.push_message(
                                    target_user_id,
                                    TextSendMessage(text=f"🎉 您已接收權限移轉！\n\n來自：{old_user_id[-8:]}\n訂閱到期日：{tenant.expires_at.strftime('%Y-%m-%d')}\n管理群組數：{len(tenant.groups)}\n\n請使用 /付費選單 查看詳情")
                                )
                            except:
                                pass
                        else:
                            reply(event['replyToken'], {
                                "type": "text",
                                "text": "❌ 您不是租戶，無法移轉"
                            })
                            del data['pending_transfer'][user_id]
                            save_data()
                    continue

            if text.strip() in ['否', '取消']:
                if user_id in data.get('pending_transfer', {}):
                    del data['pending_transfer'][user_id]
                    save_data()
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "✅ 已取消移轉"
                    })
                    continue

            # --- 綁定群組（付費用戶專用）---
            if lower in ['/綁定群組', '/bind']:
                if not group_id:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 此指令只能在群組中使用"
                    })
                    continue
                
                with app.app_context():
                    tenant = Tenant.query.filter_by(user_id=user_id).first()
                    
                    # 檢查是否為付費用戶
                    if not tenant or tenant.is_expired() or tenant.is_suspended:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 只有有效的付費用戶可以綁定群組\n\n請聯繫管理員開通或續費服務"
                        })
                        continue
                    
                    # 檢查是否超過上限
                    if not tenant.can_add_group():
                        current_groups = len(tenant.groups)
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": f"❌ 已超過綁定上限\n\n當前: {current_groups}/{tenant.max_groups}\n\n請退出舊群組或聯繫管理員擴充上限"
                        })
                        continue
                    
                    # 檢查群組是否已被其他租戶綁定
                    existing_group = Group.query.filter_by(group_id=group_id).first()
                    if existing_group and existing_group.tenant_id != tenant.id:
                        reply(event['replyToken'], {
                            "type": "text",
                            "text": "❌ 此群組已被其他租戶綁定"
                        })
                        continue
                    
                    # 獲取群組資訊
                    try:
                        group_summary = line_bot_api.get_group_summary(group_id)
                        group_name = group_summary.group_name
                    except:
                        group_name = "未知群組"
                    
                    # 創建或更新群組綁定
                    if existing_group:
                        existing_group.is_active = True
                        existing_group.bound_by_user_id = user_id
                        existing_group.bound_at = datetime.utcnow()
                        existing_group.group_name = group_name
                    else:
                        new_group = Group(
                            group_id=group_id,
                            group_name=group_name,
                            tenant_id=tenant.id,
                            bound_by_user_id=user_id,
                            auto_translate=True,
                            voice_translation=True,
                            engine_pref='google'
                        )
                        db.session.add(new_group)
                    
                    db.session.commit()
                    
                    # 顯示綁定成功訊息
                    bind_msg = f"""✅ 綁定成功！

📋 群組資訊
名稱：{group_name}
ID：...{group_id[-8:]}

✓ 功能狀態（預設全開）
✅ 自動翻譯
✅ 語音翻譯
✅ 多語言支援
✅ 翻譯引擎切換

📊 當前狀態：有效
👤 綁定人：{user_id[-8:]}
🏢 群組額度：{len(tenant.groups)}/{tenant.max_groups}

💡 使用 /選單 設定翻譯語言"""
                    
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": bind_msg
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
                # 判斷是否已有暫時管理員
                has_admin = data.get('group_admin', {}).get(group_id) is not None
                is_privileged = user_id in MASTER_USER_IDS or user_id in data.get(
                    'user_whitelist', []) or is_group_admin(user_id, group_id)

                auto_set_admin_message = None

                # 若尚未設定暫時管理員，第一個呼叫選單的人自動成為管理員
                if not has_admin and not is_privileged:
                    data.setdefault('group_admin', {})
                    data['group_admin'][group_id] = user_id
                    save_data()
                    is_privileged = True
                    auto_set_admin_message = "✅ 已自動將你設為本群的暫時管理員，可以設定翻譯語言！"

                if is_privileged:
                    if auto_set_admin_message:
                        reply(event['replyToken'], [
                            {"type": "text", "text": auto_set_admin_message},
                            language_selection_message(group_id)
                        ])
                    else:
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
                
                # 取得租戶統計
                tenant_user_id, tenant = get_tenant_by_group(group_id)
                if tenant_user_id:
                    stats = tenant.get('stats', {})
                    tenant_stats = f"\n\n📋 本群組統計：\n📊 翻譯次數: {stats.get('translate_count', 0)}\n📝 字元數: {stats.get('char_count', 0)}"
                else:
                    tenant_stats = ""
                
                reply(
                    event['replyToken'], {
                        "type":
                        "text",
                        "text":
                        f"⏰ 運行時間：{uptime_str}\n👥 群組/用戶數量：{group_count}{tenant_stats}"
                    })
                continue
            if lower in ['/統計', '翻譯統計']:
                if user_id in MASTER_USER_IDS or Whitelist.query.filter_by(user_id=user_id).first():
                    # 計算所有租戶的統計（從資料庫）
                    with app.app_context():
                        all_tenants = Tenant.query.all()
                        total_translate_count = sum(t.translate_count for t in all_tenants)
                        total_char_count = sum(t.char_count for t in all_tenants)
                        active_tenants = sum(1 for t in all_tenants if not t.is_expired())
                        total_groups = Group.query.count()
                    
                    lang_sets = get_group_stats_for_status()
                    group_count = len(lang_sets)
                    total_langs = sum(len(langs) for langs in lang_sets)
                    avg_langs = total_langs / group_count if group_count > 0 else 0
                    all_langs = set(lang for langs in lang_sets for lang in langs)
                    most_used = max(
                        all_langs,
                        key=lambda x: sum(1 for langs in lang_sets if x in langs),
                        default="無")
                    stats = f"📊 系統統計\n\n👥 總群組數：{total_groups}\n🌐 平均語言數：{avg_langs:.1f}\n⭐️ 最常用語言：{most_used}\n\n🎫 租戶統計\n👤 活躍租戶：{active_tenants}\n💬 總翻譯次數：{total_translate_count:,}\n📝 總字元數：{total_char_count:,}"
                    reply(event['replyToken'], {"type": "text", "text": stats})
                else:
                    reply(event['replyToken'], {
                        "type": "text",
                        "text": "❌ 你沒有權限查看統計資料喲～"
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

                # 依群組設定決定翻譯引擎先後順序（預設 Google 優先）
                engine_pref = get_engine_pref(group_id)
                prefer_deepl_first = (engine_pref == 'deepl')

                # 使用背景 thread + reply_message，避免阻塞 LINE callback（避免 499），
                # 同時不消耗 LINE 的 push 每月額度。
                threading.Thread(
                    target=_async_translate_and_reply,
                    args=(event['replyToken'], text, list(langs),
                          prefer_deepl_first, group_id),
                    daemon=True).start()
                continue
            elif text.startswith('!翻譯'):  # 手動翻譯指令
                text_to_translate = text[3:].strip()
                if text_to_translate:
                    langs = get_group_langs(group_id)

                    engine_pref = get_engine_pref(group_id)
                    prefer_deepl_first = (engine_pref == 'deepl')

                    threading.Thread(
                        target=_async_translate_and_reply,
                        args=(event['replyToken'], text_to_translate,
                              list(langs), prefer_deepl_first, group_id),
                        daemon=True).start()
                    continue
                    
            except Exception as event_err:
                print(f"❌ 處理事件時發生錯誤: {type(event_err).__name__}: {event_err}")
                import traceback
                traceback.print_exc()
                # 繼續處理下一個事件
                continue
        
        print(f"✅ 所有事件處理完成")
        return 'OK'
        
    except Exception as e:
        print(f"❌ Webhook 處理錯誤: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 'Error', 500

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
            # 啟動自動檢查 20 天未使用群組的機制
            start_inactive_checker()

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
