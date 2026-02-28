# db.py - قاعدة البيانات المتكاملة لبوت المناوبات (نسخة سريعة)

import sqlite3
from datetime import datetime, timedelta

DB_NAME = 'duty_bot.db'

def get_db():
    """إنشاء اتصال بقاعدة البيانات"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """إنشاء الجداول المطلوبة"""
    conn = get_db()
    cursor = conn.cursor()
    
    # جدول المستخدمين (الأطباء)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            approved INTEGER DEFAULT 0,
            max_days INTEGER DEFAULT 2,
            registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP
        )
    ''')
    
    # جدول الحجوزات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            booked_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            month TEXT NOT NULL,
            reminder_sent_24h INTEGER DEFAULT 0,
            reminder_sent_same_day INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            UNIQUE(day, month)
        )
    ''')
    
    # جدول إعدادات النظام
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول طلبات الانتظار
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_approvals (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # إضافة الإعدادات الافتراضية
    default_settings = [
        ('month_days', '31'),
        ('booking_open', '0'),
        ('scheduled_booking_time', '')
    ]
    
    for key, value in default_settings:
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
    
    conn.commit()
    conn.close()

# ==================== دوال المستخدمين ====================

def get_user(user_id):
    """الحصول على معلومات مستخدم"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_approved_users():
    """الحصول على قائمة المستخدمين المعتمدين"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE approved = 1 ORDER BY full_name")
    users = cursor.fetchall()
    conn.close()
    return users

def get_pending_users():
    """الحصول على قائمة المستخدمين المنتظرين"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pending_approvals ORDER BY request_date")
    users = cursor.fetchall()
    conn.close()
    return users

def add_user(user_id, full_name):
    """إضافة مستخدم جديد لقائمة الانتظار"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO pending_approvals (user_id, full_name) VALUES (?, ?)",
        (user_id, full_name)
    )
    conn.commit()
    conn.close()

def approve_user(user_id, max_days=2):
    """الموافقة على مستخدم"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT full_name FROM pending_approvals WHERE user_id = ?", (user_id,))
    pending = cursor.fetchone()
    
    if pending:
        cursor.execute(
            "INSERT INTO users (user_id, full_name, approved, max_days) VALUES (?, ?, 1, ?)",
            (user_id, pending['full_name'], max_days)
        )
        cursor.execute("DELETE FROM pending_approvals WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False

def reject_user(user_id):
    """رفض مستخدم"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_approvals WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def update_user_max_days(user_id, max_days):
    """تحديث عدد الأيام المسموحة لمستخدم"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET max_days = ? WHERE user_id = ?",
        (max_days, user_id)
    )
    conn.commit()
    conn.close()

def delete_user(user_id):
    """حذف مستخدم نهائياً"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM bookings WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM pending_approvals WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def update_last_active(user_id):
    """تحديث آخر نشاط للمستخدم"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()

# ==================== دوال الحجوزات ====================

def get_current_month():
    """الحصول على الشهر الحالي بصيغة YYYY-MM"""
    now = datetime.now()
    return f"{now.year}-{now.month:02d}"

def get_month_days():
    """الحصول على عدد أيام الشهر"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'month_days'")
    result = cursor.fetchone()
    conn.close()
    return int(result['value']) if result else 31

def set_month_days(days):
    """تحديد عدد أيام الشهر"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ('month_days', str(days))
    )
    conn.commit()
    conn.close()

def get_user_bookings(user_id, month=None):
    """الحصول على حجوزات مستخدم معين"""
    if month is None:
        month = get_current_month()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT day FROM bookings WHERE user_id = ? AND month = ? ORDER BY day",
        (user_id, month)
    )
    bookings = cursor.fetchall()
    conn.close()
    return bookings

