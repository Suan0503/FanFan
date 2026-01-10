"""
Database models module - 定義所有 SQLAlchemy 資料庫模型
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class GroupTranslateSetting(db.Model):
    """群組翻譯設定：每個群組選擇的目標語言清單。"""
    __tablename__ = "group_translate_setting"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(db.String(255), unique=True, nullable=False)
    # 以逗號分隔的語言代碼，例如："en,zh-TW,ja"
    languages = db.Column(db.String(255), nullable=False, default="zh-TW")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class GroupActivity(db.Model):
    """紀錄群組最後活躍時間，用來判斷是否自動退出群組。"""
    __tablename__ = "group_activity"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(db.String(255), unique=True, nullable=False)
    last_active_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class GroupEnginePreference(db.Model):
    """每個群組的翻譯引擎偏好（google / deepl）。"""
    __tablename__ = "group_engine_preference"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(db.String(255), unique=True, nullable=False)
    engine = db.Column(db.String(20), nullable=False, default="google")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


def init_db(app):
    """初始化資料庫"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
