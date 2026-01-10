"""
FanFan LINE Bot - 資料存儲管理
"""
import os
import json
from config import DATA_FILE

# 全域資料對象
_data = {
    "user_whitelist": [],
    "user_prefs": {},
    "voice_translation": {},
    "group_admin": {},
    "translate_engine_pref": {},
    "tenants": {}
}


def load_data():
    """從 data.json 載入資料"""
    global _data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                loaded_data = json.load(f)
                _data = {
                    "user_whitelist": loaded_data.get("user_whitelist", []),
                    "user_prefs": {
                        k: set(v) if isinstance(v, list) else v
                        for k, v in loaded_data.get("user_prefs", {}).items()
                    },
                    "voice_translation": loaded_data.get("voice_translation", {}),
                    "group_admin": loaded_data.get("group_admin", {}),
                    "translate_engine_pref": loaded_data.get("translate_engine_pref", {}),
                    "tenants": loaded_data.get("tenants", {})
                }
                print("✅ 成功讀取資料！")
            except Exception as e:
                print("❌ 讀取 data.json 出錯，使用預設資料")
    else:
        print("🆕 沒找到資料，創建新的 data.json")
        save_data(_data)


def get_data():
    """取得全域資料"""
    return _data


def save_data(data=None):
    """儲存資料到 data.json"""
    global _data
    if data is not None:
        _data = data
    
    save_data_dict = {
        "user_whitelist": _data["user_whitelist"],
        "user_prefs": {
            k: list(v) if isinstance(v, set) else v
            for k, v in _data["user_prefs"].items()
        },
        "voice_translation": _data["voice_translation"],
        "group_admin": _data.get("group_admin", {}),
        "translate_engine_pref": _data.get("translate_engine_pref", {}),
        "tenants": _data.get("tenants", {})
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(save_data_dict, f, ensure_ascii=False, indent=2)
        print("💾 資料已儲存！")
