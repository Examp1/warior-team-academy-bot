import telebot
import sqlite3

bot = telebot.TeleBot('8531903826:AAFSlQOtBz6vv2phMza6Q-NTqVYt1xr-iu4')

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
            telegram_id INTEGER,
            username TEXT,
            name TEXT,
            phone TEXT,
            parent_name TEXT,
            parent_phone TEXT,
            role TEXT DEFAULT 'user',
            created_at TEXT,
            last_active TEXT
        )
    ''')
    db_close_connect(conn, save=True)

init_db()



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

@bot.message_handler(commands=['admin'])
def admin(message):
    ADMIN_IDS = [342465611, 289956357, 6014645981, 1038443281]  # список ID администраторов
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
            f"🆔 ID: {r[0]}\n"
            f"👤 Имя: {r[3]}\n"
            f"📱 Телефон: {r[4]}\n"
            f"👨‍👩‍👧 Родитель: {r[5]}\n"
            f"📞 Тел. родителя: {r[6]}\n"
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
    
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=inline_markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chname_"))
def handle_edit_name(call):
    user_id = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, "Введите новое имя:")
    bot.register_next_step_handler(msg, save_new_value, user_id, "name")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chphone_"))
def handle_edit_phone(call):
    user_id = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, "Введите новый телефон:")
    bot.register_next_step_handler(msg, save_new_value, user_id, "phone")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chparentphone_"))
def handle_edit_parent_phone(call):
    user_id = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, "Введите телефон родителя:")
    bot.register_next_step_handler(msg, save_new_value, user_id, "parent_phone")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chparent_"))
def handle_edit_parent(call):
    user_id = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, "Введите имя родителя:")
    bot.register_next_step_handler(msg, save_new_value, user_id, "parent_name")
    bot.answer_callback_query(call.id)

# Универсальная функция сохранения
def save_new_value(message, user_id, field):
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
            f"🆔 ID: {r[0]}\n"
            f"👤 Имя: {r[3]}\n"
            f"📱 Телефон: {r[4]}\n"
            f"👨‍👩‍👧 Родитель: {r[5]}\n"
            f"📞 Тел. родителя: {r[6]}\n\n"
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

    data = user_states[chat_id]

    conn, cur = db_connect()
    cur.execute(
        "INSERT INTO clients (name, phone, parent_name, parent_phone) VALUES (?, ?, ?, ?)",
        (data["name"], data["phone"], data["parent_name"], data["parent_phone"])
    )
    db_close_connect(conn, save=True)

    bot.send_message(chat_id, f'✅ Регистрация {user_states[chat_id]["name"]} - {user_states[chat_id]["phone"]} завершена!')

    del user_states[chat_id]  # очищаем временное состояние пользователя
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

bot.infinity_polling()
