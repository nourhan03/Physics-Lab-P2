# PHY Lab Management System

نظام إدارة المختبرات الفيزيائية - تطبيق Flask لإدارة حجوزات المختبرات والأجهزة والصيانة.

## المميزات

- إدارة حجوزات المختبرات والأجهزة
- نظام صيانة ذكي مع توقعات AI
- تتبع استخدام الأجهزة وساعات التشغيل  
- إدارة قطع الغيار والاحتياجات المستقبلية
- واجهة API RESTful
- دعم Real-time مع Socket.IO

## التقنيات المستخدمة

- **Backend**: Flask, Flask-RESTful, Flask-SocketIO
- **Database**: SQL Server / PostgreSQL
- **Scheduler**: APScheduler
- **Deployment**: Railway, Docker
- **WSGI**: Gunicorn with Eventlet

## Deployment على Railway

### 1. إعداد المشروع

```bash
git clone <repository-url>
cd PHY-Lab-3
```

### 2. إعداد قاعدة البيانات

في Railway، أضف PostgreSQL service أو استخدم External SQL Server.

### 3. متغيرات البيئة المطلوبة

في Railway Dashboard، أضف المتغيرات التالية:

```
DATABASE_URL=postgresql://username:password@hostname:port/database_name
FLASK_ENV=production
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
```

أو للـ SQL Server:

```
DB_CONNECTION_STRING=Driver={ODBC Driver 17 for SQL Server};Server=your_server;Database=your_db;UID=your_username;PWD=your_password;Encrypt=no;TrustServerCertificate=yes;MultipleActiveResultSets=True;Connection Timeout=30;
```

### 4. Deploy

1. ربط Repository بـ Railway
2. Railway سيكتشف `Dockerfile` تلقائياً
3. سيتم البناء والنشر تلقائياً

### 5. Health Check

التطبيق يتضمن endpoint للفحص الصحي:
```
GET /health
```

## التشغيل المحلي

```bash
# إنشاء بيئة افتراضية
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# تثبيت التبعيات
pip install -r requirements.txt

# تشغيل التطبيق
python app.py
```

## API Endpoints

- `GET /health` - فحص صحة التطبيق
- `GET/POST /reservations` - إدارة الحجوزات
- `GET /devices/maintenance-needed` - الأجهزة التي تحتاج صيانة
- `GET /api/devices-maintenance-prediction` - توقعات الصيانة
- `GET /devices-replacement` - الأجهزة التي تحتاج استبدال
- `GET /future-spare-parts-needs` - احتياجات قطع الغيار

## الإعدادات المتقدمة

### Docker Build

```bash
docker build -t phy-lab .
docker run -p 5000:5000 phy-lab
```

### Production Settings

التطبيق محضر للإنتاج مع:
- Gunicorn WSGI server
- Eventlet worker class
- Health check endpoint
- Proper logging
- Security configurations

## المشاكل الشائعة

### مشكلة ODBC Driver

إذا كنت تستخدم SQL Server، تأكد من وجود ODBC Driver. الـ Dockerfile يتضمن تثبيت `msodbcsql17`.

### مشكلة Port

Railway يستخدم متغير `PORT` تلقائياً. التطبيق محضر للتعامل مع هذا.

### مشكلة Database Connection

تأكد من صحة `DATABASE_URL` أو `DB_CONNECTION_STRING` في متغيرات البيئة.

## الدعم

للمساعدة والدعم، تواصل مع فريق التطوير. 