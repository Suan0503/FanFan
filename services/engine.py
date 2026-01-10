"""
FanFan LINE Bot - 翻譯引擎偏好管理服務
"""
from utils import get_data, save_data


def get_engine_pref(group_id):
    """取得群組翻譯引擎偏好（google / deepl），優先使用資料庫。"""
    # 先看資料庫（若已連接）
    # 這裡只實現 data.json 版本
    data = get_data()
    engine = data.get("translate_engine_pref", {}).get(group_id)
    if engine in ("google", "deepl"):
        return engine
    return "google"  # 預設使用 Google


def set_engine_pref(group_id, engine):
    """設定群組翻譯引擎偏好，寫入 data.json。"""
    if engine not in ("google", "deepl"):
        engine = "google"

    data = get_data()
    data.setdefault("translate_engine_pref", {})
    data["translate_engine_pref"][group_id] = engine
    save_data(data)
