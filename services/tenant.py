"""
FanFan LINE Bot - 租戶管理服務
提供租戶訂閱、驗證、統計追蹤等功能
"""
import secrets
from datetime import datetime, timedelta
from utils import get_data, save_data


def generate_tenant_token():
    """生成唯一的租戶 TOKEN"""
    return secrets.token_urlsafe(16)


def create_tenant(user_id, months=1):
    """創建租戶訂閱"""
    data = get_data()
    token = generate_tenant_token()
    expires_at = (datetime.utcnow() + timedelta(days=30 * months)).isoformat()
    
    data.setdefault("tenants", {})
    data["tenants"][user_id] = {
        "token": token,
        "expires_at": expires_at,
        "groups": [],
        "stats": {
            "translate_count": 0,
            "char_count": 0
        },
        "created_at": datetime.utcnow().isoformat()
    }
    save_data(data)
    return token, expires_at


def get_tenant_by_group(group_id):
    """根據群組ID取得租戶"""
    data = get_data()
    tenants = data.get("tenants", {})
    for user_id, tenant in tenants.items():
        if group_id in tenant.get("groups", []):
            return user_id, tenant
    return None, None


def is_tenant_valid(user_id):
    """檢查租戶是否有效（未過期）"""
    data = get_data()
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
    data = get_data()
    tenants = data.get("tenants", {})
    if user_id not in tenants:
        return False
    
    if group_id not in tenants[user_id].get("groups", []):
        tenants[user_id].setdefault("groups", []).append(group_id)
        save_data(data)
    return True


def update_tenant_stats(user_id, translate_count=0, char_count=0):
    """更新租戶統計資料"""
    data = get_data()
    tenants = data.get("tenants", {})
    if user_id in tenants:
        stats = tenants[user_id].setdefault("stats", {"translate_count": 0, "char_count": 0})
        stats["translate_count"] = stats.get("translate_count", 0) + translate_count
        stats["char_count"] = stats.get("char_count", 0) + char_count
        save_data(data)
