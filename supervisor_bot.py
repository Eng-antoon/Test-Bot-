# supervisor_bot.py
import logging
import json
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler, CallbackContext
import db
import config

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(SUBSCRIPTION_PHONE, MAIN_MENU, SEARCH_TICKETS, AWAITING_RESPONSE) = range(4)
MAIN_MENU_OPTIONS = [['عرض الكل', 'استعلام عن مشكلة']]

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    sub = db.get_subscription(user.id, "Supervisor")
    if not sub:
        update.message.reply_text("أهلاً! يرجى إدخال رقم هاتفك للاشتراك (Supervisor):")
        return SUBSCRIPTION_PHONE
    else:
        context.user_data['awaiting_response'] = False
        reply_markup = ReplyKeyboardMarkup(MAIN_MENU_OPTIONS, resize_keyboard=True)
        update.message.reply_text(f"مرحباً {user.first_name}, اختر خياراً:", reply_markup=reply_markup)
        return MAIN_MENU

def subscription_phone(update: Update, context: CallbackContext):
    phone = update.message.text.strip()
    user = update.effective_user
    db.add_subscription(user.id, phone, 'Supervisor', "Supervisor", None,
                        user.username, user.first_name, user.last_name, update.effective_chat.id)
    context.user_data['awaiting_response'] = False
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_OPTIONS, resize_keyboard=True)
    update.message.reply_text("تم الاشتراك بنجاح كـ Supervisor!", reply_markup=reply_markup)
    return MAIN_MENU

