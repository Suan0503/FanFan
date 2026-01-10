"""
Tenant service - 租戶管理服務
"""
import json
from datetime import datetime, timedelta
from utils.file_utils import load_json, save_json
import config


def generate_tenant_token():
    """生成唯一的租戶 TOKEN"""
    import secrets
    return secrets.token_urlsafe(16)


def create_tenant(user_id, months=1):
    """
    創建租戶訂閱
    
    Args:
        user_id: 用戶 ID
        months: 訂閱月數 (1-12)
    
    Returns:
        (token, expires_at)
    """
    token = generate_tenant_token()
    expires_at = (datetime.utcnow() + timedelta(days=30 * months)).isoformat()
    
    data = load_json(config.DATA_FILE)
    data.setdefault("tenants", {})
    data["tenants"][user_id] = {
        "token": token,
        "expires_at": expires_at,
        "groups": [],
        "stats": {"translate_count": 0, "char_count": 0},
        "created_at": datetime.utcnow().isoformat()
    }
    save_json(config.DATA_FILE, data)
    return token, expires_at


def get_tenant_by_group(group_id):
    """根據群組 ID 取得租戶"""
    data = load_json(config.DATA_FILE)
    tenants = data.get("tenants", {})
    for user_id, tenant in tenants.items():
        if group_id in tenant.get("groups", []):
            return user_id, tenant
    return None, None


def is_tenant_valid(user_id):
    """檢查租戶是否有效（未過期）"""
    data = load_json(config.DATA_FILE)
    tenants = data.get("tenants", {})
    if user_id not in tenants:
        return False
    
    expires_at = tenants[user_id].get("expires_at")
    if not expires_at:
        return False
    
    try:
        expire_dt = datetime.fromisoformat(expires_at)
        return datetime.utcnow() < expire_dt
    except:
        return False


def add_group_to_tenant(user_id, group_id):
    """將群組加入租戶管理"""
    data = load_json(config.DATA_FILE)
    tenants = data.get("tenants", {})
    if user_id not in tenants:
        return False
    
    if group_id not in tenants[user_id].get("groups", []):
        tenants[user_id].setdefault("groups", []).append(group_id)
        save_json(config.DATA_FILE, data)
    return True


def update_tenant_stats(user_id, translate_count=0, char_count=0):
    """更新租戶統計資料"""
    data = load_json(config.DATA_FILE)
    tenants = data.get("tenants", {})
    if user_id in tenants:
        stats = tenants[user_id].setdefault("stats", {"translate_count": 0, "char_count": 0})
        stats["translate_count"] = stats.get("translate_count", 0) + translate_count
        stats["char_count"] = stats.get("char_count", 0) + char_count
        save_json(config.DATA_FILE, data)


def update_tenant_stats_by_group(group_id, translate_count=0, char_count=0):
    """根據群組 ID 更新租戶統計資料"""
    user_id, tenant = get_tenant_by_group(group_id)
    if user_id:
        update_tenant_stats(user_id, translate_count, char_count)


def check_group_access(group_id):
    """檢查群組是否有有效的租戶訂閱（預設全開放）"""
    user_id, tenant = get_tenant_by_group(group_id)
    if user_id:
        return is_tenant_valid(user_id)
    # 預設：未設定租戶的群組全功能開放
    return True
