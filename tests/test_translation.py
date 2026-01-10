"""
FanFan LINE Bot - 翻譯服務測試
"""
import unittest
from services.translation import _translate_with_google, _translate_with_deepl


class TestTranslation(unittest.TestCase):
    """翻譯服務測試"""
    
    def test_google_translation(self):
        """測試 Google 翻譯"""
        text = "Hello"
        result, reason = _translate_with_google(text, "zh-TW")
        
        # Google 翻譯應該成功或因網路問題失敗
        if reason == 'success':
            self.assertIsNotNone(result)
            self.assertNotEqual(result, "")
        else:
            # 若失敗，應該是網路或 timeout 問題
            self.assertIn(reason, ['timeout', 'network_error', 'http_429', 'parse_error'])
    
    def test_number_translation(self):
        """測試純數字不應進行翻譯"""
        from services.translation import translate_text
        text = "123"
        result = translate_text(text, "zh-TW")
        # 純數字應直接返回
        self.assertEqual(result, "123")
    
    def test_empty_text(self):
        """測試空文本"""
        from services.translation import translate_text
        text = ""
        result = translate_text(text, "zh-TW")
        # 空文本應直接返回
        self.assertEqual(result, "")


if __name__ == '__main__':
    unittest.main()