def main_menu_handler(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    if text == 'عرض الكل':
        tickets = db.get_all_open_tickets()
        if tickets:
            for ticket in tickets:
                message_text = (
                    f"<b>تذكرة #{ticket['ticket_id']}</b>\n"
                    f"<b>رقم الطلب:</b> {ticket['order_id']}\n"
                    f"<b>العميل:</b> {ticket['client']}\n"
                    f"<b>الوصف:</b> {ticket['issue_description']}\n"
                    f"<b>نوع المشكلة:</b> {ticket['issue_type']}\n"
                    f"<b>الحالة:</b> {ticket['status']}"
                )
                keyboard = [[InlineKeyboardButton("عرض التفاصيل", callback_data=f"view_{ticket['ticket_id']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            update.message.reply_text("لا توجد تذاكر مفتوحة حالياً.")
        reply_markup = ReplyKeyboardMarkup(MAIN_MENU_OPTIONS, resize_keyboard=True)
        update.message.reply_text("اختر خياراً:", reply_markup=reply_markup)
        return MAIN_MENU
    elif text == 'استعلام عن مشكلة':
        update.message.reply_text("أدخل رقم الطلب:")
        return SEARCH_TICKETS
    else:
        update.message.reply_text("الخيار غير معروف. الرجاء اختيار خيار من القائمة.")
        return MAIN_MENU

def search_tickets(update: Update, context: CallbackContext):
    query_text = update.message.text.strip()
    tickets = db.search_tickets_by_order(query_text)
    if tickets:
        for ticket in tickets:
            message_text = (
                f"<b>تذكرة #{ticket['ticket_id']}</b>\n"
                f"<b>رقم الطلب:</b> {ticket['order_id']}\n"
                f"<b>العميل:</b> {ticket['client']}\n"
                f"<b>الوصف:</b> {ticket['issue_description']}\n"
                f"<b>نوع المشكلة:</b> {ticket['issue_type']}\n"
                f"<b>الحالة:</b> {ticket['status']}"
            )
            keyboard = [[InlineKeyboardButton("عرض التفاصيل", callback_data=f"view_{ticket['ticket_id']}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        update.message.reply_text("لم يتم العثور على تذاكر مطابقة.")
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_OPTIONS, resize_keyboard=True)
    update.message.reply_text("اختر خياراً:", reply_markup=reply_markup)
    return MAIN_MENU

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data.startswith("view_"):
        ticket_id = int(data.split("_")[1])
        ticket = db.get_ticket(ticket_id)
        if ticket:
            try:
                logs = ""
                if ticket["logs"]:
                    logs_list = json.loads(ticket["logs"])
                    logs = "\n".join([f"{entry.get('timestamp', '')}: {entry.get('action', '')} - {entry.get('message', '')}" for entry in logs_list])
            except Exception:
                logs = "لا توجد سجلات إضافية."
            text = (
                f"<b>تفاصيل التذكرة #{ticket['ticket_id']}</b>\n"
                f"<b>رقم الطلب:</b> {ticket['order_id']}\n"
                f"<b>العميل:</b> {ticket['client']}\n"
                f"<b>الوصف:</b> {ticket['issue_description']}\n"
                f"<b>نوع المشكلة:</b> {ticket['issue_type']}\n"
                f"<b>الحالة:</b> {ticket['status']}\n\n"
                f"<b>السجلات:</b>\n{logs}"
            )
            keyboard = [
                [InlineKeyboardButton("حل المشكلة", callback_data=f"solve_{ticket_id}")],
                [InlineKeyboardButton("تحرير الحل", callback_data=f"edit_{ticket_id}")],
                [InlineKeyboardButton("طلب المزيد من المعلومات", callback_data=f"moreinfo_{ticket_id}")],
                [InlineKeyboardButton("إرسال إلى العميل", callback_data=f"sendclient_{ticket_id}")]
            ]
            # If a client solution exists (i.e. status is "Client Responded"), offer the DA forward option
            if ticket["status"] == "Client Responded":
                keyboard.insert(0, [InlineKeyboardButton("إرسال للحالة إلى الوكيل", callback_data=f"sendto_da_{ticket_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            query.edit_message_text(text="التذكرة غير موجودة.")
        return MAIN_MENU

    elif data.startswith("solve_"):
        ticket_id = int(data.split("_")[1])
        context.user_data['ticket_id'] = ticket_id
        context.user_data['action'] = 'solve'
        context.user_data['awaiting_response'] = True
        context.bot.send_message(chat_id=query.message.chat_id,
                                 text="أدخل رسالة الحل للمشكلة:",
                                 reply_markup=ForceReply(selective=True))
        return AWAITING_RESPONSE

    elif data.startswith("edit_"):
        # Allow supervisor to edit the client's solution before sending to DA
        ticket_id = int(data.split("_")[1])
        ticket = db.get_ticket(ticket_id)
        client_solution = ""
        if ticket["logs"]:
            try:
                logs = json.loads(ticket["logs"])
                for entry in logs:
                    if entry.get("action") == "client_solution":
                        client_solution = entry.get("message", "")
                        break
            except Exception:
                client_solution = ""
        context.user_data['ticket_id'] = ticket_id
        context.user_data['action'] = 'edit'
        context.user_data['awaiting_response'] = True
        context.bot.send_message(chat_id=query.message.chat_id,
                                 text=f"أدخل رسالة الحل المعدلة للمشكلة:\nالحل الحالي: {client_solution}",
                                 reply_markup=ForceReply(selective=True))
        return AWAITING_RESPONSE

    elif data.startswith("moreinfo_"):
        ticket_id = int(data.split("_")[1])
        context.user_data['ticket_id'] = ticket_id
        context.user_data['action'] = 'moreinfo'
        context.user_data['awaiting_response'] = True
        context.bot.send_message(chat_id=query.message.chat_id,
                                 text="أدخل المعلومات الإضافية المطلوبة:",
                                 reply_markup=ForceReply(selective=True))
        return AWAITING_RESPONSE

    elif data.startswith("sendclient_"):
        ticket_id = int(data.split("_")[1])
        context.user_data['ticket_id'] = ticket_id
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            query.edit_message_text(text="التذكرة غير موجودة.")
            return MAIN_MENU
        if not ticket['client'] or ticket['client'] == 'غير محدد':
            keyboard = [[
                InlineKeyboardButton("بوبا", callback_data=f"setclient_{ticket_id}_بوبا"),
                InlineKeyboardButton("بتلكو", callback_data=f"setclient_{ticket_id}_بتلكو"),
                InlineKeyboardButton("بيبس", callback_data=f"setclient_{ticket_id}_بيبس")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(text="اختر العميل لإرسال التذكرة إليه:", reply_markup=reply_markup)
            return MAIN_MENU
        else:
            send_to_client(ticket_id)
            query.edit_message_text(text="تم إرسال التذكرة إلى العميل.")
            return MAIN_MENU

    elif data.startswith("setclient_"):
        parts = data.split("_")
        ticket_id = int(parts[1])
        client_choice = parts[2]
        db.update_ticket_status(ticket_id, "Awaiting Client Response", {"action": "set_client", "value": client_choice})
        send_to_client(ticket_id)
        query.edit_message_text(text=f"تم تعيين العميل إلى {client_choice} وإرسال التذكرة للعميل.")
        return MAIN_MENU

    elif data.startswith("sendto_da_"):
        # When the supervisor wants to forward the client's solution to the DA
        parts = data.split("_")
        if len(parts) < 3:
            query.edit_message_text(text="تنسيق البيانات غير صحيح.")
            return MAIN_MENU
        try:
            ticket_id = int(parts[2])
        except ValueError:
            query.edit_message_text(text="معرف التذكرة غير صحيح.")
            return MAIN_MENU
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            query.edit_message_text(text="التذكرة غير موجودة.")
            return MAIN_MENU
        # Retrieve the client's solution from the ticket logs
        client_solution = None
        if ticket["logs"]:
            try:
                logs = json.loads(ticket["logs"])
                for log in logs:
                    if log.get("action") == "client_solution":
                        client_solution = log.get("message")
                        break
            except Exception:
                client_solution = None
        if not client_solution:
            client_solution = "لا يوجد حل من العميل."
        # Update ticket status and add a log entry for forwarding
        db.update_ticket_status(ticket_id, "Pending DA Action", {"action": "supervisor_forward", "message": client_solution})
        notify_da(ticket_id, client_solution, info_request=False)
        query.edit_message_text(text="تم إرسال التذكرة إلى الوكيل.")
        return MAIN_MENU

    else:
        query.edit_message_text(text="الإجراء غير معروف.")
        return MAIN_MENU

def awaiting_response_handler(update: Update, context: CallbackContext):
    response = update.message.text.strip()
    ticket_id = context.user_data.get('ticket_id')
    action = context.user_data.get('action')
    if not ticket_id or not action:
        update.message.reply_text("حدث خطأ. الرجاء إعادة المحاولة.")
        return MAIN_MENU
    if action in ['solve', 'edit']:
        db.update_ticket_status(ticket_id, "Pending DA Action", {"action": "supervisor_solution", "message": response})
        notify_da(ticket_id, response, info_request=False)
        if action == 'solve':
            update.message.reply_text("تم إرسال الحل إلى الوكيل.")
        else:
            update.message.reply_text("تم تعديل الحل وإرساله إلى الوكيل.")
    elif action == 'moreinfo':
        db.update_ticket_status(ticket_id, "Pending DA Response", {"action": "request_more_info", "message": response})
        notify_da(ticket_id, response, info_request=True)
        update.message.reply_text("تم إرسال الطلب إلى الوكيل.")
    context.user_data.pop('ticket_id', None)
    context.user_data.pop('action', None)
    update.message.reply_text("تم حفظ ردك.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU_OPTIONS, resize_keyboard=True))
    return MAIN_MENU

def notify_da(ticket_id, message, info_request=False):
    ticket = db.get_ticket(ticket_id)
    da_id = ticket['da_id']
    if not da_id:
        logger.error("لا يوجد وكيل معين للتذكرة.")
        return
    bot = Bot(token=config.DA_BOT_TOKEN)
    if info_request:
        text = (
            f"<b>طلب معلومات إضافية للتذكرة #{ticket_id}</b>\n"
            f"<b>رقم الطلب:</b> {ticket['order_id']}\n"
            f"<b>الوصف:</b> {ticket['issue_description']}\n"
            f"<b>الحالة:</b> {ticket['status']}\n"
            f"<b>المعلومات المطلوبة:</b> {message}"
        )
        keyboard = [[InlineKeyboardButton("تطبيق المعلومات الإضافية", callback_data=f"da_moreinfo_{ticket_id}")]]
    else:
        text = (
            f"<b>حل للمشكلة للتذكرة #{ticket_id}</b>\n"
            f"<b>رقم الطلب:</b> {ticket['order_id']}\n"
            f"<b>الوصف:</b> {ticket['issue_description']}\n"
            f"<b>الحالة:</b> {ticket['status']}\n"
            f"<b>الحل:</b> {message}"
        )
        keyboard = [[InlineKeyboardButton("إغلاق التذكرة", callback_data=f"close_{ticket_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        da_sub = db.get_subscription(da_id, "DA")
        if da_sub:
            bot.send_message(chat_id=da_sub['chat_id'], text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error notifying DA: {e}")

def send_to_client(ticket_id):
    ticket = db.get_ticket(ticket_id)
    client_name = ticket['client']
    clients = db.get_clients_by_name(client_name)
    bot = Bot(token=config.CLIENT_BOT_TOKEN)
    message = (
        f"<b>تذكرة من المشرف</b>\n"
        f"<b>تذكرة #{ticket['ticket_id']}</b>\n"
        f"<b>رقم الطلب:</b> {ticket['order_id']}\n"
        f"<b>الوصف:</b> {ticket['issue_description']}\n"
        f"<b>نوع المشكلة:</b> {ticket['issue_type']}\n"
        f"<b>الحالة:</b> {ticket['status']}"
    )
    keyboard = [
        [InlineKeyboardButton("حالياً", callback_data=f"notify_pref_{ticket_id}_now")],
        [InlineKeyboardButton("خلال 15 دقيقة", callback_data=f"notify_pref_{ticket_id}_15")],
        [InlineKeyboardButton("خلال 10 دقائق", callback_data=f"notify_pref_{ticket_id}_10")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    for client in clients:
        try:
            bot.send_message(chat_id=client['chat_id'], text=message, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error notifying client {client['chat_id']}: {e}")

def main():
    updater = Updater(config.SUPERVISOR_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SUBSCRIPTION_PHONE: [MessageHandler(Filters.text & ~Filters.command, subscription_phone)],
            MAIN_MENU: [
                MessageHandler(Filters.text & ~Filters.command, main_menu_handler),
                CallbackQueryHandler(callback_handler, pattern="^(view_|solve_|edit_|moreinfo_|sendclient_|setclient_|sendto_da_).*")
            ],
            SEARCH_TICKETS: [MessageHandler(Filters.text & ~Filters.command, search_tickets)],
            AWAITING_RESPONSE: [MessageHandler(Filters.text & ~Filters.command, awaiting_response_handler)]
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: u.message.reply_text("تم إلغاء العملية."))]
    )
    dp.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
