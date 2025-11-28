import telebot
import sqlite3

bot = telebot.TeleBot('8531903826:AAFSlQOtBz6vv2phMza6Q-NTqVYt1xr-iu4')

# --------------------------------------------------------------------------
# INIT DB
# --------------------------------------------------------------------------


def init_db():
    conn = sqlite3.connect("clients.sql")
    cur = conn.cursor()
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
    conn.commit()
    conn.close()

init_db()

# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------

# отправка длинных сообщений
def send_long(chat_id, text):
    last_msg = None
    for i in range(0, len(text), 4000):
        last_msg = bot.send_message(chat_id, text[i:i+4000], parse_mode="Markdown")
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
    else:
        msg = bot.send_message(message.chat.id, "Неизвестная команда. Выберите кнопку.")
        bot.register_next_step_handler(msg, choose_admin_function)


# --------------------------------------------------------------------------
# SHOW USERS
# --------------------------------------------------------------------------

def show_all_users(message):
    conn = sqlite3.connect("clients.sql")
    cur = conn.cursor()
    cur.execute("SELECT * FROM clients")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        msg = bot.send_message(message.chat.id, "Пользователей пока нет.")
        bot.register_next_step_handler(msg, choose_admin_function)
        return

    text = "📋 *Список пользователей:*\n\n"
    for r in rows:
        text += (
            f"🆔 ID: {r[0]}\n"
            f"👤 Имя: {r[1]}\n"
            f"📱 Телефон: {r[2]}\n"
            f"👨‍👩‍👧 Родитель: {r[3]}\n"
            f"📞 Тел. родителя: {r[4]}\n\n"
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

    conn = sqlite3.connect("clients.sql")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO clients (name, phone, parent_name, parent_phone) VALUES (?, ?, ?, ?)",
        (data["name"], data["phone"], data["parent_name"], data["parent_phone"])
    )
    conn.commit()
    conn.close()

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
