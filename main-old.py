import telebot
import sqlite3

bot = telebot.TeleBot('8531903826:AAFSlQOtBz6vv2phMza6Q-NTqVYt1xr-iu4')

name = ''
phone = ''
parrent_name = ''
parrent_phone = ''

def send_long(chat_id, text):
    for i in range(0, len(text), 4000):
        bot.send_message(chat_id, text[i:i+4000], parse_mode="Markdown")

def init_db():
    conn = sqlite3.connect("clients.sql")
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            parrent_name TEXT,
            parrent_phone TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db() 
# admin functions
@bot.message_handler(commands=['admin'])
def admin(message):
    msg = bot.send_message(message.chat.id, 'Вход в админ панель, введите пароль')
    bot.register_next_step_handler(msg, sign_in_admin)

def sign_in_admin(message):
    password = message.text.strip()
    if password == 'admin123':
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = telebot.types.KeyboardButton("Просмотреть всех пользователей")
        btn2 = telebot.types.KeyboardButton("Регестрация пользователя")
        markup.row(btn1, btn2)
        msg = bot.send_message(message.chat.id, 'Добро пожаловать в админ панель!', reply_markup=markup)
        bot.register_next_step_handler(message, choose_admin_function)
    else:
        bot.send_message(message.chat.id, 'Неверный пароль. Доступ запрещен.')

def choose_admin_function(message):
    if message.text == "Просмотреть всех пользователей":
        conn = sqlite3.connect("clients.sql")
        cur = conn.cursor()
        cur.execute("SELECT * FROM clients")
        clients = cur.fetchall()
        info = ''
        for el in clients:
            info += f'ID: {el[0]}, Name: {el[1]}, Pass: {el[2]}\n'
        cur.close()
        conn.close()
        send_long(message.chat.id, info)
    elif message.text == "Регестрация пользователя":
        bot.register_next_step_handler(message, start_register)
    else:
        bot.send_message(message.chat.id, 'Неизвестная команда. Пожалуйста, выберите одну из кнопок.')
# register user functions

def start_register(message):
    bot.send_message(message.chat.id, 'Начинаем регестрацию нового пользователя. Введите имя:')
    global name
    name = message.text.strip()
    bot.register_next_step_handler(message, register_step_2)

def register_step_2(message):
    bot.send_message(message.chat.id, 'Введите номер телефона')
    global phone
    phone = message.text.strip()
    bot.register_next_step_handler(message, register_step_3)

def register_step_3(message):
    bot.send_message(message.chat.id, 'Введите ФИО родителя')
    global parrent_name
    parrent_name = message.text.strip()
    bot.register_next_step_handler(message, register_step_4)

def register_step_4(message):
    bot.send_message(message.chat.id, 'Введите номер телефона родителя')
    global parrent_phone
    parrent_phone = message.text.strip()
    bot.register_next_step_handler(message, register_finish)

def register_finish(message):
    conn = sqlite3.connect('clients.sql')
    cur = conn.cursor()

    cur.execute('''
        INSERT INTO clients (name, phone, parrent_name, parrent_phone)
        VALUES (?, ?, ?, ?)
    ''', (name, phone, parrent_name, parrent_phone))

    conn.commit()
    cur.close()
    conn.close()

    bot.send_photo(message.chat.id, open('./test.jpg', 'rb'))
    bot.send_message(message.chat.id, 'Регистрация завершена!')


# start bot
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, 'Добро пожаловать!')
   
def user_pass(message):
    password = message.text.strip()
    conn = sqlite3.connect('clients.sql')    
    cur = conn.cursor()

    cur.execute("INSERT INTO clients (name, pass) VALUES ('%s', '%s')" % (name, password))
    conn.commit()   
    cur.close()
    conn.close()
    
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton('Список пользователей', callback_data='clients'))
    bot.send_message(message.chat.id, 'Вы успешно зарегистрированы!', reply_markup=markup)

@bot.message_handler(commands=['db'])
def db(message):
    conn = sqlite3.connect("clients.sql")
    cur = conn.cursor()

    cur.execute("SELECT * FROM clients")
    clients = cur.fetchall()
    
    info = ''
    for el in clients:
        info += f'ID: {el[0]}, Name: {el[1]}, Pass: {el[2]}\n'

    cur.close()
    conn.close()

    bot.send_message(message.chat.id, info)

bot.infinity_polling()

# import json
# from telebot import types

# bot = telebot.TeleBot('8531903826:AAFSlQOtBz6vv2phMza6Q-NTqVYt1xr-iu4')

# # # ---------- Функция для отправки длинных сообщений ----------
# def send_long(chat_id, text):
#     for i in range(0, len(text), 4000):
#         bot.send_message(chat_id, text[i:i+4000])

# @bot.message_handler(commands=['start'])
# def start(message):
#     markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
#     btn1 = types.KeyboardButton("Перейти на сайт")
#     btn2 = types.KeyboardButton("функция 2")
#     btn3 = types.KeyboardButton("функция 3")
#     markup.row(btn1)
#     markup.row(btn2, btn3)
#     file = open('./test.jpg', 'rb')
#     bot.send_photo(message.chat.id, file, reply_markup=markup)
#     bot.register_next_step_handler(message, on_click)

# def on_click(message):
#     if message.text == "Перейти на сайт":
#         bot.send_message(message.chat.id, 'Вот ссылка на сайт: https://google.com')
#     elif message.text == "функция 2":
#         bot.send_message(message.chat.id, 'Вы выбрали функцию 2')
#     elif message.text == "функция 3":
#         bot.send_message(message.chat.id, 'Вы выбрали функцию 3')
#     else:
#         bot.send_message(message.chat.id, 'Неизвестная команда. Пожалуйста, выберите одну из кнопок.')


# @bot.message_handler(commands=['hello' ,'main'])
# def main(message):
#     markup = types.InlineKeyboardMarkup()
#     btn1 = types.InlineKeyboardButton("Перейти на сайт", url="https://google.com")
#     btn2 = types.InlineKeyboardButton("функция 2", callback_data="func2")
#     btn3 = types.InlineKeyboardButton("функция 3", callback_data="func3")
#     markup.row(btn1, btn2)
#     markup.row(btn3)
#     bot.send_message(message.chat.id, f'Привет, {message.from_user.first_name} {message.from_user.last_name}! Добро пожаловать в главное меню бота.', reply_markup=markup)


# @bot.callback_query_handler(func=lambda call: True)
# def callback_query(call):
#     if call.data == "func2":
#         bot.answer_callback_query(call.id, "Вы нажали кнопку функции 2")
#     elif call.data == "func3":
#         bot.answer_callback_query(call.id, "Вы нажали кнопку функции 3")


# @bot.message_handler(commands=['debug'])
# def debug(message):
#     raw = message.json                 
#     formatted = json.dumps(raw, ensure_ascii=False, indent=2)
#     send_long(message.chat.id, formatted) 


# @bot.message_handler()
# def info(message):
#     if message.text.lower() == 'привет' :
#         bot.send_message(message.chat.id, f'Привет, {message.from_user.first_name} {message.from_user.last_name}!')
#     elif message.text.lower() == 'id':
#         bot.reply_to(message, f'Ваш ID: {message.from_user.id}')

# bot.infinity_polling()