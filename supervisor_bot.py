#!/usr/bin/env python3
# supervisor_bot.py
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler, CallbackContext
import db
import config

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

(SUBSCRIPTION_PHONE, MAIN_MENU, SEARCH_TICKETS, AWAITING_RESPONSE) = range(4)

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    sub = db.get_subscription(user.id, "Supervisor")
    if not sub:
        update.message.reply_text("أهلاً! يرجى إدخال رقم هاتفك للاشتراك (Supervisor):")
        return SUBSCRIPTION_PHONE
    else:
        keyboard = [[InlineKeyboardButton("عرض الكل", callback_data="menu_show_all"),
                     InlineKeyboardButton("استعلام عن مشكلة", callback_data="menu_query_issue")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(f"مرحباً {user.first_name}", reply_markup=reply_markup)
        return MAIN_MENU

def subscription_phone(update: Update, context: CallbackContext):
    phone = update.message.text.strip()
    user = update.effective_user
    db.add_subscription(user.id, phone, 'Supervisor', "Supervisor", None,
                        user.username, user.first_name, user.last_name, update.effective_chat.id)
    keyboard = [[InlineKeyboardButton("عرض الكل", callback_data="menu_show_all"),
                 InlineKeyboardButton("استعلام عن مشكلة", callback_data="menu_query_issue")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("تم الاشتراك بنجاح كـ Supervisor!", reply_markup=reply_markup)
    return MAIN_MENU

def supervisor_main_menu_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    if data == "menu_show_all":
        tickets = db.get_all_open_tickets()
        if tickets:
            for ticket in tickets:
                text = (f"<b>تذكرة #{ticket['ticket_id']}</b>\n"
                        f"رقم الطلب: {ticket['order_id']}\n"
                        f"العميل: {ticket['client']}\n"
                        f"الوصف: {ticket['issue_description']}\n"
                        f"الحالة: {ticket['status']}")
                keyboard = [[InlineKeyboardButton("عرض التفاصيل", callback_data=f"view_{ticket['ticket_id']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                query.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            query.edit_message_text("لا توجد تذاكر مفتوحة حالياً.")
        return MAIN_MENU
    elif data == "menu_query_issue":
        query.edit_message_text("أدخل رقم الطلب:")
        return SEARCH_TICKETS
    elif data.startswith("view_"):
        ticket_id = int(data.split("_")[1])
        ticket = db.get_ticket(ticket_id)
        if ticket:
            try:
                logs = ""
                if ticket["logs"]:
                    logs_list = json.loads(ticket["logs"])
                    logs = "\n".join([f"{entry.get('timestamp', '')}: {entry.get('action', '')} - {entry.get('message', '')}"
                                       for entry in logs_list])
            except Exception:
                logs = "لا توجد سجلات إضافية."
            text = (f"<b>تفاصيل التذكرة #{ticket['ticket_id']}</b>\n"
                    f"رقم الطلب: {ticket['order_id']}\n"
                    f"العميل: {ticket['client']}\n"
                    f"الوصف: {ticket['issue_description']}\n"
                    f"سبب المشكلة: {ticket['issue_reason']}\n"
                    f"نوع المشكلة: {ticket['issue_type']}\n"
                    f"الحالة: {ticket['status']}\n\n"
                    f"السجلات:\n{logs}")
            # "تحرير الحل" button removed.
            keyboard = [
                [InlineKeyboardButton("حل المشكلة", callback_data=f"solve_{ticket_id}")],
                [InlineKeyboardButton("طلب المزيد من المعلومات", callback_data=f"moreinfo_{ticket_id}")],
                [InlineKeyboardButton("إرسال إلى العميل", callback_data=f"sendclient_{ticket_id}")]
            ]
            if ticket["status"] == "Client Responded":
                keyboard.insert(0, [InlineKeyboardButton("إرسال للحالة إلى الوكيل", callback_data=f"sendto_da_{ticket_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            query.edit_message_text("التذكرة غير موجودة.")
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
        # Show confirmation before sending to client.
        keyboard = [[InlineKeyboardButton("نعم", callback_data=f"confirm_sendclient_{ticket_id}"),
                     InlineKeyboardButton("لا", callback_data=f"cancel_sendclient_{ticket_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("هل أنت متأكد من إرسال التذكرة إلى العميل؟", reply_markup=reply_markup)
        return MAIN_MENU
    elif data.startswith("confirm_sendclient_"):
        ticket_id = int(data.split("_")[2])
        send_to_client(ticket_id)
        query.edit_message_text("تم إرسال التذكرة إلى العميل.")
        return MAIN_MENU
    elif data.startswith("cancel_sendclient_"):
        ticket_id = int(data.split("_")[2])
        query.edit_message_text("تم إلغاء الإرسال إلى العميل.")
        return MAIN_MENU
    elif data.startswith("sendto_da_"):
        ticket_id = int(data.split("_")[1])
        # Show confirmation before sending to DA.
        keyboard = [[InlineKeyboardButton("نعم", callback_data=f"confirm_sendto_da_{ticket_id}"),
                     InlineKeyboardButton("لا", callback_data=f"cancel_sendto_da_{ticket_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("هل أنت متأكد من إرسال الحل إلى الوكيل؟", reply_markup=reply_markup)
        return MAIN_MENU
    elif data.startswith("confirm_sendto_da_"):
        ticket_id = int(data.split("_")[2])
        ticket = db.get_ticket(ticket_id)
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
        db.update_ticket_status(ticket_id, "Pending DA Action", {"action": "supervisor_forward", "message": client_solution})
        notify_da(ticket_id, client_solution, info_request=False)
        query.edit_message_text("تم إرسال التذكرة إلى الوكيل.")
        return MAIN_MENU
    elif data.startswith("cancel_sendto_da_"):
        ticket_id = int(data.split("_")[2])
        query.edit_message_text("تم إلغاء إرسال التذكرة إلى الوكيل.")
        return MAIN_MENU
    else:
        query.edit_message_text("الإجراء غير معروف.")
        return MAIN_MENU

def search_tickets(update: Update, context: CallbackContext):
    query_text = update.message.text.strip()
    tickets = db.search_tickets_by_order(query_text)
    if tickets:
        for ticket in tickets:
            text = (f"<b>تذكرة #{ticket['ticket_id']}</b>\n"
                    f"رقم الطلب: {ticket['order_id']}\n"
                    f"العميل: {ticket['client']}\n"
                    f"الوصف: {ticket['issue_description']}\n"
                    f"الحالة: {ticket['status']}")
            keyboard = [[InlineKeyboardButton("عرض التفاصيل", callback_data=f"view_{ticket['ticket_id']}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        update.message.reply_text("لم يتم العثور على تذاكر مطابقة.")
    keyboard = [[InlineKeyboardButton("عرض الكل", callback_data="menu_show_all"),
                 InlineKeyboardButton("استعلام عن مشكلة", callback_data="menu_query_issue")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("اختر خياراً:", reply_markup=reply_markup)
    return MAIN_MENU

def awaiting_response_handler(update: Update, context: CallbackContext):
    response = update.message.text.strip()
    ticket_id = context.user_data.get('ticket_id')
    action = context.user_data.get('action')
    if not ticket_id or not action:
        update.message.reply_text("حدث خطأ. أعد المحاولة.")
        return MAIN_MENU
    if action == 'solve':
        db.update_ticket_status(ticket_id, "Pending DA Action", {"action": "supervisor_solution", "message": response})
        notify_da(ticket_id, response, info_request=False)
        update.message.reply_text("تم إرسال الحل إلى الوكيل.")
    elif action == 'moreinfo':
        db.update_ticket_status(ticket_id, "Pending DA Response", {"action": "request_more_info", "message": response})
        notify_da(ticket_id, response, info_request=True)
        update.message.reply_text("تم إرسال الطلب إلى الوكيل.")
    context.user_data.pop('ticket_id', None)
    context.user_data.pop('action', None)
    return MAIN_MENU

def notify_da(ticket_id, message, info_request=False):
    ticket = db.get_ticket(ticket_id)
    da_id = ticket['da_id']
    if not da_id:
        logger.error("لا يوجد وكيل معين للتذكرة.")
        return
    bot = Bot(token=config.DA_BOT_TOKEN)
    if info_request:
        text = (f"<b>طلب معلومات إضافية للتذكرة #{ticket_id}</b>\n"
                f"رقم الطلب: {ticket['order_id']}\n"
                f"الوصف: {ticket['issue_description']}\n"
                f"الحالة: {ticket['status']}\n"
                f"المعلومات المطلوبة: {message}")
        keyboard = [[InlineKeyboardButton("تطبيق المعلومات الإضافية", callback_data=f"da_moreinfo_{ticket_id}")]]
    else:
        text = (f"<b>حل للمشكلة للتذكرة #{ticket_id}</b>\n"
                f"رقم الطلب: {ticket['order_id']}\n"
                f"الوصف: {ticket['issue_description']}\n"
                f"الحالة: {ticket['status']}\n"
                f"الحل: {message}")
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
    message = (f"<b>تذكرة من المشرف</b>\n"
               f"تذكرة #{ticket['ticket_id']}\n"
               f"رقم الطلب: {ticket['order_id']}\n"
               f"الوصف: {ticket['issue_description']}\n"
               f"الحالة: {ticket['status']}")
    keyboard = [
        [InlineKeyboardButton("حالياً", callback_data=f"notify_pref_{ticket_id}_now")],
        [InlineKeyboardButton("خلال 15 دقيقة", callback_data=f"notify_pref_{ticket_id}_15")],
        [InlineKeyboardButton("خلال 10 دقائق", callback_data=f"notify_pref_{ticket_id}_10")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    for client in db.get_clients_by_name(client_name):
        try:
            bot.send_message(chat_id=client['chat_id'], text=message, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error notifying client {client['chat_id']}: {e}")

def default_handler_supervisor(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("عرض الكل", callback_data="menu_show_all"),
                 InlineKeyboardButton("استعلام عن مشكلة", callback_data="menu_query_issue")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("الرجاء اختيار خيار:", reply_markup=reply_markup)
    return MAIN_MENU

def main():
    updater = Updater(config.SUPERVISOR_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SUBSCRIPTION_PHONE: [MessageHandler(Filters.text & ~Filters.command, subscription_phone)],
            MAIN_MENU: [CallbackQueryHandler(supervisor_main_menu_callback,
                                             pattern="^(menu_show_all|menu_query_issue|view_|solve_|moreinfo_|sendclient_|setclient_|sendto_da_|confirm_sendclient_|cancel_sendclient_|confirm_sendto_da_|cancel_sendto_da_).*")],
            SEARCH_TICKETS: [MessageHandler(Filters.text & ~Filters.command, search_tickets)],
            AWAITING_RESPONSE: [MessageHandler(Filters.text & ~Filters.command, awaiting_response_handler)]
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: u.message.reply_text("تم إلغاء العملية."))]
    )
    dp.add_handler(conv_handler)
    dp.add_handler(MessageHandler(Filters.text, default_handler_supervisor))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
