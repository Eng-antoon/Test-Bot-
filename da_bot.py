# da_bot.py
import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler, CallbackContext
import db
import config

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(SUBSCRIPTION_PHONE, MAIN_MENU, NEW_ISSUE_CLIENT, NEW_ISSUE_ORDER,
 NEW_ISSUE_DESCRIPTION, NEW_ISSUE_TYPE, ASK_IMAGE, WAIT_IMAGE, AWAITING_DA_RESPONSE) = range(9)

CLIENT_OPTIONS = [['بوبا', 'بتلكو', 'بيبس']]
MAIN_MENU_OPTIONS = [['استعلام عن مشكلة', 'إضافة مشكلة']]
ISSUE_TYPE_OPTIONS = [['توزيع طلبات', 'خطأ في المستند', 'خطأ في التاكيد',
                       'سب المستلم', 'شركة التوصيل', 'اسم السائق',
                       'مشكلة السكن', 'ملاحظات عامة', 'ارسال حوالة بنكية'],
                      ['أخرى...']]

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    sub = db.get_subscription(user.id, "DA")
    if not sub:
        update.message.reply_text("أهلاً! يرجى إدخال رقم هاتفك للاشتراك (DA):")
        return SUBSCRIPTION_PHONE
    else:
        reply_markup = ReplyKeyboardMarkup(MAIN_MENU_OPTIONS, resize_keyboard=True)
        update.message.reply_text(f"مرحباً {user.first_name}, اختر خياراً:", reply_markup=reply_markup)
        return MAIN_MENU

def subscription_phone(update: Update, context: CallbackContext):
    phone = update.message.text.strip()
    user = update.effective_user
    db.add_subscription(user.id, phone, 'DA', "DA", None, user.username, user.first_name, user.last_name, update.effective_chat.id)
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_OPTIONS, resize_keyboard=True)
    update.message.reply_text("تم الاشتراك بنجاح كـ DA!", reply_markup=reply_markup)
    return MAIN_MENU

def main_menu(update: Update, context: CallbackContext):
    choice = update.message.text.strip()
    if choice == 'إضافة مشكلة':
        reply_markup = ReplyKeyboardMarkup(CLIENT_OPTIONS, resize_keyboard=True)
        update.message.reply_text("اختر العميل (أو اكتب اسم العميل):", reply_markup=reply_markup)
        return NEW_ISSUE_CLIENT
    elif choice == 'استعلام عن مشكلة':
        update.message.reply_text("يرجى إدخال رقم الطلب:")
        return NEW_ISSUE_ORDER
    else:
        update.message.reply_text("الخيار غير معروف. الرجاء اختيار خيار من القائمة.")
        return MAIN_MENU

def new_issue_client(update: Update, context: CallbackContext):
    client_selected = update.message.text.strip()
    context.user_data['client'] = client_selected
    update.message.reply_text("أدخل رقم الطلب (مثال: ANR-123):")
    return NEW_ISSUE_ORDER

def new_issue_order(update: Update, context: CallbackContext):
    order_id = update.message.text.strip()
    context.user_data['order_id'] = order_id
    update.message.reply_text("صف المشكلة التي تواجهها:")
    return NEW_ISSUE_DESCRIPTION

def new_issue_description(update: Update, context: CallbackContext):
    description = update.message.text.strip()
    context.user_data['description'] = description
    reply_markup = ReplyKeyboardMarkup(ISSUE_TYPE_OPTIONS, resize_keyboard=True)
    update.message.reply_text("اختر نوع المشكلة أو اكتب نوعها:", reply_markup=reply_markup)
    return NEW_ISSUE_TYPE

def new_issue_type(update: Update, context: CallbackContext):
    issue_type = update.message.text.strip()
    context.user_data['issue_type'] = issue_type
    reply_markup = ReplyKeyboardMarkup([['نعم', 'لا']], resize_keyboard=True)
    update.message.reply_text("هل تريد إرفاق صورة للمشكلة؟", reply_markup=reply_markup)
    return ASK_IMAGE

def ask_image(update: Update, context: CallbackContext):
    choice = update.message.text.strip()
    if choice == 'نعم':
        update.message.reply_text("يرجى إرسال الصورة:")
        return WAIT_IMAGE
    else:
        return finalize_ticket(update, context, image_url=None)

def wait_image(update: Update, context: CallbackContext):
    if update.message.photo:
        photo_file = update.message.photo[-1].file_id
        image_url = photo_file
        return finalize_ticket(update, context, image_url=image_url)
    else:
        update.message.reply_text("لم يتم إرسال صورة صحيحة. الرجاء إعادة الإرسال:")
        return WAIT_IMAGE

