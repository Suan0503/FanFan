"""
FanFan LINE Bot - 群組翻譯設定服務
"""
from utils import get_data, save_data


def _load_group_langs_from_db(group_id):
    """從資料庫取得群組語言設定（set），若沒有設定則回傳 None。"""
    # 這個函數在使用資料庫時由 main.py 額外處理
    # 這裡只實現 data.json 的版本
    data = get_data()
    if 'user_prefs' not in data:
        return None
    
    langs = data['user_prefs'].get(group_id)
    if langs:
        return set(langs) if isinstance(langs, list) else langs
    return None


def _save_group_langs_to_db(group_id, langs):
    """儲存群組語言設定到資料庫。"""
    data = get_data()
    if 'user_prefs' not in data:
        data['user_prefs'] = {}
    data['user_prefs'][group_id] = list(langs) if isinstance(langs, set) else langs
    save_data(data)


def _delete_group_langs_from_db(group_id):
    """刪除群組的資料庫設定（重設用）。"""
    data = get_data()
    if 'user_prefs' in data:
        data['user_prefs'].pop(group_id, None)
        save_data(data)


def get_group_langs(group_id):
    """對外統一取得群組語言設定，優先使用資料庫，否則退回預設值。"""
    langs = _load_group_langs_from_db(group_id)
    if langs is not None:
        return langs
    # 預設使用繁體中文
    return {'zh-TW'}


def set_group_langs(group_id, langs):
    """對外統一設定群組語言。"""
    _save_group_langs_to_db(group_id, langs)


def get_group_stats_for_status():
    """給 /狀態 與 /統計 用的群組統計資訊。"""
    data = get_data()
    return list(data.get('user_prefs', {}).values())
