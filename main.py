# main.py - البوت المتكامل لإدارة المناوبات (نسخة نهائية سريعة)

import logging
from datetime import datetime, timedelta
import threading
import csv
from io import StringIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN, ADMIN_ID
import db

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING  # تقليل التسريع
)
logger = logging.getLogger(__name__)

# متغيرات عامة للتذكيرات
reminder_timers = []

# ==================== دوال المساعدة والواجهات ====================

def get_main_keyboard(user_id):
    """لوحة المفاتيح الرئيسية للمستخدمين"""
    is_admin = (user_id == ADMIN_ID)
    
    keyboard = [
        [KeyboardButton("📅 حجز مناوبة")],
        [KeyboardButton("📋 عرض الجدول")],
        [KeyboardButton("👤 ملفي الشخصي")],
        [KeyboardButton("📚 كيفية الاستخدام")]
    ]
    
    if is_admin:
        keyboard.append([KeyboardButton("⚙️ لوحة المشرف")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    """لوحة مفاتيح المشرف المتكاملة"""
    keyboard = [
        [KeyboardButton("👥 طلبات موافقة"), KeyboardButton("📋 قائمة الأطباء")],
        [KeyboardButton("🗑 حذف مستخدم"), KeyboardButton("📊 إحصائيات")],
        [KeyboardButton("🔓 فتح الحجز"), KeyboardButton("🔒 غلق الحجز")],
        [KeyboardButton("⏰ فتح مجدول"), KeyboardButton("📅 ضبط أيام الشهر")],
        [KeyboardButton("📢 إشعار جماعي"), KeyboardButton("📥 تصدير الجدول")],
        [KeyboardButton("➕ زيادة أيام"), KeyboardButton("➖ تقليل أيام")],
        [KeyboardButton("🔄 بدء شهر جديد")],
        [KeyboardButton("🔙 العودة للقائمة الرئيسية")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def format_schedule():
    """تنسيق جدول المناوبات بشكل جميل"""
    month = db.get_current_month()
    bookings = db.get_all_bookings(month)
    month_days = db.get_month_days()
    
    # تحويل الحجوزات إلى قاموس
    booked = {b['day']: b['full_name'] for b in bookings}
    
    # ترجمة الشهر
    months = {
        '01': 'يناير', '02': 'فبراير', '03': 'مارس', '04': 'أبريل',
        '05': 'مايو', '06': 'يونيو', '07': 'يوليو', '08': 'أغسطس',
        '09': 'سبتمبر', '10': 'أكتوبر', '11': 'نوفمبر', '12': 'ديسمبر'
    }
    year, month_num = month.split('-')
    month_name = months.get(month_num, month_num)
    
    # إنشاء الجدول
    schedule = "╔" + "═" * 35 + "╗\n"
    schedule += f"║       📋 جدول مناوبات {month_name} {year}       ║\n"
    schedule += "╠" + "═" * 35 + "╣\n"
    
    # عرض الأيام في 3 أعمدة
    days_line = ""
    for i in range(1, month_days + 1, 3):
        line = "║ "
        for j in range(3):
            day = i + j
            if day <= month_days:
                if day in booked:
                    name = booked[day].split()[-1][:8]  # اختصار الاسم
                    line += f"▪️ {day:2d}:{name:8} "
                else:
                    line += f"▫️ {day:2d}:---      "
            else:
                line += "              "
        schedule += line + "║\n"
    
    schedule += "╠" + "═" * 35 + "╣\n"
    schedule += f"║ ✅ محجوز: {len(bookings):2d}  │  ⬜ شاغر: {month_days - len(bookings):2d} ║\n"
    schedule += "╚" + "═" * 35 + "╝"
    
    return schedule

def get_days_keyboard(user_id):
    """إنشاء لوحة أيام الحجز"""
    month = db.get_current_month()
    bookings = db.get_all_bookings(month)
    booked_days = [b['day'] for b in bookings]
    
    user = db.get_user(user_id)
    if not user:
        return None, "المستخدم غير موجود"
    
    user_bookings = [b['day'] for b in db.get_user_bookings(user_id, month)]
    
    # حساب الأيام المتاحة
    month_days = db.get_month_days()
    available_days = [d for d in range(1, month_days + 1) if d not in booked_days]
    
    if not available_days:
        return None, "⚠️ لا توجد أيام متاحة للحجز"
    
    # إنشاء أزرار الأيام (5 أعمدة)
    keyboard = []
    row = []
    
    for i, day in enumerate(available_days, 1):
        button_text = f"📌 {day}" if day in user_bookings else str(day)
        row.append(InlineKeyboardButton(button_text, callback_data=f"book_{day}"))
        
        if i % 5 == 0:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    # أزرار التحكم
    keyboard.append([
        InlineKeyboardButton("❌ إلغاء", callback_data="cancel_booking")
    ])
    
    # معلومات للمستخدم
    remaining = user['max_days'] - len(user_bookings)
    header = (
        f"📅 *حجز مناوبة*\n\n"
        f"👤 د.{user['full_name']}\n"
        f"📊 الأيام المتبقية: {remaining} من {user['max_days']}\n"
        f"📍 أيامك: {', '.join(map(str, sorted(user_bookings))) if user_bookings else 'لا يوجد'}\n\n"
        f"🔽 اختر اليوم:"
    )
    
    return InlineKeyboardMarkup(keyboard), header

def get_help_text(user):
    """نص المساعدة الشامل"""
    max_days = user['max_days'] if user else 2
    
    return f"""
╔════════════════════════════╗
║     📚 دليل استخدام البوت     ║
╚════════════════════════════╝

🔹 *الخطوات الأولى:*
  1. أرسل /start
  2. أرسل اسمك الثلاثي
  3. انتظر موافقة المشرف

🔹 *الأوامر المتاحة:*
  📅 حجز مناوبة - لحجز يوم
  📋 عرض الجدول - لعرض المناوبات
  👤 ملفي الشخصي - لمعلوماتك
  📚 كيفية الاستخدام - هذا الدليل

🔹 *القواعد:*
  • الحد الأقصى: {max_days} أيام
  • تذكير قبل 24 ساعة
  • تذكير في يوم المناوبة
  • يمكنك حذف حجزك

🔹 *للتواصل:*
  راسل المشرف للمساعدة

بالتوفيق للجميع! 🩺
"""

def export_to_csv():
    """تصدير الجدول إلى CSV"""
    month = db.get_current_month()
    bookings = db.get_all_bookings(month)
    month_days = db.get_month_days()
    
    booked_dict = {b['day']: b for b in bookings}
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['اليوم', 'التاريخ', 'الطبيب'])
    
    for day in range(1, month_days + 1):
        if day in booked_dict:
            writer.writerow([day, f"{month}-{day:02d}", booked_dict[day]['full_name']])
        else:
            writer.writerow([day, f"{month}-{day:02d}", 'متاح'])
    
    return output.getvalue()

# ==================== المهام الدورية (مخففة) ====================

def check_and_send_reminders(app):
    """فحص وإرسال التذكيرات"""
    try:
        month = db.get_current_month()
        tomorrow = (datetime.now() + timedelta(days=1)).day
        today = datetime.now().day
        
        bookings = db.get_all_bookings(month)
        
        for booking in bookings:
            if booking['day'] == tomorrow:
                try:
                    app.bot.send_message(
                        chat_id=booking['user_id'],
                        text=f"🔔 *تذكير مهم*\n\n"
                             f"عزيزي د.{booking['full_name']}\n"
                             f"لديك مناوبة غداً (اليوم {booking['day']})\n\n"
                             f"بالتوفيق! 🌟",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            elif booking['day'] == today:
                try:
                    app.bot.send_message(
                        chat_id=booking['user_id'],
                        text=f"⏰ *تذكير اليوم*\n\n"
                             f"عزيزي د.{booking['full_name']}\n"
                             f"لديك مناوبة اليوم\n\n"
                             f"نتمنى لك يوماً موفقاً! 🩺",
                        parse_mode='Markdown'
                    )
                except:
                    pass
    except:
        pass

def schedule_reminders(app):
    """جدولة التذكيرات"""
    def run_reminders():
        while True:
            now = datetime.now()
            if now.hour == 8 and now.minute == 0:  # الساعة 8 صباحاً
                check_and_send_reminders(app)
            threading.Event().wait(60)  # انتظر دقيقة
    
    thread = threading.Thread(target=run_reminders, daemon=True)
    thread.start()

# ==================== معالجات البوت الرئيسية ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /start"""
    user = update.effective_user
    user_id = user.id
    
    try:
        db.update_last_active(user_id)
    except:
        pass
    
    db_user = db.get_user(user_id)
    
    if db_user and db_user['approved'] == 1:
        welcome = f"🎉 *مرحباً بك د.{db_user['full_name']}*"
        if user_id == ADMIN_ID:
            welcome += "\n\n✨ *أنت المشرف* - لديك صلاحيات كاملة"
        
        await update.message.reply_text(
            welcome,
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(user_id)
        )
        
    elif db_user and db_user['approved'] == 0:
        await update.message.reply_text("⏳ *حسابك قيد المراجعة*\n\nسيتم إعلامك فور الموافقة.", parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "👋 *مرحباً بك في بوت المناوبات*\n\nللانضمام، أرسل اسمك الثلاثي:",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_name'] = True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل النصية"""
    user_id = update.effective_user.id
    text = update.message.text
    is_admin = (user_id == ADMIN_ID)
    
    # معالجة إدخال الاسم
    if context.user_data.get('awaiting_name'):
        full_name = text.strip()
        
        if len(full_name.split()) < 2:
            await update.message.reply_text("❌ الرجاء إرسال الاسم الثلاثي كاملاً")
            return
        
        db.add_user(user_id, full_name)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 *طلب موافقة جديد*\n\n👤 الاسم: {full_name}\n🆔 المعرف: {user_id}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ موافقة", callback_data=f"app_{user_id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"rej_{user_id}")
                ]
            ])
        )
        
        await update.message.reply_text("✅ *تم إرسال طلبك إلى المشرف*\n\nسيتم إعلامك فور الموافقة.", parse_mode='Markdown')
        context.user_data['awaiting_name'] = False
        return
    
    # التحقق من حالة المستخدم
    db_user = db.get_user(user_id)
    if not db_user or db_user['approved'] != 1:
        await update.message.reply_text("❌ ليس لديك صلاحية استخدام البوت")
        return
    
    # ==================== قائمة المستخدم ====================
    
    if text == "📅 حجز مناوبة":
        if not db.is_booking_open() and not is_admin:
            await update.message.reply_text("🔒 *الحجز مغلق حالياً*", parse_mode='Markdown')
            return
        
        keyboard, header = get_days_keyboard(user_id)
        if keyboard:
            await update.message.reply_text(header, parse_mode='Markdown', reply_markup=keyboard)
        else:
            await update.message.reply_text(header, parse_mode='Markdown')
    
    elif text == "📋 عرض الجدول":
        schedule = format_schedule()
        await update.message.reply_text(f"`{schedule}`", parse_mode='Markdown')
    
    elif text == "👤 ملفي الشخصي":
        month = db.get_current_month()
        bookings = db.get_user_bookings(user_id, month)
        booked_days = [b['day'] for b in bookings]
        
        info = f"👤 *الملف الشخصي*\n\n"
        info += f"📌 الاسم: د.{db_user['full_name']}\n"
        info += f"📊 الحد الأقصى: {db_user['max_days']} أيام\n"
        info += f"📅 المحجوز: {len(bookings)}\n"
        
        if booked_days:
            info += f"📍 أيامك: {', '.join(map(str, sorted(booked_days)))}"
            await update.message.reply_text(
                info,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🗑 حذف حجز", callback_data="show_delete")
                ]])
            )
        else:
            info += "⚠️ لا توجد حجوزات هذا الشهر"
            await update.message.reply_text(info, parse_mode='Markdown')
    
    elif text == "📚 كيفية الاستخدام":
        help_text = get_help_text(db_user)
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    # ==================== قائمة المشرف ====================
    
    elif text == "⚙️ لوحة المشرف" and is_admin:
        stats = db.get_month_statistics()
        await update.message.reply_text(
            f"🔧 *لوحة تحكم المشرف*\n\n"
            f"📊 إحصائيات سريعة:\n"
            f"• الأطباء: {stats['total_doctors']}\n"
            f"• حجوزات: {stats['booked_days']}/{stats['month_days']}\n"
            f"• الحجز: {'مفتوح' if db.is_booking_open() else 'مغلق'}\n\n"
            f"اختر ما تريد:",
            parse_mode='Markdown',
            reply_markup=get_admin_keyboard()
        )
    
    elif text == "🔙 العودة للقائمة الرئيسية":
        await update.message.reply_text("القائمة الرئيسية", reply_markup=get_main_keyboard(user_id))
    
    elif text == "👥 طلبات موافقة" and is_admin:
        pending = db.get_pending_users()
        if not pending:
            await update.message.reply_text("✅ لا توجد طلبات جديدة")
            return
        
        for p in pending:
            await update.message.reply_text(
                f"🔔 *طلب موافقة*\n\n👤 {p['full_name']}\n🆔 `{p['user_id']}`",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ موافقة", callback_data=f"app_{p['user_id']}"),
                        InlineKeyboardButton("❌ رفض", callback_data=f"rej_{p['user_id']}")
                    ]
                ])
            )
    
    elif text == "📋 قائمة الأطباء" and is_admin:
        users = db.get_approved_users()
        if not users:
            await update.message.reply_text("📭 لا يوجد أطباء مسجلين")
            return
        
        msg = "📋 *قائمة الأطباء*\n\n"
        for u in users:
            bookings = db.get_user_bookings(u['user_id'], db.get_current_month())
            msg += f"• د.{u['full_name']}: {len(bookings)}/{u['max_days']}\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    
    elif text == "🗑 حذف مستخدم" and is_admin:
        users = db.get_approved_users()
        keyboard = []
        for u in users:
            if u['user_id'] != ADMIN_ID:
                keyboard.append([InlineKeyboardButton(f"❌ د.{u['full_name']}", callback_data=f"deluser_{u['user_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 إلغاء", callback_data="cancel")])
        await update.message.reply_text("⚠️ *حذف مستخدم*\n\nاختر:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif text == "📊 إحصائيات" and is_admin:
        stats = db.get_month_statistics()
        msg = f"📊 *إحصائيات الشهر*\n\n"
        msg += f"📅 الشهر: {stats['month']}\n"
        msg += f"📆 أيام الشهر: {stats['month_days']}\n"
        msg += f"✅ محجوز: {stats['booked_days']}\n"
        msg += f"⬜ شاغر: {stats['free_days']}\n"
        msg += f"👥 الأطباء: {stats['total_doctors']}\n"
        msg += f"🔓 الحجز: {'مفتوح' if db.is_booking_open() else 'مغلق'}"
        await update.message.reply_text(msg, parse_mode='Markdown')
    
    elif text == "🔓 فتح الحجز" and is_admin:
        db.set_booking_open(True)
        await update.message.reply_text("✅ *تم فتح الحجز*", parse_mode='Markdown')
        
        # إشعار سريع
        users = db.get_approved_users()
        for u in users:
            if u['user_id'] != ADMIN_ID:
                try:
                    await context.bot.send_message(
                        chat_id=u['user_id'],
                        text="🔔 *تم فتح باب الحجز!*\n\nيمكنك الآن حجز مناوباتك.",
                        parse_mode='Markdown'
                    )
                except:
                    pass
    
    elif text == "🔒 غلق الحجز" and is_admin:
        db.set_booking_open(False)
        await update.message.reply_text("🔒 *تم غلق الحجز*", parse_mode='Markdown')
    
    elif text == "⏰ فتح مجدول" and is_admin:
        await update.message.reply_text(
            "⏰ *فتح الحجز بتاريخ محدد*\n\n"
            "أرسل التاريخ والوقت بهذه الصيغة:\n"
            "`YYYY/MM/DD HH:MM`\n\n"
            "مثال: `2026/03/15 09:00`\n"
            "(15 مارس 2026 الساعة 9 صباحاً)",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_full_datetime'] = True
    
    elif text == "📅 ضبط أيام الشهر" and is_admin:
        current = db.get_month_days()
        await update.message.reply_text(
            f"📅 *عدد أيام الشهر الحالي: {current}*\n\n"
            "أرسل الرقم الجديد (28-31):",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_month_days'] = True
    
    elif text == "📢 إشعار جماعي" and is_admin:
        await update.message.reply_text(
            "📢 *إرسال إشعار جماعي*\n\n"
            "أرسل الرسالة التي تريد إرسالها لجميع الأطباء:",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_broadcast'] = True
    
    elif text == "📥 تصدير الجدول" and is_admin:
        csv_data = export_to_csv()
        month = db.get_current_month()
        await update.message.reply_document(
            document=csv_data.encode('utf-8'),
            filename=f"mandoobat_{month}.csv",
            caption=f"📊 جدول مناوبات شهر {month}"
        )
    
    elif text == "➕ زيادة أيام" and is_admin:
        users = db.get_approved_users()
        keyboard = []
        for u in users:
            keyboard.append([InlineKeyboardButton(f"د.{u['full_name']} ({u['max_days']})", callback_data=f"inc_{u['user_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 إلغاء", callback_data="cancel")])
        await update.message.reply_text("اختر طبيباً:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif text == "➖ تقليل أيام" and is_admin:
        users = db.get_approved_users()
        keyboard = []
        for u in users:
            if u['max_days'] > 1:
                keyboard.append([InlineKeyboardButton(f"د.{u['full_name']} ({u['max_days']})", callback_data=f"dec_{u['user_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 إلغاء", callback_data="cancel")])
        await update.message.reply_text("اختر طبيباً:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif text == "🔄 بدء شهر جديد" and is_admin:
        month = db.get_current_month()
        await update.message.reply_text(
            f"⚠️ *بدء شهر جديد*\n\nسيتم حذف جميع حجوزات شهر {month}\nهل أنت متأكد؟",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ نعم", callback_data="reset_month"),
                 InlineKeyboardButton("❌ لا", callback_data="cancel")]
            ])
        )
    
    # ==================== معالجة الإدخالات الخاصة ====================
    
    elif context.user_data.get('awaiting_full_datetime') and is_admin:
        try:
            # دعم الصيغة YYYY/MM/DD HH:MM
            scheduled_time = datetime.strptime(text.strip(), "%Y/%m/%d %H:%M")
            now = datetime.now()
            
            if scheduled_time <= now:
                await update.message.reply_text(
                    f"❌ يجب أن يكون الوقت في المستقبل!\nالوقت الحالي: {now.strftime('%Y/%m/%d %H:%M')}"
                )
                return
            
            # حفظ الوقت
            db.set_scheduled_booking_time(scheduled_time.strftime("%Y/%m/%d %H:%M"))
            
            # حساب الوقت المتبقي
            diff = scheduled_time - now
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            
            await update.message.reply_text(
                f"✅ *تم جدولة فتح الحجز*\n\n"
                f"📅 التاريخ: {scheduled_time.strftime('%Y/%m/%d')}\n"
                f"⏰ الوقت: {scheduled_time.strftime('%H:%M')}\n"
                f"⏳ متبقي: {diff.days} يوم و {hours} ساعة",
                parse_mode='Markdown'
            )
            
            # إشعار للأطباء
            users = db.get_approved_users()
            count = 0
            for u in users:
                if u['user_id'] != ADMIN_ID:
                    try:
                        await context.bot.send_message(
                            chat_id=u['user_id'],
                            text=f"📅 *تم تحديد موعد فتح الحجز*\n\n"
                                 f"📆 {scheduled_time.strftime('%Y/%m/%d')}\n"
                                 f"⏰ {scheduled_time.strftime('%H:%M')}\n\n"
                                 f"🔔 سيتم فتح الحجز تلقائياً.",
                            parse_mode='Markdown'
                        )
                        count += 1
                    except:
                        pass
            
            await update.message.reply_text(f"📢 تم إشعار {count} طبيب")
            
            # إعداد المؤقت
            def open_booking():
                try:
                    db.set_booking_open(True)
                    # إشعار المشرف
                    context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text="✅ *تم فتح الحجز تلقائياً*",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            
            timer = threading.Timer(diff.total_seconds(), open_booking)
            timer.daemon = True
            timer.start()
            
            context.user_data['awaiting_full_datetime'] = False
            
        except ValueError:
            await update.message.reply_text(
                "❌ صيغة خاطئة!\n"
                "استخدم: `YYYY/MM/DD HH:MM`\n"
                "مثال: `2026/03/15 09:00`",
                parse_mode='Markdown'
            )
    
    elif context.user_data.get('awaiting_month_days') and is_admin:
        try:
            days = int(text.strip())
            if 28 <= days <= 31:
                db.set_month_days(days)
                await update.message.reply_text(f"✅ تم ضبط أيام الشهر إلى {days}")
                context.user_data['awaiting_month_days'] = False
            else:
                await update.message.reply_text("❌ الرجاء إدخال رقم بين 28 و 31")
        except ValueError:
            await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
    
    elif context.user_data.get('awaiting_broadcast') and is_admin:
        message = text.strip()
        users = db.get_approved_users()
        success = 0
        
        await update.message.reply_text("📤 جاري الإرسال...")
        
        for u in users:
            if u['user_id'] != ADMIN_ID:
                try:
                    await context.bot.send_message(
                        chat_id=u['user_id'],
                        text=f"📢 *رسالة من المشرف*\n\n{message}",
                        parse_mode='Markdown'
                    )
                    success += 1
                except:
                    pass
        
        await update.message.reply_text(f"✅ تم الإرسال لـ {success} طبيب")
        context.user_data['awaiting_broadcast'] = False

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    is_admin = (user_id == ADMIN_ID)
    
    # ==================== معالجة الموافقات ====================
    
    if data.startswith('app_') and is_admin:
        target = int(data.split('_')[1])
        if db.approve_user(target):
            await query.edit_message_text("✅ تمت الموافقة")
            try:
                await context.bot.send_message(
                    chat_id=target,
                    text="✅ *تمت الموافقة على طلبك!*\n\nيمكنك استخدام البوت الآن.",
                    parse_mode='Markdown',
                    reply_markup=get_main_keyboard(target)
                )
            except:
                pass
        else:
            await query.edit_message_text("❌ فشل الموافقة")
    
    elif data.startswith('rej_') and is_admin:
        target = int(data.split('_')[1])
        db.reject_user(target)
        await query.edit_message_text("❌ تم الرفض")
    
    # ==================== معالجة الحجوزات ====================
    
    elif data.startswith('book_'):
        day = int(data.split('_')[1])
        db_user = db.get_user(user_id)
        
        if not db_user or db_user['approved'] != 1:
            await query.edit_message_text("❌ ليس لديك صلاحية")
            return
        
        if not db.is_booking_open() and not is_admin:
            await query.edit_message_text("🔒 الحجز مغلق حالياً")
            return
        
        success, msg = db.book_day(user_id, day)
        await query.edit_message_text(msg)
        
        if success:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📌 *حجز جديد*\n\nد.{db_user['full_name']} حجز يوم {day}",
                parse_mode='Markdown'
            )
    
    # ==================== معالجة حذف الحجوزات ====================
    
    elif data.startswith('del_'):
        day = int(data.split('_')[1])
        if db.cancel_booking(day, db.get_current_month(), user_id):
            await query.edit_message_text(f"✅ تم حذف حجز يوم {day}")
        else:
            await query.edit_message_text("❌ فشل حذف الحجز")
    
    elif data == "show_delete":
        month = db.get_current_month()
        bookings = db.get_user_bookings(user_id, month)
        if not bookings:
            await query.edit_message_text("📭 لا توجد حجوزات")
            return
        
        keyboard = []
        for b in bookings:
            keyboard.append([InlineKeyboardButton(f"❌ حذف يوم {b['day']}", callback_data=f"del_{b['day']}")])
        keyboard.append([InlineKeyboardButton("🔙 إلغاء", callback_data="cancel")])
        await query.edit_message_text("🗑 *حذف حجز*\nاختر:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ==================== معالجة إدارة المستخدمين ====================
    
    elif data.startswith('deluser_') and is_admin:
        target = int(data.split('_')[1])
        db.delete_user(target)
        await query.edit_message_text("✅ تم حذف المستخدم")
    
    elif data.startswith('inc_') and is_admin:
        target = int(data.split('_')[1])
        user = db.get_user(target)
        if user:
            db.update_user_max_days(target, user['max_days'] + 1)
            await query.edit_message_text(f"✅ تمت الزيادة إلى {user['max_days'] + 1}")
    
    elif data.startswith('dec_') and is_admin:
        target = int(data.split('_')[1])
        user = db.get_user(target)
        if user and user['max_days'] > 1:
            db.update_user_max_days(target, user['max_days'] - 1)
            await query.edit_message_text(f"✅ تم التقليل إلى {user['max_days'] - 1}")
    
    # ==================== معالجة الإعدادات ====================
    
    elif data == "reset_month" and is_admin:
        db.reset_month()
        await query.edit_message_text("✅ تم تصفير الشهر")
    
    elif data == "cancel":
        await query.edit_message_text("✅ تم الإلغاء")
    
    elif data == "cancel_booking":
        await query.edit_message_text("✅ تم إلغاء عملية الحجز")

# ==================== تشغيل البوت ====================

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    print("=" * 50)
    print("🤖 بوت إدارة المناوبات - النسخة النهائية")
    print("=" * 50)
    print(f"📱 معرف المشرف: {ADMIN_ID}")
    print("=" * 50)
    print("🚀 جاري تشغيل البوت...")
    
    try:
        app = Application.builder().token(BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(CallbackQueryHandler(button_handler))
        
        # تشغيل التذكيرات في خيط منفصل
        schedule_reminders(app)
        
        print("✅ البوت يعمل بنجاح!")
        print("=" * 50)
        print("📌 الميزات:")
        print("  ✓ جدولة فتح الحجز (YYYY/MM/DD HH:MM)")
        print("  ✓ تذكير قبل 24 ساعة")
        print("  ✓ تذكير يوم المناوبة")
        print("  ✓ إشعارات جماعية")
        print("  ✓ تصدير CSV")
        print("  ✓ واجهة عربية جميلة")
        print("=" * 50)
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"❌ خطأ: {e}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 تم إيقاف البوت")