def finalize_ticket(update: Update, context: CallbackContext, image_url):
    user = update.effective_user
    data = context.user_data
    order_id = data.get('order_id')
    description = data.get('description')
    issue_type = data.get('issue_type')
    client_selected = data.get('client', 'غير محدد')
    ticket_id = db.add_ticket(order_id, description, issue_type, client_selected, image_url, "Opened", user.id)
    update.message.reply_text(f"تم إنشاء التذكرة برقم {ticket_id}.")
    notify_supervisors(ticket_id, user)
    context.user_data.clear()
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_OPTIONS, resize_keyboard=True)
    update.message.reply_text("اختر خياراً:", reply_markup=reply_markup)
    return MAIN_MENU

def notify_supervisors(ticket_id, da_user):
    ticket = db.get_ticket(ticket_id)
    supervisors = db.get_supervisors()
    message = (f"تذكرة جديدة من {da_user.first_name} (ID: {da_user.id})\n"
               f"رقم الطلب: {ticket['order_id']}\nالعميل: {ticket['client']}\nالحالة: {ticket['status']}")
    keyboard = [[InlineKeyboardButton("عرض التفاصيل", callback_data=f"view_{ticket_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot = Bot(token=config.SUPERVISOR_BOT_TOKEN)
    for sup in supervisors:
        try:
            bot.send_message(chat_id=sup['chat_id'], text=message, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error notifying supervisor {sup['chat_id']}: {e}")

# Handler for callbacks directed to the DA (from Supervisor)
def da_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    if data.startswith("close_"):
        ticket_id = int(data.split("_")[1])
        db.update_ticket_status(ticket_id, "Closed", {"action": "da_closed"})
        query.edit_message_text(text="تم إغلاق التذكرة بنجاح.")
        bot_sup = Bot(token=config.SUPERVISOR_BOT_TOKEN)
        for sup in db.get_supervisors():
            try:
                bot_sup.send_message(chat_id=sup['chat_id'], text=f"التذكرة #{ticket_id} تم إغلاقها من قبل الوكيل.")
            except Exception as e:
                logger.error(f"Error notifying supervisor of closure: {e}")
    elif data.startswith("da_moreinfo_"):
        ticket_id = int(data.split("_")[2])
        context.user_data['ticket_id'] = ticket_id
        # Instead of editing the inline message with ForceReply, send a new message.
        context.bot.send_message(chat_id=query.message.chat_id, text="أدخل المعلومات الإضافية المطلوبة:", reply_markup=ForceReply(selective=True))
        return AWAITING_DA_RESPONSE
    else:
        query.edit_message_text(text="الإجراء غير معروف.")

def da_awaiting_response_handler(update: Update, context: CallbackContext):
    additional_info = update.message.text.strip()
    ticket_id = context.user_data.get('ticket_id')
    db.update_ticket_status(ticket_id, "Additional Info Provided", {"action": "da_moreinfo", "message": additional_info})
    update.message.reply_text("تم إرسال المعلومات الإضافية إلى المشرف.")
    bot_sup = Bot(token=config.SUPERVISOR_BOT_TOKEN)
    for sup in db.get_supervisors():
        try:
            bot_sup.send_message(chat_id=sup['chat_id'], text=f"تم إرسال معلومات إضافية للتذكرة #{ticket_id}:\n{additional_info}")
        except Exception as e:
            logger.error(f"Error notifying supervisors: {e}")
    context.user_data.pop('ticket_id', None)
    return MAIN_MENU

def main():
    updater = Updater(config.DA_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SUBSCRIPTION_PHONE: [MessageHandler(Filters.text & ~Filters.command, subscription_phone)],
            MAIN_MENU: [MessageHandler(Filters.text & ~Filters.command, main_menu)],
            NEW_ISSUE_CLIENT: [MessageHandler(Filters.text & ~Filters.command, new_issue_client)],
            NEW_ISSUE_ORDER: [MessageHandler(Filters.text & ~Filters.command, new_issue_order)],
            NEW_ISSUE_DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, new_issue_description)],
            NEW_ISSUE_TYPE: [MessageHandler(Filters.text & ~Filters.command, new_issue_type)],
            ASK_IMAGE: [MessageHandler(Filters.text & ~Filters.command, ask_image)],
            WAIT_IMAGE: [MessageHandler(Filters.photo, wait_image)],
            AWAITING_DA_RESPONSE: [MessageHandler(Filters.text & ~Filters.command, da_awaiting_response_handler)]
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: u.message.reply_text("تم إلغاء العملية."))]
    )
    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(da_callback_handler, pattern="^(close_|da_moreinfo_).*"))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
