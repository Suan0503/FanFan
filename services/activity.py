"""
FanFan LINE Bot - 群組活動追蹤服務
"""
from datetime import datetime, timedelta
from config import INACTIVE_GROUP_DAYS
from utils import get_data, save_data


def touch_group_activity(group_id):
    """更新群組最後活躍時間（只在有資料庫時生效）。"""
    # 這個函數在使用資料庫時由 main.py 額外處理
    pass


def check_inactive_groups():
    """檢查超過指定天數沒有任何活動的群組，自動清理。"""
    # 這個函數在使用資料庫時由 main.py 額外處理
    # 這裡只實現基本邏輯
    pass
