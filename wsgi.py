"""
WSGI entry point for production deployment
"""
import os
import sys
import logging

# إضافة مسار التطبيق إلى Python path
sys.path.insert(0, os.path.dirname(__file__))

# إعداد التسجيل للإنتاج
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

try:
    from app import app as application
    logger = logging.getLogger(__name__)
    logger.info("تم تحميل التطبيق بنجاح من app.py")
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"خطأ في استيراد التطبيق: {e}")
    raise

if __name__ == "__main__":
    # للتشغيل المباشر (للاختبار فقط)
    application.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 