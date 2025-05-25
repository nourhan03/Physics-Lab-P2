from flask_socketio import SocketIO
from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
socketio = SocketIO(async_mode='threading', daemon=False)
scheduler = APScheduler()

def init_extensions(app):
    """تهيئة تمديدات Flask"""
    # تهيئة قاعدة البيانات
    db.init_app(app)
    
    # تهيئة Socket.IO
    socketio.init_app(app, cors_allowed_origins="*")
    
    # أي تهيئة أخرى ضرورية
    
    # إنشاء جميع الجداول إذا لم تكن موجودة
    with app.app_context():
        db.create_all() 