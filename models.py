"""
資料庫模型定義
"""
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Tenant(db.Model):
    """租戶模型 - 付費用戶"""
    __tablename__ = 'tenants'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), unique=True, nullable=False, index=True)  # LINE user ID
    token = db.Column(db.String(500), nullable=False)  # LINE Personal Token
    expires_at = db.Column(db.DateTime, nullable=False)  # 到期日
    is_active = db.Column(db.Boolean, default=True)  # 是否啟用
    plan = db.Column(db.String(20), default='premium')  # premium/free
    
    # 統計資料
    translate_count = db.Column(db.Integer, default=0)
    char_count = db.Column(db.Integer, default=0)
    
    # 提醒記錄
    reminded_7days = db.Column(db.Boolean, default=False)  # 7天提醒已發送
    reminded_1day = db.Column(db.Boolean, default=False)   # 1天提醒已發送
    
    # 時間戳記
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 關聯
    groups = db.relationship('Group', backref='tenant', lazy=True, cascade='all, delete-orphan')
    
    def is_expired(self):
        """檢查是否過期"""
        return datetime.utcnow() > self.expires_at
    
    def days_remaining(self):
        """剩餘天數"""
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)
    
    def should_remind_7days(self):
        """是否應該發送7天提醒"""
        return self.days_remaining() <= 7 and not self.reminded_7days
    
    def should_remind_1day(self):
        """是否應該發送1天提醒"""
        return self.days_remaining() <= 1 and not self.reminded_1day
    
    def to_dict(self):
        return {
            'user_id': self.user_id,
            'token': self.token,
            'expires_at': self.expires_at.isoformat(),
            'is_active': self.is_active,
            'plan': self.plan,
            'translate_count': self.translate_count,
            'char_count': self.char_count,
            'days_remaining': self.days_remaining()
        }


class Group(db.Model):
    """群組模型 - 租戶管理的群組"""
    __tablename__ = 'groups'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.String(100), unique=True, nullable=False, index=True)  # LINE group ID
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    
    # 群組設定
    auto_translate = db.Column(db.Boolean, default=True)  # 自動翻譯
    voice_translation = db.Column(db.Boolean, default=True)  # 語音翻譯
    engine_pref = db.Column(db.String(20), default='google')  # google/deepl
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 關聯
    user_prefs = db.relationship('UserPreference', backref='group', lazy=True, cascade='all, delete-orphan')
    group_admins = db.relationship('GroupAdmin', backref='group', lazy=True, cascade='all, delete-orphan')


class UserPreference(db.Model):
    """用戶語言偏好"""
    __tablename__ = 'user_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    user_id = db.Column(db.String(100), nullable=False)  # LINE user ID in group
    languages = db.Column(db.JSON, default=list)  # ['zh-TW', 'en', ...]
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('group_id', 'user_id', name='unique_group_user'),
    )


class GroupAdmin(db.Model):
    """群組臨時管理員"""
    __tablename__ = 'group_admins'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    user_id = db.Column(db.String(100), nullable=False)  # LINE user ID
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('group_id', 'user_id', name='unique_group_admin'),
    )


class Whitelist(db.Model):
    """白名單用戶（免費使用）"""
    __tablename__ = 'whitelists'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
