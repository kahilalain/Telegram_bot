import logging
import datetime
import time

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ================== الإعدادات ==================

BOT_TOKEN = "8098575885:AAGXwJS31qqSHfDv196wKA0zxVpNpyz1imo"
CHANNEL_ID = "-1003503649640"

VALID_MEMBERSHIP_CODE = "CS2025"

MAX_FILE_MB = 30
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "png", "jpg", "jpeg", "zip", "rar"}
MIN_SECONDS_BETWEEN_SUBMISSIONS = 10 

# حالة واحدة رئيسية لجمع البيانات
COLLECTING_DATA = 1

# ================== Logging ==================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ================== دوال مساعدة ==================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception", exc_info=context.error)

def parse_student_details(text):
    """تحليل النص واستخراج البيانات"""
    if not text:
        return None
        
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # يجب أن يكون هناك 4 أسطر على الأقل
    if len(lines) < 4:
        return {"valid": False, "error": "missing_lines"}

    # التحقق من كود العضوية
    membership_code = lines[3]
    
    if membership_code != VALID_MEMBERSHIP_CODE:
        return {"valid": False, "error": "invalid_code"}

    return {
        "valid": True,
        "name": lines[0],
        "course": lines[1],
        "title": lines[2],
        "membership_code": membership_code,
        "desc": lines[4] if len(lines) >= 5 else "—"
    }

async def send_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال البيانات المكتملة إلى القناة"""
    data = context.user_data
    details = data.get("details")
    file_info = data.get("file")

    submission_time = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

    caption = (
        "📥 **تكليف جديد**\n\n"
        f"👤 **الاسم:** {details['name']}\n"
        f"🆔 **المقرر:** {details['course']}\n"
        f"🎓 **العضوية:** {details['membership_code']}\n"
        f"📚 **العنوان:** {details['title']}\n"
        f"📝 **الوصف:** {details['desc']}\n"
        f"🕒 **الوقت:** {submission_time}"
    )

    try:
        # إزالة parse_mode لضمان قبول جميع الرموز والأسماء
        if file_info['type'] == 'document':
            await context.bot.send_document(
                chat_id=CHANNEL_ID,
                document=file_info['id'],
                caption=caption
            )
        else:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=file_info['id'],
                caption=caption
            )
            
        await update.message.reply_text(
            "✅ **تم تسليم التكليف بنجاح!**\n\n"
            "يمكنك البدء من جديد عبر /start",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Failed to send: {e}")
        await update.message.reply_text("❌ فشل الإرسال للقناة. تأكد من صلاحيات البوت وأعد المحاولة.")
        return COLLECTING_DATA

# ================== الهاندلرز (Handlers) ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بداية المحادثة أو إعادة التشغيل"""
    context.user_data.clear()
    
    welcome_text = (
        "👋 **مرحبًا بك في بوت تسليم التكاليف**\n\n"
        "أنا جاهز لاستلام بياناتك بأي ترتيب تفضله.\n"
        "يمكنك إرسال:\n"
        "📄 **البيانات النصية** (الاسم، المقرر، العنوان، الكود، الوصف).\n"
        "📎 **ملف التكليف** (صورة أو ملف).\n"
        "أو كلاهما معاً في رسالة واحدة.\n\n"
        "⚠️ **تنسيق النص المطلوب (كل بيان في سطر):**\n"
        "1. اسم الطالب\n2. المقرر\n3. عنوان التكليف\n4. كود العضوية (CS2025)\n5. وصف (اختياري)"
    )
    
    await update.message.reply_text(welcome_text)
    return COLLECTING_DATA

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ذكية لكل المدخلات (نص أو ملف)"""
    msg = update.message
    
    # 1. استخراج النص (سواء كان رسالة نصية أو شرح لملف caption)
    text_content = msg.text or msg.caption
    
    # 2. استخراج الملف
    document = msg.document
    photo = msg.photo[-1] if msg.photo else None
    
    new_info_added = False

    # --- معالجة الملف ---
    if document or photo:
        file_obj = document or photo
        file_size = file_obj.file_size
        
        if document:
            ext = document.file_name.split(".")[-1].lower() if document.file_name else ""
            if ext not in ALLOWED_EXTENSIONS:
                await msg.reply_text(f"❌ نوع الملف غير مدعوم ({ext}). الامتدادات المسموحة: {', '.join(ALLOWED_EXTENSIONS)}")
                return COLLECTING_DATA
        
        if file_size > MAX_FILE_MB * 1024 * 1024:
            await msg.reply_text(f"❌ حجم الملف كبير جداً. الحد الأقصى {MAX_FILE_MB} ميجابايت.")
            return COLLECTING_DATA

        context.user_data['file'] = {
            'id': file_obj.file_id,
            'type': 'document' if document else 'photo'
        }
        new_info_added = True
        # تم إزالة quote=True من هنا
        await msg.reply_text("📎 تم استلام الملف.")

    # --- معالجة النص ---
    if text_content:
        parsed = parse_student_details(text_content)
        
        if parsed and parsed['valid']:
            context.user_data['details'] = parsed
            new_info_added = True
            # تم إزالة quote=True من هنا
            await msg.reply_text(f"✅ تم استلام بيانات الطالب: {parsed['name']}")
        elif parsed and not parsed['valid']:
            if not (document or photo):
                if parsed['error'] == 'invalid_code':
                    await msg.reply_text("❌ كود العضوية غير صحيح. يرجى التأكد وإعادة إرسال البيانات.")
                else:
                    await msg.reply_text("⚠️ البيانات النصية غير مكتملة (تأكد من إرسال 4 أسطر على الأقل). حاول مرة أخرى.")

    if not new_info_added:
         await msg.reply_text("⚠️ لم أتمكن من فهم الرسالة. يرجى إرسال بيانات نصية صحيحة أو ملف.")
         return COLLECTING_DATA

    # --- التحقق من الاكتمال ---
    has_details = 'details' in context.user_data
    has_file = 'file' in context.user_data

    if has_details and has_file:
        await msg.reply_text("🔄 جاري تسليم التكليف...")
        return await send_to_channel(update, context)
    
    elif has_details and not has_file:
        await msg.reply_text("⏳ البيانات جاهزة. **بانتظار إرسال ملف التكليف...**")
        
    elif has_file and not has_details:
        await msg.reply_text("⏳ الملف جاهز. **بانتظار إرسال بيانات الطالب النصية...**")

    return COLLECTING_DATA

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("⛔ تم إلغاء العملية. اضغط /start للبدء من جديد.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ================== التشغيل ==================

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_error_handler(error_handler)

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            COLLECTING_DATA: [
                MessageHandler(
                    filters.TEXT | filters.Document.ALL | filters.PHOTO, 
                    handle_input
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True 
    )

    app.add_handler(conv)

    print("🤖 Bot is running with Enhanced Logic...")
    app.run_polling()


if __name__ == "__main__":
    main()