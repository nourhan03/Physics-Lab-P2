# استخدام Python 3.12 slim image لتقليل الحجم
FROM python:3.12-slim

# تعيين متغيرات البيئة
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# تحديث النظام وتثبيت التبعيات الأساسية
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    unixodbc \
    unixodbc-dev \
    gnupg \
    apt-transport-https \
    && rm -rf /var/lib/apt/lists/*

# تثبيت Microsoft ODBC Driver
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    rm -rf /var/lib/apt/lists/*

# إنشاء مجلد العمل
WORKDIR /app

# نسخ وتثبيت التبعيات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ كود التطبيق
COPY . .

# إنشاء مستخدم غير root
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# تعيين PORT
EXPOSE 5000

# تشغيل التطبيق
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "eventlet", "--workers", "1", "--timeout", "120", "app:app"] 