def get_all_bookings(month=None):
    """الحصول على جميع الحجوزات للشهر الحالي"""
    if month is None:
        month = get_current_month()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.day, b.user_id, u.full_name
        FROM bookings b
        JOIN users u ON b.user_id = u.user_id
        WHERE b.month = ?
        ORDER BY b.day
    """, (month,))
    bookings = cursor.fetchall()
    conn.close()
    return bookings

def book_day(user_id, day, month=None):
    """حجز يوم مع التحقق من جميع الشروط"""
    if month is None:
        month = get_current_month()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # التحقق من أن اليوم غير محجوز
    cursor.execute(
        "SELECT * FROM bookings WHERE day = ? AND month = ?",
        (day, month)
    )
    if cursor.fetchone():
        conn.close()
        return False, "❌ اليوم محجوز مسبقاً"
    
    # التحقق من عدد أيام المستخدم
    user = get_user(user_id)
    if not user:
        conn.close()
        return False, "❌ المستخدم غير موجود"
    
    user_bookings = cursor.execute(
        "SELECT COUNT(*) as count FROM bookings WHERE user_id = ? AND month = ?",
        (user_id, month)
    ).fetchone()['count']
    
    if user_bookings >= user['max_days']:
        conn.close()
        return False, f"❌ لقد وصلت للحد الأقصى ({user['max_days']} أيام)"
    
    # التحقق من أن اليوم ضمن أيام الشهر
    month_days = get_month_days()
    if day > month_days:
        conn.close()
        return False, f"❌ اليوم {day} خارج نطاق أيام الشهر ({month_days} يوم)"
    
    # حجز اليوم
    cursor.execute(
        "INSERT INTO bookings (day, user_id, month) VALUES (?, ?, ?)",
        (day, user_id, month)
    )
    
    conn.commit()
    conn.close()
    return True, "✅ تم الحجز بنجاح"

def cancel_booking(day, month=None, user_id=None):
    """إلغاء حجز يوم"""
    if month is None:
        month = get_current_month()
    
    conn = get_db()
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute(
            "DELETE FROM bookings WHERE day = ? AND month = ? AND user_id = ?",
            (day, month, user_id)
        )
    else:
        cursor.execute(
            "DELETE FROM bookings WHERE day = ? AND month = ?",
            (day, month)
        )
    
    conn.commit()
    conn.close()
    return True

def reset_month(month=None):
    """تصفير الشهر بالكامل"""
    if month is None:
        month = get_current_month()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bookings WHERE month = ?", (month,))
    conn.commit()
    conn.close()

# ==================== دوال الإعدادات ====================

def is_booking_open():
    """التحقق إذا كان الحجز مفتوحاً"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'booking_open'")
    result = cursor.fetchone()
    conn.close()
    return result and result['value'] == '1'

def set_booking_open(status):
    """فتح أو غلق الحجز"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ('booking_open', '1' if status else '0')
    )
    conn.commit()
    conn.close()

def set_scheduled_booking_time(datetime_str):
    """حفظ وقت فتح الحجز المجدول"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ('scheduled_booking_time', datetime_str)
    )
    conn.commit()
    conn.close()

def get_scheduled_booking_time():
    """الحصول على وقت فتح الحجز المجدول"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'scheduled_booking_time'")
    result = cursor.fetchone()
    conn.close()
    return result['value'] if result else None

# ==================== دوال الإحصائيات ====================

def get_month_statistics():
    """إحصائيات سريعة للشهر"""
    month = get_current_month()
    month_days = get_month_days()
    bookings = get_all_bookings(month)
    users = get_approved_users()
    
    return {
        'month': month,
        'month_days': month_days,
        'booked_days': len(bookings),
        'free_days': month_days - len(bookings),
        'total_doctors': len(users)
    }

def get_tomorrow_bookings():
    """الحصول على حجوزات الغد"""
    month = get_current_month()
    tomorrow = (datetime.now() + timedelta(days=1)).day
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, u.full_name, u.user_id 
        FROM bookings b
        JOIN users u ON b.user_id = u.user_id
        WHERE b.month = ? AND b.day = ? AND b.reminder_sent_24h = 0
    """, (month, tomorrow))
    bookings = cursor.fetchall()
    conn.close()
    return bookings

def get_today_bookings():
    """الحصول على حجوزات اليوم"""
    month = get_current_month()
    today = datetime.now().day
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, u.full_name, u.user_id 
        FROM bookings b
        JOIN users u ON b.user_id = u.user_id
        WHERE b.month = ? AND b.day = ? AND b.reminder_sent_same_day = 0
    """, (month, today))
    bookings = cursor.fetchall()
    conn.close()
    return bookings

def mark_reminder_sent(booking_id, reminder_type):
    """تحديث حالة إرسال التذكير"""
    conn = get_db()
    cursor = conn.cursor()
    if reminder_type == '24h':
        cursor.execute(
            "UPDATE bookings SET reminder_sent_24h = 1 WHERE id = ?",
            (booking_id,)
        )
    elif reminder_type == 'same_day':
        cursor.execute(
            "UPDATE bookings SET reminder_sent_same_day = 1 WHERE id = ?",
            (booking_id,)
        )
    conn.commit()
    conn.close()

# تهيئة قاعدة البيانات
init_db()