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
    conn.row_factory = sqlite3.Row
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
            how_much_was_price TEXT,
            training_type TEXT,
            telegram_id INTEGER,
            telegram_username TEXT,
            comment TEXT,
            role TEXT DEFAULT 'user',
            birthday TEXT
        )
    ''')
    db_close_connect(conn, save=True)

init_db()

# --------------------------------------------------------------------------
# CHECK SUBSCRIBTIONS
# --------------------------------------------------------------------------

def safe_send(chat_id, text):
    try:
        bot.send_message(chat_id, text)
        return True
    except Exception as e:
        print(f"Не удалось отправить сообщение {chat_id}: {e}")
        return False

def check_subscriptions():
    while True:
        conn, cur = db_connect()
        cur.execute("SELECT id, name, telegram_id, telegram_username, finish_date, is_expiried FROM clients")
        rows = cur.fetchall()
        db_close_connect(conn)
        
        today = datetime.now().date()
        to_update = []
        
        for row in rows:
            user_id, name, telegram_id, telegram_username, finish_date_str, is_expiried = row
            
            if not finish_date_str:
                continue
                
            try:
                finish_date = datetime.strptime(finish_date_str, "%d.%m.%Y").date()
                days_left = (finish_date - today).days
                
                if days_left == 1:
                    for admin_id in ADMIN_IDS:
                        safe_send(admin_id, f"⚠️ Абонемент {name} @{telegram_username} истекает завтра ({finish_date_str})")
                    if telegram_id:
                        safe_send(telegram_id, f"⚠️ {name}, ваш абонемент истекает завтра!")
                        
                elif days_left <= 0:
                    # Обновляем только если ещё не помечен как истёкший
                    to_update.append(user_id)
                    
                    if days_left == 0:
                        msg = f"❌ Абонемент {name} @{telegram_username} истекает сегодня!"
                    else:
                        msg = f"❌ Абонемент {name} @{telegram_username} истёк {finish_date_str}!"
                    
                    if days_left == 0:
                        msg2 = f"❌ Ваш абонемент {name} истекает сегодня!"
                    else:
                        msg2 = f"❌ Ваш абонемент {name} истёк {finish_date_str}!"
                    
                    for admin_id in ADMIN_IDS:
                        safe_send(admin_id, msg)
                    if telegram_id:
                        safe_send(telegram_id, msg2)
                        
            except ValueError as e:
                print(f"Ошибка парсинга даты у {name}: {e}")
                continue
        
        # Один UPDATE после цикла
        if to_update:
            conn, cur = db_connect()
            cur.executemany("UPDATE clients SET is_expiried = TRUE WHERE id = ?", [(uid,) for uid in to_update])
            db_close_connect(conn, save=True)
        
        time.sleep(86400)



# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------

COMMANDS = ['/start', '/admin']

def with_command_check(func):
    def wrapper(message, *args, **kwargs):
        if message.text in COMMANDS:
            if message.text == '/start':
                start(message)
            elif message.text == '/admin':
                admin(message)
            return
        return func(message, *args, **kwargs)
    return wrapper

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
    markup.add("Продлить все абонементы на N дней")
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
    elif message.text == "Продлить все абонементы на N дней":
        renew_all_subscription(message)
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
        expired_status = "✔️" if r[7] == 1 else "❌"
        text = (
            f"🆔 Tg: @{r['telegram_username']} | id: {r['telegram_id']}\n"
            f"👤 Имя: {r['name']}\n"
            f"📅 Дата рождения: {r['birthday']}\n"
            f"📱 Телефон: {r['phone']}\n"
            f"👨‍👩‍👧 Родитель: {r['parent_name']}\n"
            f"📞 Тел. родителя: {r['parent_phone']}\n"
            f"📅 Дата оплаты абонемента: {r['start_date']}\n"
            f"📅 Дата окончанния абонемента: {r['finish_date']}\n"
            f"📅 Абонемент закончился?: {expired_status}\n"
            f"💵 Сколько внес денег: {r['how_much_was_price']}\n"
            f"🤾‍♀️ Тип тренеровок: {r['training_type']}\n"
        )
        if r["comment"]:
            text += f"📝 Примечание: {r['comment']}\n"
        
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

def renew_all_subscription(message):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "Введите количество дней для продления:")
    bot.register_next_step_handler(msg, process_renew_all)

def process_renew_all(message):
    chat_id = message.chat.id
    
    try:
        days = int(message.text.strip())
    except ValueError:
        msg = bot.send_message(chat_id, "❌ Введите число!")
        bot.register_next_step_handler(msg, process_renew_all)
        return
    
    conn, cur = db_connect()
    cur.execute("SELECT id, finish_date FROM clients")
    clients = cur.fetchall()
    
    updated = 0
    for client in clients:
        if not client["finish_date"]:
            continue
        try:
            finish_date = datetime.strptime(client["finish_date"], "%d.%m.%Y").date()
            new_finish_date = finish_date + relativedelta(days=days)
            cur.execute("UPDATE clients SET finish_date = ?, is_expiried = FALSE WHERE id = ?", 
                       (new_finish_date.strftime("%d.%m.%Y"), client["id"]))
            updated += 1
        except ValueError:
            continue
    
    db_close_connect(conn, save=True)
    
    markup = make_admin_markup()
    msg = bot.send_message(chat_id, f"✅ Продлено {updated} абонементов на {days} дней!", reply_markup=markup)
    bot.register_next_step_handler(msg, choose_admin_function)
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
    bot.answer_callback_query(call.id, "Удалено!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
def handle_edit(call):
    user_id = call.data.split("_")[1]
    inline_markup = telebot.types.InlineKeyboardMarkup()
    inline_markup.add(telebot.types.InlineKeyboardButton("Изменить имя", callback_data=f"chname_{user_id}"), telebot.types.InlineKeyboardButton("Изменить дату рожения", callback_data=f"cbirthday_{user_id}"))
    inline_markup.add(telebot.types.InlineKeyboardButton("Изменить телефон", callback_data=f"chphone_{user_id}"), telebot.types.InlineKeyboardButton("Изменить родителя", callback_data=f"chparent_{user_id}"))
    inline_markup.add(telebot.types.InlineKeyboardButton("Изменить телефон родителя", callback_data=f"chparentphone_{user_id}"), telebot.types.InlineKeyboardButton("Редактировать внесенную сумму", callback_data=f"cSumm_{user_id}"))
    inline_markup.add(telebot.types.InlineKeyboardButton("Продлить абонемент", callback_data=f"renewSubscription_{user_id}"), telebot.types.InlineKeyboardButton("Редактировать тип абонемента", callback_data=f"cTrainingType_{user_id}"))
    inline_markup.add(telebot.types.InlineKeyboardButton("Добавить коментарий к клиенту", callback_data=f"addComment_{user_id}"))
    
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=inline_markup)
    bot.answer_callback_query(call.id)

EDIT_FIELDS = {
    "chname": {"field": "name", "prompt": "Введите новое имя:"},
    "cbirthday": {"field": "birthday", "prompt": "Введите новую дату:"},
    "chphone": {"field": "phone", "prompt": "Введите новый телефон:"},
    "chparent": {"field": "parent_name", "prompt": "Введите имя родителя:"},
    "chparentphone": {"field": "parent_phone", "prompt": "Введите телефон родителя:"},
    "cSumm": {"field": "how_much_was_price", "prompt": "Введите новую сумму:"},
    "cTrainingType": {"field": "training_type", "prompt": "Введите тип абонемента:", "options": ["Обычный", "Безлимит"] },
    "addComment": {"field": "comment", "prompt": "Введите комментарий:"},
}

def is_edit_callback(call):
    prefix = call.data.split("_")[0]
    return prefix in EDIT_FIELDS

@bot.callback_query_handler(func=is_edit_callback)
def handle_edit_field(call):
    parts = call.data.split("_")
    prefix = parts[0]
    user_id = parts[1]
    
    config = EDIT_FIELDS[prefix]
    
    if "options" in config:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        for option in config["options"]:
            markup.add(option)
        markup.add("Отмените действие")
    else:
        markup = cancel_action()
    
    msg = bot.send_message(
        call.message.chat.id, 
        config["prompt"], 
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, save_new_value, user_id, config["field"])
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("renewSubscription_"))
def handle_edit_parent(call):
    user_id = call.data.split("_")[1]
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
        expired_status = "✔️" if r[7] == 1 else "❌"
          
        text += (
            f"🆔 Tg: @{r['telegram_username']} | id: {r['telegram_id']}\n"
            f"👤 Имя: {r['name']}\n"
            f"📅 Дата рождения: {r['birthday']}\n"
            f"📱 Телефон: {r['phone']}\n"
            f"👨‍👩‍👧 Родитель: {r['parent_name']}\n"
            f"📞 Тел. родителя: {r['parent_phone']}\n"
            f"📅 Дата оплаты абонемента: {r['start_date']}\n"
            f"📅 Дата окончанния абонемента: {r['finish_date']}\n"
            f"📅 Абонемент закончился?: {expired_status}\n"
            f"💵 Сколько внес денег: {r['how_much_was_price']}\n"
            f"🤾‍♀️ Тип тренеровок: {r['training_type']}\n"
        )
        if r["comment"]:
            text += f"📝 Примечание: {r['comment']}\n"

        text += f"\n\n"
        
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
    msg = bot.send_message(chat_id, "Введите дату рождения:")
    bot.register_next_step_handler(msg, reg_birthday)
    
def reg_birthday(message):
    chat_id = message.chat.id
    user_states[chat_id]["birthday"] = message.text.strip()
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
    markup.add("Обычный")
    markup.add("Безлимит")
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
                "INSERT INTO clients (name, birthday, phone, parent_name, parent_phone, start_date, finish_date, how_much_was_price, training_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data["name"], data['birthday'], data["phone"], data["parent_name"], data["parent_phone"],
                 start_date.strftime("%d.%m.%Y"), finish_date.strftime("%d.%m.%Y"), data["how_much_was_price"], data["training_type"])
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
    user = auto_login_user(message)  # Без декоратора! Это просто функция запроса к БД
    if user:
        markup = telebot.types.InlineKeyboardMarkup()
        btn1 = telebot.types.InlineKeyboardButton("Мой абонемент", callback_data="my_subscription")
        btn2 = telebot.types.InlineKeyboardButton("Связаться с администратором", callback_data="contact_admin")
        markup.row(btn1, btn2)
        bot.send_message(message.chat.id, f'✅ Вы успешно вошли, {user["name"]}!', reply_markup=markup)
    else:
        msg = bot.send_message(message.chat.id, f'Добро пожаловать, {message.from_user.first_name}! Введите свой номер телефона указанный при регистрации.')
        bot.register_next_step_handler(msg, login_user)


def auto_login_user(message):
    conn, cur = db_connect()
    cur.execute("SELECT * FROM clients WHERE telegram_username = ?", (message.from_user.username,))  # execute, не excute! И кортеж!
    user = cur.fetchone()
    db_close_connect(conn)
    return user


def login_user(message):
    phone = message.text.strip()
    conn, cur = db_connect()
    cur.execute("SELECT * FROM clients WHERE phone = ? OR parent_phone = ?", (phone, phone))
    user = cur.fetchone()
    db_close_connect(conn)

    if user:
        markup = telebot.types.InlineKeyboardMarkup()
        btn1 = telebot.types.InlineKeyboardButton("Мой абонемент", callback_data="my_subscription")
        btn2 = telebot.types.InlineKeyboardButton("Связаться с администратором", callback_data="contact_admin")
        markup.row(btn1, btn2)
        bot.send_message(message.chat.id, f'✅ Вы успешно вошли, {user["name"]}!', reply_markup=markup)
        
        # Сохраняем telegram данные
        conn, cur = db_connect()
        cur.execute("UPDATE clients SET telegram_id = ?, telegram_username = ? WHERE id = ?", 
                    (message.chat.id, message.from_user.username, user["id"]))
        db_close_connect(conn, save=True)
    else:
        bot.send_message(message.chat.id, '❌ Пользователь с таким номером не найден. Пожалуйста, свяжитесь с администратором.')


def choose_user_function(message):
    bot.send_message(message.chat.id, "Выберите функцию.")
    
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "my_subscription":
        conn, cur = db_connect()
        cur.execute("SELECT start_date, finish_date, is_expiried FROM clients WHERE telegram_id = ?", (call.message.chat.id,))
        user = cur.fetchone()
        db_close_connect(conn)

        if user:
            abonement_status = "✔️ Активен" if user['is_expiried'] == 0 else "❌ Истёк"
            
            text = (
                f"📅 Дата оплаты абонемента: {user['start_date']}\n"
                f"📅 Дата окончанния абонемента: {user['finish_date']}\n"
                f"📅 Cтатус абонемента : {abonement_status}\n"
            )
            bot.send_message(call.message.chat.id, text)
        else:
            bot.send_message(call.message.chat.id, "❌ Пользователь не найден.")
    
    elif call.data == "contact_admin":
        bot.send_message(call.message.chat.id, f"Свяжитесь с администратором:\n @nfllex, @Nokortt, @Mrrrimp")
    
    bot.answer_callback_query(call.id)

# --------------------------------------------------------------------------
# START POLLING
# --------------------------------------------------------------------------

subscription_thread = threading.Thread(target=check_subscriptions, daemon=True)
subscription_thread.start()

bot.infinity_polling()
