"""
Group service - 群組設定管理服務
"""
from models import db, GroupTranslateSetting, GroupActivity, GroupEnginePreference
from datetime import datetime, timedelta
from utils.file_utils import load_json, save_json
from utils.cache import (
    get_group_langs_cache,
    set_group_langs_cache,
    invalidate_group_langs_cache,
)
import config


def _load_group_langs_from_db(group_id):
    """從資料庫取得群組語言設定（set），若沒有設定則回傳 None。"""
    if not db or not group_id:
        return None
    try:
        setting = GroupTranslateSetting.query.filter_by(group_id=group_id).first()
        if not setting or not setting.languages:
            return None
        langs = [c.strip() for c in setting.languages.split(',') if c.strip()]
        return set(langs) if langs else None
    except Exception:
        return None


def _save_group_langs_to_db(group_id, langs):
    """儲存群組語言設定到資料庫，同時維持舊有 data.json 結構。"""
    # 先更新記憶體與 data.json
    data = load_json(config.DATA_FILE)
    if 'user_prefs' not in data:
        data['user_prefs'] = {}
    data['user_prefs'][group_id] = list(langs) if isinstance(langs, set) else langs
    save_json(config.DATA_FILE, data)

    if not db or not group_id:
        return
    try:
        setting = GroupTranslateSetting.query.filter_by(group_id=group_id).first()
        if not setting:
            setting = GroupTranslateSetting(group_id=group_id)
            db.session.add(setting)
        setting.languages = ','.join(sorted(langs)) if langs else ''
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    # 更新快取
    invalidate_group_langs_cache(group_id)


def get_group_langs(group_id):
    """
    對外統一取得群組語言設定，優先使用快取，再用資料庫，最後退回 data.json。
    （已優化：添加快取層）
    """
    # 1️⃣ 檢查快取
    cached = get_group_langs_cache(group_id)
    if cached is not None:
        print(f"✅ [快取命中] 群組語言設定: {group_id}")
        return cached
    
    # 2️⃣ 從 DB 取
    langs = _load_group_langs_from_db(group_id)
    if langs is not None:
        set_group_langs_cache(group_id, langs)  # 設定快取
        return langs
    
    # 3️⃣ 從 data.json 取
    data = load_json(config.DATA_FILE)
    langs = data.get('user_prefs', {}).get(group_id, config.DEFAULT_LANGUAGES)
    set_group_langs_cache(group_id, langs)  # 設定快取
    return langs


def set_group_langs(group_id, langs):
    """對外統一設定群組語言。"""
    _save_group_langs_to_db(group_id, langs)


def touch_group_activity(group_id):
    """更新群組最後活躍時間（只在有資料庫時生效）。"""
    if not db or not group_id:
        return
    try:
        activity = GroupActivity.query.filter_by(group_id=group_id).first()
        now = datetime.utcnow()
        if not activity:
            activity = GroupActivity(group_id=group_id, last_active_at=now)
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
            pref = GroupEnginePreference.query.filter_by(group_id=group_id).first()
            if pref and pref.engine in ("google", "deepl"):
                return pref.engine
        except Exception:
            pass

    # 退回 data.json 記憶體
    data = load_json(config.DATA_FILE)
    engine = data.get("translate_engine_pref", {}).get(group_id)
    if engine in ("google", "deepl"):
        return engine
    return "google"  # 預設使用 Google


def set_engine_pref(group_id, engine):
    """設定群組翻譯引擎偏好，寫入 data.json 與資料庫。"""
    if engine not in ("google", "deepl"):
        engine = "google"

    data = load_json(config.DATA_FILE)
    data.setdefault("translate_engine_pref", {})
    data["translate_engine_pref"][group_id] = engine
    save_json(config.DATA_FILE, data)

    if not db or not group_id:
        return
    try:
        pref = GroupEnginePreference.query.filter_by(group_id=group_id).first()
        if not pref:
            pref = GroupEnginePreference(group_id=group_id, engine=engine)
            db.session.add(pref)
        else:
            pref.engine = engine
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_group_stats_for_status():
    """給 /狀態 與 /統計 用的群組統計資訊。"""
    if db:
        try:
            settings = GroupTranslateSetting.query.all()
            lang_sets = []
            for s in settings:
                if s.languages:
                    lang_sets.append(set([c.strip() for c in s.languages.split(',') if c.strip()]))
            return lang_sets
        except Exception:
            pass

    data = load_json(config.DATA_FILE)
    return list(data.get('user_prefs', {}).values())


def check_inactive_groups():
    """檢查超過 INACTIVE_GROUP_DAYS 天沒有任何活動的群組，自動退出群組。"""
    if not db:
        return

    try:
        threshold = datetime.utcnow() - timedelta(days=config.INACTIVE_GROUP_DAYS)
        inactive = GroupActivity.query.filter(GroupActivity.last_active_at < threshold).all()
    except Exception:
        return

    if not inactive:
        return

    from linebot import LineBotApi
    line_bot_api = LineBotApi(config.CHANNEL_ACCESS_TOKEN)

    for activity in inactive:
        group_id = activity.group_id
        try:
            print(f"🚪 超過 {config.INACTIVE_GROUP_DAYS} 天未使用，自動退出群組: {group_id}")
            line_bot_api.leave_group(group_id)
        except Exception as e:
            print(f"❌ 退出群組 {group_id} 失敗: {e}")

        # 清理記憶體中的資料
        try:
            data = load_json(config.DATA_FILE)
            if 'user_prefs' in data:
                data['user_prefs'].pop(group_id, None)
            if 'voice_translation' in data:
                data['voice_translation'].pop(group_id, None)
            if 'group_admin' in data:
                data['group_admin'].pop(group_id, None)
            if 'auto_translate' in data:
                data['auto_translate'].pop(group_id, None)
            save_json(config.DATA_FILE, data)
        except Exception:
            pass

        # 清理資料庫中的設定
        if not db:
            continue
        try:
            setting = GroupTranslateSetting.query.filter_by(group_id=group_id).first()
            if setting:
                db.session.delete(setting)
            db.session.delete(activity)
            db.session.commit()
        except Exception:
            db.session.rollback()
