"""
Cache module - 高效快取層
用於加快翻譯、群組設定等常用查詢
"""
from collections import OrderedDict
import time
import config


class LRUCache:
    """簡單的 LRU 快取實現"""
    
    def __init__(self, max_size=1000, ttl=3600):
        """
        Args:
            max_size: 最多儲存記錄數
            ttl: 過期時間（秒）
        """
        self.max_size = max_size
        self.ttl = ttl
        self.cache = OrderedDict()  # 維持插入順序
        self.timestamps = {}  # 記錄插入時間
    
    def get(self, key):
        """取得快取值，若過期返回 None"""
        if key not in self.cache:
            return None
        
        # 檢查是否過期
        if time.time() - self.timestamps.get(key, 0) > self.ttl:
            del self.cache[key]
            del self.timestamps[key]
            return None
        
        # 移到最後（LRU）
        self.cache.move_to_end(key)
        return self.cache[key]
    
    def set(self, key, value):
        """設定快取值"""
        if key in self.cache:
            del self.cache[key]
        
        self.cache[key] = value
        self.timestamps[key] = time.time()
        self.cache.move_to_end(key)
        
        # 超出大小限制時刪除最舊的
        if len(self.cache) > self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            del self.timestamps[oldest_key]
    
    def clear(self):
        """清空快取"""
        self.cache.clear()
        self.timestamps.clear()
    
    def size(self):
        """返回當前快取大小"""
        return len(self.cache)


# 翻譯結果快取
translation_cache = LRUCache(
    max_size=config.TRANSLATION_CACHE_SIZE,
    ttl=config.TRANSLATION_CACHE_TTL
)

# 群組語言設定快取
group_langs_cache = LRUCache(
    max_size=500,
    ttl=config.GROUP_LANGS_CACHE_TTL
)

# 租戶快取（長期）
tenant_cache = LRUCache(
    max_size=200,
    ttl=1800  # 30 分鐘
)


def get_translation_cache(text, target_lang):
    """
    取得翻譯快取
    
    Args:
        text: 原文
        target_lang: 目標語言代碼
    
    Returns:
        翻譯結果或 None
    """
    key = f"{text}|{target_lang}"
    return translation_cache.get(key)


def set_translation_cache(text, target_lang, translated_text):
    """
    設定翻譯快取
    
    Args:
        text: 原文
        target_lang: 目標語言代碼
        translated_text: 翻譯結果
    """
    key = f"{text}|{target_lang}"
    translation_cache.set(key, translated_text)


def get_group_langs_cache(group_id):
    """取得群組語言設定快取"""
    return group_langs_cache.get(group_id)


def set_group_langs_cache(group_id, langs):
    """設定群組語言設定快取"""
    group_langs_cache.set(group_id, langs)


def invalidate_group_langs_cache(group_id):
    """刪除群組語言設定快取（用於更新時）"""
    group_langs_cache.cache.pop(group_id, None)
    group_langs_cache.timestamps.pop(group_id, None)


def get_cache_stats():
    """取得快取統計"""
    return {
        "translation_cache_size": translation_cache.size(),
        "group_langs_cache_size": group_langs_cache.size(),
        "tenant_cache_size": tenant_cache.size(),
    }
