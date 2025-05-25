from flask import Flask, jsonify
from flask_cors import CORS
from flask_restful import Api
from extensions import db, socketio, scheduler
from resources import ReservationListResource, ReservationResource, MaintenanceNeededResource, SuggestDeviceResource, DeviceMaintenancePredictionResource, DevicesReplacementResource, FutureNeedsResource
import signal
import sys
import urllib.parse
import os
import logging

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_app(config_name='default'):
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "*"}})
    
    # استخدام متغيرات بيئية للاتصال
    db_url = os.environ.get('DATABASE_URL')
    
    if db_url:
        # للتعامل مع عناوين قواعد البيانات من Railway التي قد تبدأ بـ postgres://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    else:
        # استخدام الاتصال الافتراضي
        connection_string = os.environ.get('DB_CONNECTION_STRING', 
            "Driver={ODBC Driver 17 for SQL Server};"
            "Server=db17785.public.databaseasp.net;"
            "Database=db17785;"
            "UID=db17785;"
            "PWD=9t?TyP7#@6pX;"
            "Encrypt=no;"
            "TrustServerCertificate=yes;"
            "MultipleActiveResultSets=True;"
            "Connection Timeout=30;"
        )
        params = urllib.parse.quote_plus(connection_string)
        app.config['SQLALCHEMY_DATABASE_URI'] = f"mssql+pyodbc:///?odbc_connect={params}"
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # إضافة مسار للفحص الصحي
    @app.route('/health')
    def health_check():
        return jsonify({'status': 'healthy'}), 200
    
    # تعيين ترميز JSON إلى UTF-8
    app.config['JSON_AS_ASCII'] = False
    
    # إعداد APScheduler - تعطيل API لتجنب التعارض
    app.config['SCHEDULER_API_ENABLED'] = False
    app.config['SCHEDULER_TIMEZONE'] = 'UTC'
    app.config['SCHEDULER_DAEMON'] = False  
       
    db.init_app(app)
    socketio.init_app(app, 
                     cors_allowed_origins="*",
                     async_mode='threading',  
                     daemon=False)  
    scheduler.init_app(app)
    
    api = Api(app)
    # Reservation List Resource
    api.add_resource(ReservationListResource, '/reservations')
    api.add_resource(ReservationResource, '/reservations/<int:reservation_id>')

    # Maintenance Needed Resource
    api.add_resource(MaintenanceNeededResource, '/devices/maintenance-needed')

    # Suggest Device Resource
    api.add_resource(SuggestDeviceResource, '/devices/suggest/<int:device_id>')
    
    # توقعات الصيانة للأجهزة المتاحة
    api.add_resource(DeviceMaintenancePredictionResource, '/api/devices-maintenance-prediction')
    
    # الأجهزة التي تحتاج إلى استبدال
    api.add_resource(DevicesReplacementResource, '/devices-replacement')
    
    # الاحتياجات المستقبلية من قطع الغيار
    api.add_resource(FutureNeedsResource, '/future-spare-parts-needs')
    
    logger.info("تم إنشاء التطبيق بنجاح")
    return app  # Return the app instance

app = create_app()  # Create the app instance globally

def cleanup_resources():
    with app.app_context():
        try:
            scheduler.shutdown()
            db.session.remove()
            db.engine.dispose()
            logger.info("تم تنظيف الموارد بنجاح")
        except Exception as e:
            logger.error(f'Error during cleanup: {str(e)}')
    
def signal_handler(sig, frame):
    logger.info('تم استلام إشارة إنهاء. جاري إغلاق التطبيق...')
    cleanup_resources()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"بدء تشغيل التطبيق على المنفذ {port}")
    scheduler.start()
    try:
        socketio.run(app, debug=False, use_reloader=False, host="0.0.0.0", port=port)
    except KeyboardInterrupt:
        logger.info('تم إيقاف التطبيق بواسطة المستخدم')
    except Exception as e:
        logger.error(f'حدث خطأ أثناء تشغيل التطبيق: {str(e)}')
    finally:
        cleanup_resources()

