#!/usr/bin/env python3
# da_bot.py
import logging
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler, CallbackContext
import db
import config

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states (0 to 11)
(SUBSCRIPTION_PHONE, MAIN_MENU, NEW_ISSUE_CLIENT, NEW_ISSUE_ORDER,
 NEW_ISSUE_DESCRIPTION, NEW_ISSUE_REASON, NEW_ISSUE_TYPE, ASK_IMAGE, WAIT_IMAGE, AWAITING_DA_RESPONSE,
 EDIT_PROMPT, EDIT_FIELD) = range(12)

# Mapping of issue reasons to available types.
ISSUE_OPTIONS = {
    "المخزن": ["تالف", "منتهي الصلاحية", "عجز في المخزون", "تحضير خاطئ"],
    "المورد": ["خطا بالمستندات", "رصيد غير موجود", "اوردر خاطئ", "اوردر بكميه اكبر",
               "خطا فى الباركود او اسم الصنف", "اوردر وهمى", "خطأ فى الاسعار",
               "تخطى وقت الانتظار لدى العميل", "اختلاف بيانات الفاتورة", "توالف مصنع"],
    "العميل": ["رفض الاستلام", "مغلق", "عطل بالسيستم", "لا يوجد مساحة للتخزين", "شك عميل فى سلامة العبوه"],
    "التسليم": ["وصول متاخر", "تالف", "عطل بالسياره"]
}

