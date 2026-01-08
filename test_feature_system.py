"""
功能開關系統測試腳本
用於驗證新年風格選單和 TOKEN 功能開關系統
"""

import json

# 模擬資料結構
test_data = {
    "user_whitelist": [],
    "user_prefs": {},
    "voice_translation": {},
    "group_admin": {},
    "translate_engine_pref": {},
    "feature_switches": {}
}

# 測試功能列表
FEATURE_LIST = {
    "translate": "翻譯功能",
    "voice": "語音翻譯",
    "admin": "管理功能",
    "auto_translate": "自動翻譯",
    "statistics": "統計功能"
}

def generate_group_token():
    """生成唯一的群組 TOKEN"""
    import secrets
    return secrets.token_urlsafe(16)

def set_group_features(group_id, features, token=None):
    """設定群組可用的功能列表"""
    from datetime import datetime
    
    if not token:
        token = generate_group_token()
    
    test_data.setdefault("feature_switches", {})
    test_data["feature_switches"][group_id] = {
        "features": features,
        "token": token,
        "created_at": datetime.utcnow().isoformat()
    }
    return token

def get_group_features(group_id):
    """取得群組可用的功能列表，預設為所有功能"""
    feature_switches = test_data.get("feature_switches", {})
    if group_id not in feature_switches:
        # 預設給予所有功能
        return list(FEATURE_LIST.keys())
    return feature_switches[group_id].get("features", [])

def check_feature_enabled(group_id, feature_name):
    """檢查群組是否啟用某項功能"""
    enabled_features = get_group_features(group_id)
    return feature_name in enabled_features

def get_group_token(group_id):
    """取得群組的 TOKEN"""
    feature_switches = test_data.get("feature_switches", {})
    if group_id in feature_switches:
        return feature_switches[group_id].get("token")
    return None

# 測試案例
def test_feature_system():
    print("=== 開始測試功能開關系統 ===\n")
    
    # 測試 1: 新群組預設功能
    print("測試 1: 新群組預設功能")
    group1 = "C1234567890abcdef"
    features = get_group_features(group1)
    print(f"群組 {group1[:10]}... 的預設功能: {features}")
    print(f"[V] 翻譯功能啟用: {check_feature_enabled(group1, 'translate')}")
    print(f"[V] 語音功能啟用: {check_feature_enabled(group1, 'voice')}\n")
    
    # 測試 2: 設定群組功能（基礎版）
    print("測試 2: 設定群組功能（基礎版）")
    group2 = "C9876543210fedcba"
    token2 = set_group_features(group2, ["translate", "auto_translate"])
    print(f"群組 {group2[:10]}... 設定為基礎版")
    print(f"TOKEN: {token2}")
    print(f"[V] 翻譯功能啟用: {check_feature_enabled(group2, 'translate')}")
    print(f"[X] 語音功能啟用: {check_feature_enabled(group2, 'voice')}")
    print(f"[X] 統計功能啟用: {check_feature_enabled(group2, 'statistics')}\n")
    
    # 測試 3: 設定群組功能（專業版）
    print("測試 3: 設定群組功能（專業版）")
    group3 = "Cabcdef1234567890"
    token3 = set_group_features(group3, list(FEATURE_LIST.keys()))
    print(f"群組 {group3[:10]}... 設定為專業版")
    print(f"TOKEN: {token3}")
    for feature, name in FEATURE_LIST.items():
        status = "[V]" if check_feature_enabled(group3, feature) else "[X]"
        print(f"{status} {name}: {check_feature_enabled(group3, feature)}")
    print()
    
    # 測試 4: 切換功能狀態
    print("測試 4: 切換功能狀態")
    current_features = get_group_features(group2)
    print(f"當前功能: {current_features}")
    
    # 新增語音功能
    if "voice" not in current_features:
        current_features.append("voice")
    set_group_features(group2, current_features, get_group_token(group2))
    print(f"新增語音功能後: {get_group_features(group2)}")
    print(f"[V] 語音功能啟用: {check_feature_enabled(group2, 'voice')}\n")
    
    # 測試 5: 查看 TOKEN
    print("測試 5: 查看所有群組 TOKEN")
    print(json.dumps(test_data["feature_switches"], indent=2, ensure_ascii=False))
    print()
    
    # 測試 6: 功能列表顯示
    print("測試 6: 功能列表顯示")
    for group_id in [group1, group2, group3]:
        features = get_group_features(group_id)
        features_text = '\n'.join([
            f"  {'[V]' if f in features else '[X]'} {FEATURE_LIST[f]}" 
            for f in FEATURE_LIST.keys()
        ])
        print(f"群組 {group_id[:10]}...:")
        print(features_text)
        print()
    
    print("=== 所有測試完成！===")

if __name__ == "__main__":
    test_feature_system()
