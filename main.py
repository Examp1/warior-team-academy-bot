import os
import telebot
import sqlite3
import threading
import time
from dotenv import load_dotenv
from datetime import datetime
from dateutil.relativedelta import relativedelta
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS").split(",")]

bot = telebot.TeleBot(BOT_TOKEN)

# --------------------------------------------------------------------------
# DB FUNCTIONS
# --------------------------------------------------------------------------

def db_connect():
    conn = sqlite3.connect("clients.sql")
    cur = conn.cursor()
    return conn, cur

def db_close_connect(conn, save=False):
    if save:
        conn.commit()
    conn.close()

def init_db():
    conn, cur = db_connect()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            parent_name TEXT,
            parent_phone TEXT,
            start_date TEXT,
            finish_date TEXT,
            is_expiried BOOLEAN DEFAULT FALSE,
            how_much_was_price INTEGER,
            telegram_id INTEGER,
            telegram_username TEXT,
            role TEXT DEFAULT 'user'
        )
    ''')
    db_close_connect(conn, save=True)

init_db()

# --------------------------------------------------------------------------
# CHECK SUBSCRIBTIONS
# --------------------------------------------------------------------------

def check_subscriptions():
    time.sleep(10)
    while True: #делаем бесконечный цикл
        conn, cur = db_connect() #конект к бд
        cur.execute("SELECT id, name, finish_date FROM clients") #достаем всех клиентов
        rows = cur.fetchall() #получаем клиентов в перменную row
        db_close_connect(conn) # закрываем конект к бд
        
        today = datetime.now().date() # получаем текущую дату
        
        for row in rows:
            user_id, name, finish_date_str = row # деструкторизируем
            
            if not finish_date_str:  # если finish_date пустое/None/""
                continue             # пропускаем этого клиента, переходим к следующему
                
            try: # делаем трай , чтобы если что-то не так выбрасывать ошибку 
                finish_date = datetime.strptime(finish_date_str, "%d.%m.%Y").date() # получаем финиш дату 
                days_left = (finish_date - today).days # высчитываем сколько дней осталось
                
                if days_left == 1: # если 1 , то кидаем сообщение админам
                    for admin_id in ADMIN_IDS:
                        bot.send_message(
                            admin_id,
                            f"⚠️ Абонемент для {name} истекает завтра ({finish_date_str})"
                        )
                elif days_left == 0:
                    conn, cur = db_connect() 
                    cur.execute("UPDATE clients SET is_expiried = TRUE WHERE id = ?", (user_id,))
                    db_close_connect(conn, save=True)
                    for admin_id in ADMIN_IDS:
                        bot.send_message(
                            admin_id,
                            f"❌ Абонемент для {name} истек сегодня!"
                        )
                        
            except ValueError:
                continue
        
        time.sleep(600)


# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------

# отправка длинных сообщений
def send_long(chat_id, text, markup=None):
    last_msg = None
    for i in range(0, len(text), 4000):
        last_msg = bot.send_message(chat_id, text[i:i+4000], parse_mode="Markdown", reply_markup=markup)
    return last_msg

# хранение состояния регистрации
user_states = {}   # {chat_id: {name:..., phone:..., parent_name:..., parent_phone:...}}


# --------------------------------------------------------------------------
# ADMIN PANEL
# --------------------------------------------------------------------------

def make_admin_markup():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Просмотреть всех пользователей")
    markup.add("Регистрация пользователя")
    markup.add("Поиск пользователя по базе")
    return markup

def cancel_action():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Отмените действие")
    return markup

@bot.message_handler(commands=['admin'])
def admin(message):
    if message.chat.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ У вас нет доступа к админ панели.")
        return
    else:
        sign_in_admin(message)


def sign_in_admin(message):
    markup = make_admin_markup()
    msg = bot.send_message(message.chat.id, "Добро пожаловать в админ панель:", reply_markup=markup)
    bot.register_next_step_handler(msg, choose_admin_function)


def choose_admin_function(message):
    if message.text == "Просмотреть всех пользователей":
        show_all_users(message)
    elif message.text == "Регистрация пользователя":
        start_register(message)
    elif message.text == "Поиск пользователя по базе":
        start_search(message)
    else:
        markup = make_admin_markup()
        msg = bot.send_message(message.chat.id, "Неизвестная команда. Выберите кнопку.", reply_markup=markup)
        bot.register_next_step_handler(msg, choose_admin_function)


# --------------------------------------------------------------------------
# SERACH USERS
# --------------------------------------------------------------------------

def start_search(message):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    msg = bot.send_message(message.chat.id, "Введите имя или телефон пользователя для поиска:", reply_markup=remove_markup)
    bot.register_next_step_handler(msg, perform_search)

def perform_search(message):
    query = message.text.strip()
    conn, cur = db_connect()
    cur.execute("SELECT * FROM clients WHERE name LIKE ? OR phone LIKE ? OR parent_name LIKE ? OR parent_phone LIKE ?", 
                (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"))
    find_users = cur.fetchall()
    db_close_connect(conn)

    if not find_users:
        markup = make_admin_markup()
        msg = bot.send_message(message.chat.id, "Пользователи не найдены.", reply_markup=markup)
        bot.register_next_step_handler(msg, choose_admin_function)
        return

    for r in find_users:
        text = (
            f"🆔 Tg: @{r[9]} | id: {r[8]}\n"
            f"👤 Имя: {r[1]}\n"
            f"📱 Телефон: {r[2]}\n"
            f"👨‍👩‍👧 Родитель: {r[3]}\n"
            f"📞 Тел. родителя: {r[4]}\n"
            f"📅 Дата оплаты абонемента: {r[5]}\n"
            f"📅 Дата окончанния абонемента: {r[6]}\n"
            f"📅 Абонемент закончился ?: {r[7]}\n"
        )
        
        # Создаём инлайн-кнопки для каждого пользователя
        inline_markup = telebot.types.InlineKeyboardMarkup()
        inline_markup.add(
            telebot.types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{r[0]}"),
            telebot.types.InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{r[0]}")
        )
        bot.send_message(message.chat.id, text, reply_markup=inline_markup)

# --------------------------------------------------------------------------
# USERS ACTIONS 
# --------------------------------------------------------------------------

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def handle_delete(call):
    user_id = call.data.split("_")[1]
    conn, curr = db_connect()
    curr.execute("DELETE FROM clients WHERE id = ?", (user_id,))
    db_close_connect(conn, save=True)
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.answer_callback_query(call.id, "Удалено!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
def handle_edit(call):
    user_id = call.data.split("_")[1]
    inline_markup = telebot.types.InlineKeyboardMarkup()
    inline_markup.add(telebot.types.InlineKeyboardButton("Изменить имя", callback_data=f"chname_{user_id}"))
    inline_markup.add(telebot.types.InlineKeyboardButton("Изменить телефон", callback_data=f"chphone_{user_id}"))
    inline_markup.add(telebot.types.InlineKeyboardButton("Изменить родителя", callback_data=f"chparent_{user_id}"))
    inline_markup.add(telebot.types.InlineKeyboardButton("Изменить телефон родителя", callback_data=f"chparentphone_{user_id}"))
    inline_markup.add(telebot.types.InlineKeyboardButton("Продлить абонемент", callback_data=f"renew_subscription_{user_id}"))
    
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=inline_markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chname_"))
def handle_edit_name(call):
    user_id = call.data.split("_")[1]
    cancale_btn = cancel_action()
    msg = bot.send_message(call.message.chat.id, "Введите новое имя:", reply_markup=cancale_btn)
    bot.register_next_step_handler(msg, save_new_value, user_id, "name")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chphone_"))
def handle_edit_phone(call):
    user_id = call.data.split("_")[1]
    cancale_btn = cancel_action()
    msg = bot.send_message(call.message.chat.id, "Введите новый телефон:", reply_markup=cancale_btn)
    bot.register_next_step_handler(msg, save_new_value, user_id, "phone")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chparentphone_"))
def handle_edit_parent_phone(call):
    user_id = call.data.split("_")[1]
    cancale_btn = cancel_action()
    msg = bot.send_message(call.message.chat.id, "Введите телефон родителя:", reply_markup=cancale_btn)
    bot.register_next_step_handler(msg, save_new_value, user_id, "parent_phone")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chparent_"))
def handle_edit_parent(call):
    user_id = call.data.split("_")[1]
    cancale_btn = cancel_action()
    msg = bot.send_message(call.message.chat.id, "Введите имя родителя:", reply_markup=cancale_btn)
    bot.register_next_step_handler(msg, save_new_value, user_id, "parent_name")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("renew_subscription_"))
def handle_edit_parent(call):
    user_id = call.data.split("_")[2]
    chat_id = call.message.chat.id
    # cancale_btn = cancel_action()
    conn, cur = db_connect()
    cur.execute("SELECT * FROM clients WHERE id = ?", (user_id,))
    find_user = cur.fetchone()
    db_close_connect(conn, save=True)
    if not find_user:
        bot.answer_callback_query(call.id, "Пользователь не найден")
        return
    
    user_states[chat_id] = {
        "action": "renew",
        "client_id": user_id,
        "client_name": find_user[1]
        }
    calendar, step = DetailedTelegramCalendar().build()
    bot.send_message(chat_id, f"Продление для {find_user[1]}. Выберите новую дату начала:", reply_markup=calendar)
    bot.answer_callback_query(call.id)
    
# Универсальная функция сохранения
def save_new_value(message, user_id, field):
    if message.text == "Отмените действие":
        markup = make_admin_markup()
        msg = bot.send_message(message.chat.id, "Действие отменено.", reply_markup=markup)
        bot.register_next_step_handler(msg, choose_admin_function)
        return
    new_value = message.text.strip()
    conn, cur = db_connect()
    cur.execute(f"UPDATE clients SET {field} = ? WHERE id = ?", (new_value, user_id))
    db_close_connect(conn, save=True)
    markup = make_admin_markup()
    msg = bot.send_message(message.chat.id, "✅ Данные обновлены!", reply_markup=markup)
    bot.register_next_step_handler(msg, choose_admin_function)
    
# --------------------------------------------------------------------------
# SHOW USERS
# --------------------------------------------------------------------------

def show_all_users(message):
    conn, cur = db_connect()
    cur.execute("SELECT * FROM clients")
    rows = cur.fetchall()
    db_close_connect(conn)

    if not rows:
        msg = bot.send_message(message.chat.id, "Пользователей пока нет.")
        bot.register_next_step_handler(msg, choose_admin_function)
        return

    text = "📋 *Список пользователей:*\n\n"
    for r in rows:
        text += (
            f"🆔 Tg: @{r[9]} | id: {r[8]}\n"
            f"👤 Имя: {r[1]}\n"
            f"📱 Телефон: {r[2]}\n"
            f"👨‍👩‍👧 Родитель: {r[3]}\n"
            f"📞 Тел. родителя: {r[4]}\n"
            f"📅 Дата оплаты абонемента: {r[5]}\n"
            f"📅 Дата окончанния абонемента: {r[6]}\n"
            f"📅 Абонемент закончился ?: {r[7]}\n\n"
        )

    msg = send_long(message.chat.id, text)
    bot.register_next_step_handler(msg, choose_admin_function)

# --------------------------------------------------------------------------
# REGISTRATION FSM
# --------------------------------------------------------------------------

def start_register(message):
    remove_markup = telebot.types.ReplyKeyboardRemove()
    chat_id = message.chat.id
    user_states[chat_id] = {}
    msg = bot.send_message(chat_id, "Введите имя пользователя:", reply_markup=remove_markup)
    bot.register_next_step_handler(msg, reg_name)


def reg_name(message):
    chat_id = message.chat.id
    user_states[chat_id]["name"] = message.text.strip()
    user_states[chat_id]["telegram_id"] = message.chat.id
    user_states[chat_id]["telegram_username"] = message.chat.username
    msg = bot.send_message(chat_id, "Введите номер телефона:")
    bot.register_next_step_handler(msg, reg_phone)


def reg_phone(message):
    chat_id = message.chat.id
    user_states[chat_id]["phone"] = message.text.strip()
    msg = bot.send_message(chat_id, "Введите ФИО родителя:")
    bot.register_next_step_handler(msg, reg_parent_name)


def reg_parent_name(message):
    chat_id = message.chat.id
    user_states[chat_id]["parent_name"] = message.text.strip()
    msg = bot.send_message(chat_id, "Введите номер телефона родителя:")
    bot.register_next_step_handler(msg, reg_parent_phone)


def reg_parent_phone(message):
    chat_id = message.chat.id
    user_states[chat_id]["parent_phone"] = message.text.strip()
    msg = bot.send_message(chat_id, "Введите сумму сколько оплатили:")
    bot.register_next_step_handler(msg, how_much_was_paid)

def how_much_was_paid(message):
    chat_id = message.chat.id
    user_states[chat_id]["how_much_was_price"] = message.text.strip()
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Груповые тренеровки")
    markup.add("Персональные тренеровки")
    msg = bot.send_message(chat_id, "Выберите тип тренеровки:" , reply_markup=markup)
    bot.register_next_step_handler(msg, training_type)
    
def training_type(message):
    chat_id = message.chat.id
    user_states[chat_id]["training_type"] = message.text.strip()
    
    remove_markup = telebot.types.ReplyKeyboardRemove()
    calendar, step = DetailedTelegramCalendar().build()
    bot.send_message(chat_id, "Выберите дату начала абонемента:", reply_markup=remove_markup)
    bot.send_message(chat_id, "📅 Выберите дату:", reply_markup=calendar)
    
   
@bot.callback_query_handler(func=DetailedTelegramCalendar.func())
def handle_calendar(call):
    chat_id = call.message.chat.id
    result, key, step = DetailedTelegramCalendar().process(call.data)
    
    if not result and key:
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=key)
    elif result:
        start_date = result
        finish_date = start_date + relativedelta(months=1)
        
        data = user_states[chat_id]
        conn, cur = db_connect()
        
        if data.get("action") == "renew":
            # Продление — UPDATE
            cur.execute(
                "UPDATE clients SET start_date = ?, finish_date = ?, is_expiried = ? WHERE id = ?",
                (start_date.strftime("%d.%m.%Y"), finish_date.strftime("%d.%m.%Y"), 0 ,data["client_id"])
            )
            bot.edit_message_text(
                f'✅ Подписка продлена для {data["client_name"]}!\n📅 Абонемент: {start_date.strftime("%d.%m.%Y")} - {finish_date.strftime("%d.%m.%Y")}',
                chat_id, call.message.message_id
            )
        else:
            # Регистрация — INSERT
            cur.execute(
                "INSERT INTO clients (name, phone, parent_name, parent_phone, start_date, finish_date, telegram_id, telegram_username) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (data["name"], data["phone"], data["parent_name"], data["parent_phone"],
                 start_date.strftime("%d.%m.%Y"), finish_date.strftime("%d.%m.%Y"), data["telegram_id"], data["telegram_username"])
            )
            bot.edit_message_text(
                f'✅ Регистрация завершена!\n📅 Абонемент: {start_date.strftime("%d.%m.%Y")} - {finish_date.strftime("%d.%m.%Y")}',
                chat_id, call.message.message_id
            )
        
        db_close_connect(conn, save=True)
        del user_states[chat_id]
        
        markup = make_admin_markup()
        msg = bot.send_message(chat_id, "Возвращаемся в админ панель:", reply_markup=markup)
        bot.register_next_step_handler(msg, choose_admin_function)

# --------------------------------------------------------------------------
# USER PANEL
# --------------------------------------------------------------------------

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, f'Добро пожаловать! Ваш ID: {message.chat.id}')

# --------------------------------------------------------------------------
# START POLLING
# --------------------------------------------------------------------------

subscription_thread = threading.Thread(target=check_subscriptions, daemon=True)
subscription_thread.start()

bot.infinity_polling()