# --------------------------
# Basic flow functions
# --------------------------

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    sub = db.get_subscription(user.id, "DA")
    if not sub:
        update.message.reply_text("أهلاً! يرجى إدخال رقم هاتفك للاشتراك (DA):")
        return SUBSCRIPTION_PHONE
    else:
        keyboard = [[InlineKeyboardButton("إضافة مشكلة", callback_data="menu_add_issue"),
                     InlineKeyboardButton("استعلام عن مشكلة", callback_data="menu_query_issue")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(f"مرحباً {user.first_name}", reply_markup=reply_markup)
        return MAIN_MENU

def subscription_phone(update: Update, context: CallbackContext):
    phone = update.message.text.strip()
    user = update.effective_user
    db.add_subscription(user.id, phone, 'DA', "DA", None,
                        user.username, user.first_name, user.last_name, update.effective_chat.id)
    keyboard = [[InlineKeyboardButton("إضافة مشكلة", callback_data="menu_add_issue"),
                 InlineKeyboardButton("استعلام عن مشكلة", callback_data="menu_query_issue")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("تم الاشتراك بنجاح كـ DA!", reply_markup=reply_markup)
    return MAIN_MENU

def da_main_menu_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    if data == "menu_add_issue":
        keyboard = [[InlineKeyboardButton("بوبا", callback_data="client_option_بوبا"),
                     InlineKeyboardButton("بتلكو", callback_data="client_option_بتلكو"),
                     InlineKeyboardButton("بيبس", callback_data="client_option_بيبس")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("اختر العميل:", reply_markup=reply_markup)
        return NEW_ISSUE_CLIENT
    elif data == "menu_query_issue":
        user = query.from_user
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        tickets = [t for t in db.get_all_tickets() if t['da_id'] == user.id and t['created_at'].startswith(today_str)]
        if tickets:
            # Show full details with status (translated) and resolution if closed.
            status_mapping = {
                "Opened": "مفتوحة",
                "Pending DA Action": "في انتظار إجراء الوكيل",
                "Awaiting Client Response": "في انتظار رد العميل",
                "Client Responded": "تم رد العميل",
                "Client Ignored": "تم تجاهل العميل",
                "Closed": "مغلقة",
                "Additional Info Provided": "تم توفير معلومات إضافية",
                "Pending DA Response": "في انتظار رد الوكيل"
            }
            for ticket in tickets:
                status_ar = status_mapping.get(ticket['status'], ticket['status'])
                resolution = ""
                if ticket['status'] == "Closed":
                    resolution = "\nالحل: تم الحل."
                text = (f"<b>تذكرة #{ticket['ticket_id']}</b>\n"
                        f"رقم الطلب: {ticket['order_id']}\n"
                        f"الوصف: {ticket['issue_description']}\n"
                        f"سبب المشكلة: {ticket['issue_reason']}\n"
                        f"نوع المشكلة: {ticket['issue_type']}\n"
                        f"الحالة: {status_ar}{resolution}")
                query.message.reply_text(text, parse_mode="HTML")
        else:
            query.edit_message_text("لا توجد تذاكر اليوم.")
        return MAIN_MENU
    elif data.startswith("client_option_"):
        client_selected = data.split("_", 2)[2]
        context.user_data['client'] = client_selected
        query.edit_message_text(f"تم اختيار العميل: {client_selected}\nأدخل رقم الطلب (مثال: ANR-123):")
        return NEW_ISSUE_ORDER
    elif data.startswith("issue_reason_"):
        reason = data.split("_", 2)[2]
        context.user_data['issue_reason'] = reason
        types = ISSUE_OPTIONS.get(reason, [])
        keyboard = [[InlineKeyboardButton(t, callback_data=f"issue_type_{t}")] for t in types]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("اختر نوع المشكلة:", reply_markup=reply_markup)
        return NEW_ISSUE_TYPE
    elif data.startswith("issue_type_"):
        issue_type = data.split("_", 2)[2]
        context.user_data['issue_type'] = issue_type
        keyboard = [[InlineKeyboardButton("نعم", callback_data="attach_yes"),
                     InlineKeyboardButton("لا", callback_data="attach_no")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("هل تريد إرفاق صورة للمشكلة؟", reply_markup=reply_markup)
        return ASK_IMAGE
    elif data in ["attach_yes", "attach_no"]:
        if data == "attach_yes":
            query.edit_message_text("يرجى إرسال الصورة:")
            return WAIT_IMAGE
        else:
            return show_ticket_summary_for_edit(query, context)
    elif data.startswith("edit_ticket_") or data.startswith("edit_field_"):
        return edit_ticket_prompt_callback(update, context)
    else:
        query.edit_message_text("الخيار غير معروف.")
        return MAIN_MENU

def new_issue_order(update: Update, context: CallbackContext):
    order_id = update.message.text.strip()
    context.user_data['order_id'] = order_id
    update.message.reply_text("صف المشكلة التي تواجهها:")
    return NEW_ISSUE_DESCRIPTION

def new_issue_description(update: Update, context: CallbackContext):
    description = update.message.text.strip()
    context.user_data['description'] = description
    keyboard = [
        [InlineKeyboardButton("المخزن", callback_data="issue_reason_المخزن"),
         InlineKeyboardButton("المورد", callback_data="issue_reason_المورد")],
        [InlineKeyboardButton("العميل", callback_data="issue_reason_العميل"),
         InlineKeyboardButton("التسليم", callback_data="issue_reason_التسليم")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("اختر سبب المشكلة:", reply_markup=reply_markup)
    return NEW_ISSUE_REASON

def wait_image(update: Update, context: CallbackContext):
    if update.message.photo:
        photo_file = update.message.photo[-1].file_id
        context.user_data['image'] = photo_file
        return show_ticket_summary_for_edit(update.message, context)
    else:
        update.message.reply_text("لم يتم إرسال صورة صحيحة. أعد الإرسال:")
        return WAIT_IMAGE

def show_ticket_summary_for_edit(source, context):
    # source can be a Message or CallbackQuery.
    msg_func = source.edit_message_text if hasattr(source, 'edit_message_text') else context.bot.send_message
    data = context.user_data
    summary = (f"رقم الطلب: {data.get('order_id','')}\n"
               f"الوصف: {data.get('description','')}\n"
               f"سبب المشكلة: {data.get('issue_reason','')}\n"
               f"نوع المشكلة: {data.get('issue_type','')}\n"
               f"العميل: {data.get('client','')}\n"
               f"الصورة: {data.get('image', 'لا توجد')}")
    text = "ملخص التذكرة المدخلة:\n" + summary + "\nهل تريد تعديل التذكرة قبل الإرسال؟"
    keyboard = [[InlineKeyboardButton("نعم", callback_data="edit_ticket_yes"),
                 InlineKeyboardButton("لا", callback_data="edit_ticket_no")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_func(text=text, reply_markup=reply_markup)
    return EDIT_PROMPT

def edit_ticket_prompt_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    if data == "edit_ticket_no":
        return finalize_ticket_da(query, context, image_url=context.user_data.get('image', None))
    elif data == "edit_ticket_yes":
        keyboard = [
            [InlineKeyboardButton("رقم الطلب", callback_data="edit_field_order"),
             InlineKeyboardButton("الوصف", callback_data="edit_field_description")],
            [InlineKeyboardButton("سبب المشكلة", callback_data="edit_field_issue_reason"),
             InlineKeyboardButton("نوع المشكلة", callback_data="edit_field_issue_type")],
            [InlineKeyboardButton("العميل", callback_data="edit_field_client"),
             InlineKeyboardButton("الصورة", callback_data="edit_field_image")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("اختر الحقل الذي تريد تعديله:", reply_markup=reply_markup)
        return EDIT_FIELD
    else:
        keyboard = [[InlineKeyboardButton("نعم", callback_data="edit_ticket_yes"),
                     InlineKeyboardButton("لا", callback_data="edit_ticket_no")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("هل تريد تعديل التذكرة قبل الإرسال؟", reply_markup=reply_markup)
        return EDIT_PROMPT

def edit_field_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    field = query.data  # e.g., "edit_field_order"
    context.user_data['edit_field'] = field
    if field == "edit_field_issue_reason":
        keyboard = [
            [InlineKeyboardButton("المخزن", callback_data="issue_reason_المخزن"),
             InlineKeyboardButton("المورد", callback_data="issue_reason_المورد")],
            [InlineKeyboardButton("العميل", callback_data="issue_reason_العميل"),
             InlineKeyboardButton("التسليم", callback_data="issue_reason_التسليم")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("اختر سبب المشكلة الجديد:", reply_markup=reply_markup)
        return EDIT_FIELD
    elif field == "edit_field_issue_type":
        current_reason = context.user_data.get('issue_reason', '')
        types = ISSUE_OPTIONS.get(current_reason, [])
        if not types:
            query.edit_message_text("لا توجد خيارات متاحة لنوع المشكلة.")
            return EDIT_PROMPT
        keyboard = [[InlineKeyboardButton(t, callback_data="edit_field_issue_type_" + t)] for t in types]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("اختر نوع المشكلة الجديد:", reply_markup=reply_markup)
        return EDIT_FIELD
    elif field == "edit_field_client":
        keyboard = [[InlineKeyboardButton("بوبا", callback_data="edit_field_client_بوبا"),
                     InlineKeyboardButton("بتلكو", callback_data="edit_field_client_بتلكو"),
                     InlineKeyboardButton("بيبس", callback_data="edit_field_client_بيبس")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("اختر العميل الجديد:", reply_markup=reply_markup)
        return EDIT_FIELD
    else:
        field_name = field.split('_')[-1]
        query.edit_message_text(f"أدخل القيمة الجديدة لـ {field_name}:")
        return EDIT_FIELD

def edit_field_input_handler(update: Update, context: CallbackContext):
    if 'edit_field' in context.user_data:
        field = context.user_data['edit_field']
        if field.startswith("edit_field_issue_type_"):
            new_value = field.split('_', 3)[-1]
            context.user_data['issue_type'] = new_value
            log_entry = {"action": "edit_field", "field": "نوع المشكلة", "new_value": new_value}
        elif field.startswith("edit_field_client_"):
            new_value = field.split('_', 3)[-1]
            context.user_data['client'] = new_value
            log_entry = {"action": "edit_field", "field": "العميل", "new_value": new_value}
        else:
            new_value = update.message.text.strip()
            field_name = field.split('_')[-1]
            if field == "edit_field_order":
                context.user_data['order_id'] = new_value
            elif field == "edit_field_description":
                context.user_data['description'] = new_value
            elif field == "edit_field_image":
                context.user_data['image'] = new_value
            elif field == "edit_field_issue_reason":
                context.user_data['issue_reason'] = new_value
            log_entry = {"action": "edit_field", "field": field_name, "new_value": new_value}
        context.user_data.setdefault('edit_log', []).append(log_entry)
        update.message.reply_text(f"تم تعديل {field.split('_')[-1]} إلى: {new_value}")
        keyboard = [[InlineKeyboardButton("نعم", callback_data="edit_ticket_yes"),
                     InlineKeyboardButton("لا", callback_data="edit_ticket_no")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("هل تريد تعديل التذكرة مرة أخرى؟", reply_markup=reply_markup)
        return EDIT_PROMPT
    else:
        update.message.reply_text("حدث خطأ أثناء التعديل.")
        return EDIT_PROMPT

# --- MISSING FUNCTION DEFINITION ---
def notify_supervisors(ticket_id, da_user):
    """
    Notifies all supervisors about the new ticket.
    """
    ticket = db.get_ticket(ticket_id)
    supervisors = db.get_supervisors()
    message = (
        f"<b>تذكرة جديدة من {da_user.first_name} (ID: {da_user.id})</b>\n"
        f"رقم الطلب: {ticket['order_id']}\n"
        f"العميل: {ticket['client']}\n"
        f"الوصف: {ticket['issue_description']}\n"
        f"سبب المشكلة: {ticket['issue_reason']}\n"
        f"نوع المشكلة: {ticket['issue_type']}\n"
        f"الحالة: {ticket['status']}"
    )
    keyboard = [[InlineKeyboardButton("عرض التفاصيل", callback_data=f"view_{ticket_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot = Bot(token=config.SUPERVISOR_BOT_TOKEN)
    for sup in supervisors:
        try:
            bot.send_message(chat_id=sup['chat_id'], text=message, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error notifying supervisor {sup['chat_id']}: {e}")

# --------------------------
# Finalization and additional flows
# --------------------------

def finalize_ticket_da(source, context, image_url):
    if hasattr(source, 'from_user'):
        user = source.from_user
    else:
        user = source.message.from_user
    data = context.user_data
    order_id = data.get('order_id')
    description = data.get('description')
    issue_reason = data.get('issue_reason')
    issue_type = data.get('issue_type')
    client_selected = data.get('client', 'غير محدد')
    ticket_id = db.add_ticket(order_id, description, issue_reason, issue_type, client_selected, image_url, "Opened", user.id)
    if hasattr(source, 'edit_message_text'):
        source.edit_message_text(f"تم إنشاء التذكرة برقم {ticket_id}.\nالحالة: Opened")
    else:
        context.bot.send_message(chat_id=user.id, text=f"تم إنشاء التذكرة برقم {ticket_id}.\nالحالة: Opened")
    if 'edit_log' in context.user_data:
        for log_entry in context.user_data['edit_log']:
            db.update_ticket_status(ticket_id, "Opened", log_entry)
    notify_supervisors(ticket_id, user)
    context.user_data.clear()
    return MAIN_MENU

def da_awaiting_response_handler(update: Update, context: CallbackContext):
    additional_info = update.message.text.strip()
    ticket_id = context.user_data.get('ticket_id')
    if not ticket_id:
        update.message.reply_text("حدث خطأ. أعد المحاولة.")
        return MAIN_MENU
    db.update_ticket_status(ticket_id, "Additional Info Provided", {"action": "da_moreinfo", "message": additional_info})
    ticket = db.get_ticket(ticket_id)
    text = (f"<b>تحديث للتذكرة #{ticket_id}</b>\n"
            f"رقم الطلب: {ticket['order_id']}\n"
            f"الوصف: {ticket['issue_description']}\n"
            f"سبب المشكلة: {ticket['issue_reason']}\n"
            f"نوع المشكلة: {ticket['issue_type']}\n"
            f"الحالة: {ticket['status']}\n\n"
            f"المعلومات الإضافية: {additional_info}\n\n"
            "يمكن للمشرف الآن عرض التفاصيل واتخاذ الإجراء المناسب.")
    keyboard = [[InlineKeyboardButton("عرض التفاصيل", callback_data=f"view_{ticket_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("تم إرسال المعلومات الإضافية إلى المشرف.")
    bot_sup = Bot(token=config.SUPERVISOR_BOT_TOKEN)
    for sup in db.get_supervisors():
        try:
            bot_sup.send_message(chat_id=sup['chat_id'], text=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error notifying supervisors: {e}")
    context.user_data.pop('ticket_id', None)
    return MAIN_MENU

def da_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    if data.startswith("close_"):
        ticket_id = int(data.split("_")[1])
        db.update_ticket_status(ticket_id, "Closed", {"action": "da_closed"})
        query.edit_message_text("تم إغلاق التذكرة بنجاح.")
        bot_sup = Bot(token=config.SUPERVISOR_BOT_TOKEN)
        for sup in db.get_supervisors():
            try:
                bot_sup.send_message(chat_id=sup['chat_id'],
                                     text=f"التذكرة #{ticket_id} تم إغلاقها من قبل الوكيل.",
                                     parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error notifying supervisor of closure: {e}")
        return MAIN_MENU
    elif data.startswith("da_moreinfo_"):
        parts = data.split("_", 2)
        try:
            ticket_id = int(parts[2])
        except (IndexError, ValueError):
            query.edit_message_text("خطأ في بيانات التذكرة.")
            return MAIN_MENU
        context.user_data['ticket_id'] = ticket_id
        ticket = db.get_ticket(ticket_id)
        text = (f"<b>التذكرة #{ticket_id}</b>\n"
                f"رقم الطلب: {ticket['order_id']}\n"
                f"الوصف: {ticket['issue_description']}\n"
                f"الحالة: {ticket['status']}\n\n"
                "أدخل المعلومات الإضافية المطلوبة للتذكرة:")
        context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=ForceReply(selective=True), parse_mode="HTML")
        return AWAITING_DA_RESPONSE
    else:
        query.edit_message_text("الإجراء غير معروف.")
        return MAIN_MENU

def default_handler_da(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("إضافة مشكلة", callback_data="menu_add_issue"),
                 InlineKeyboardButton("استعلام عن مشكلة", callback_data="menu_query_issue")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("الرجاء اختيار خيار:", reply_markup=reply_markup)
    return MAIN_MENU

def default_handler_da_edit(update: Update, context: CallbackContext):
    update.message.reply_text("الرجاء إدخال القيمة المطلوبة أو اختر من الخيارات المتاحة.")
    return EDIT_FIELD

def edit_field_input_handler(update: Update, context: CallbackContext):
    if 'edit_field' in context.user_data:
        field = context.user_data['edit_field']
        if field.startswith("edit_field_issue_type_"):
            new_value = field.split('_', 3)[-1]
            context.user_data['issue_type'] = new_value
            log_entry = {"action": "edit_field", "field": "نوع المشكلة", "new_value": new_value}
        elif field.startswith("edit_field_client_"):
            new_value = field.split('_', 3)[-1]
            context.user_data['client'] = new_value
            log_entry = {"action": "edit_field", "field": "العميل", "new_value": new_value}
        else:
            new_value = update.message.text.strip()
            field_name = field.split('_')[-1]
            if field == "edit_field_order":
                context.user_data['order_id'] = new_value
            elif field == "edit_field_description":
                context.user_data['description'] = new_value
            elif field == "edit_field_image":
                context.user_data['image'] = new_value
            elif field == "edit_field_issue_reason":
                context.user_data['issue_reason'] = new_value
            log_entry = {"action": "edit_field", "field": field_name, "new_value": new_value}
        context.user_data.setdefault('edit_log', []).append(log_entry)
        update.message.reply_text(f"تم تعديل {field.split('_')[-1]} إلى: {new_value}")
        keyboard = [[InlineKeyboardButton("نعم", callback_data="edit_ticket_yes"),
                     InlineKeyboardButton("لا", callback_data="edit_ticket_no")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("هل تريد تعديل التذكرة مرة أخرى؟", reply_markup=reply_markup)
        return EDIT_PROMPT
    else:
        update.message.reply_text("حدث خطأ أثناء التعديل.")
        return EDIT_PROMPT

def main():
    updater = Updater(config.DA_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SUBSCRIPTION_PHONE: [MessageHandler(Filters.text & ~Filters.command, subscription_phone)],
            MAIN_MENU: [CallbackQueryHandler(da_main_menu_callback,
                                             pattern="^(menu_add_issue|menu_query_issue|client_option_|issue_reason_|issue_type_|attach_.*|edit_ticket_.*|edit_field_.*)")],
            NEW_ISSUE_CLIENT: [CallbackQueryHandler(da_main_menu_callback, pattern="^client_option_.*")],
            NEW_ISSUE_ORDER: [MessageHandler(Filters.text & ~Filters.command, new_issue_order)],
            NEW_ISSUE_DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, new_issue_description)],
            NEW_ISSUE_REASON: [CallbackQueryHandler(da_main_menu_callback, pattern="^issue_reason_.*")],
            NEW_ISSUE_TYPE: [CallbackQueryHandler(da_main_menu_callback, pattern="^issue_type_.*")],
            ASK_IMAGE: [CallbackQueryHandler(da_main_menu_callback, pattern="^(attach_yes|attach_no)$")],
            WAIT_IMAGE: [MessageHandler(Filters.photo, wait_image)],
            EDIT_PROMPT: [CallbackQueryHandler(edit_ticket_prompt_callback, pattern="^(edit_ticket_yes|edit_ticket_no)$")],
            EDIT_FIELD: [CallbackQueryHandler(edit_field_callback, pattern="^edit_field_.*"),
                         MessageHandler(Filters.text & ~Filters.command, edit_field_input_handler)],
            AWAITING_DA_RESPONSE: [MessageHandler(Filters.text & ~Filters.command, da_awaiting_response_handler)]
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: u.message.reply_text("تم إلغاء العملية."))]
    )
    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(da_callback_handler, pattern="^(close_|da_moreinfo_).*"))
    dp.add_handler(MessageHandler(Filters.text, default_handler_da))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
