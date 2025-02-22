import logging
from itertools import count
from logging.handlers import RotatingFileHandler
import telebot
import time
import os
import json
import threading
import subprocess
from telebot import apihelper
from datetime import datetime
from telebot import types

# Настройка RotatingFileHandler
handler = RotatingFileHandler(
    'bot.log',
    maxBytes=0.5 * 1024 * 1024,  # 0.5 MB
    backupCount=2
)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Создание логгера
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)


# Обработка формата данных - конвертирование в гб, мб, кб
def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024


# Установите свой токен от BotFather
TOKEN = '6761385263:AAH5u0SdH3AhqzovX8S01Mg4-TFA4Ve0p9w1'
bot = telebot.TeleBot(TOKEN)

# Пути к файлам
STATUS_LOG_PATH = '/var/log/openvpn/status.log'
STATUS_UPD_LOG_PATH = '/var/log/openvpn/udp_status.log'  # Новый путь к файлу
STATS_FILE_PATH = 'user_traffic_stats.json'
DOWNLOAD_FOLDER = 'downloaded_files'
LOCAL_PORT = 6000
# Список разрешенных пользователей
allowed_users = [1181564151, 488287488]

# Интервал обновления данных (в секундах)
UPDATE_INTERVAL = 60  # например, 60 секунд (1 минута)


# Функция для загрузки предыдущих данных трафика из файла
def load_previous_stats(server_name=None):
    try:
        stats_path = STATS_FILE_PATH if not server_name else os.path.join(DOWNLOAD_FOLDER, f"{server_name}_stats.json")
        if os.path.exists(stats_path):
            with open(stats_path, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logging.error(f"Error loading previous stats: {e}")
        return {}


# Функция для сохранения обновленных данных трафика в файл
def save_stats(stats, server_name=None):
    try:
        stats_path = STATS_FILE_PATH if not server_name else os.path.join(DOWNLOAD_FOLDER, f"{server_name}_stats.json")
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=4)
        logging.info('Stats saved successfully')
    except Exception as e:
        logging.error(f"Error saving stats: {e}")


# Функция для парсинга файла status.log
def parse_status_log(server_name=None, log_type='status'):
    log_path = STATUS_LOG_PATH if log_type == 'status' else STATUS_UPD_LOG_PATH
    if server_name:
        log_path = os.path.join(DOWNLOAD_FOLDER, f"{server_name}.log")

    if not os.path.exists(log_path):
        error_message = f"Status log file not found for {server_name or 'local'} server"
        logging.error(error_message)
        return error_message

    previous_stats = load_previous_stats(server_name)
    current_stats = {}
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as log_file:
            lines = log_file.readlines()
    except Exception as e:
        error_message = f"Error reading log file: {str(e)}"
        logging.error(error_message)
        return error_message

    user_data_section = False

    for user in previous_stats:
        previous_stats[user]['status'] = 'offline'

    for line in lines:
        if line.startswith("ROUTING TABLE"):
            user_data_section = False

        if user_data_section:
            data = line.split(',')
            if len(data) >= 5:
                username = data[0]

                if username == "UNDEF":
                    continue

                current_received = int(data[2])
                current_sent = int(data[3])

                if username in previous_stats:
                    prev_received = previous_stats[username]['received']
                    prev_sent = previous_stats[username]['sent']
                    prev_total_received = previous_stats[username].get('total_received', 0)
                    prev_total_sent = previous_stats[username].get('total_sent', 0)

                    diff_received = max(current_received - prev_received, 0)
                    diff_sent = max(current_sent - prev_sent, 0)

                    total_received = prev_total_received + diff_received
                    total_sent = prev_total_sent + diff_sent
                else:
                    total_received = current_received
                    total_sent = current_sent

                current_stats[username] = {
                    'received': current_received,
                    'sent': current_sent,
                    'total_received': total_received,
                    'total_sent': total_sent,
                    'last_seen': current_time,
                    'status': 'online'
                }

        if line.startswith("Common Name,Real Address,Bytes Received,Bytes Sent"):
            user_data_section = True

    previous_stats.update(current_stats)
    save_stats(previous_stats, server_name)
    logging.info(f'Status log parsed successfully for {server_name or "local"} server')
    return previous_stats


# Фоновая функция для автоматического обновления данных
def auto_update_stats():
    while True:
        try:
            parse_status_log(log_type='status')
            parse_status_log(log_type='status_upd')
            logging.info('Auto-update completed successfully')
        except Exception as e:
            logging.error(f"Error during auto-update: {e}")
        threading.Event().wait(UPDATE_INTERVAL)


threading.Thread(target=auto_update_stats, daemon=True).start()


# Функция для приема файла через ncat и сохранения его в указанную папку
def receive_file_with_custom_name(local_folder, local_port):
    try:
        result = subprocess.run(
            ['ncat', '-l', str(local_port), '-w', '60'],
            stdout=subprocess.PIPE,
            timeout=60  # Установить тайм-аут для завершения команды, если данных нет
        )
        file_data = result.stdout
        if not file_data:
            logging.error("Received empty file data.")
            return None

        header_text, _, remaining_data = file_data.partition(b' ')
        header_text = header_text.decode().strip()

        if not header_text:
            logging.error("Received empty header text.")
            return None

        file_name = f"{header_text}.log"
        local_file_path = os.path.join(local_folder, file_name)

        if file_name != 'GET.log' or 'CONNECT.log':
            with open(local_file_path, 'wb') as f:
                f.write(remaining_data)
        else:
            logging.error("Received empty GET file not saved")
            return None

        logging.info(f"Файл был успешно получен и сохранен как {local_file_path}.")
        parse_status_log(header_text)
        return file_name
    except Exception as e:
        logging.error(f"Ошибка при получении файла на порту {local_port}: {str(e)}")
        return None


def receive_files_loop():
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    while True:
        logging.info(f"Ожидание файла на порту {LOCAL_PORT}...")
        receive_file_with_custom_name(DOWNLOAD_FOLDER, LOCAL_PORT)


threading.Thread(target=receive_files_loop, daemon=True).start()


# Команда для получения статистики по трафику
@bot.message_handler(commands=['traffic'])
def send_traffic_stats(message):
    try:
        stats = parse_status_log(log_type='status')
        if isinstance(stats, str):
            bot.reply_to(message, stats)
            return

        online_users = {user: data for user, data in stats.items() if data['status'] == 'online' and user != 'UNDEF'}
        offline_users = {user: data for user, data in stats.items() if data['status'] == 'offline' and user != 'UNDEF'}

        sorted_online_users = dict(sorted(online_users.items()))
        sorted_offline_users = dict(sorted(offline_users.items()))

        response = "Traffic Statistics:\n\n"

        for user, data in sorted_online_users.items():
            received = format_bytes(data['total_received'])
            sent = format_bytes(data['total_sent'])
            response += f"✅ <b>{user}</b>: {received} / {sent}\n\n"
#            response += f"User: {user} ✅\n"
#            response += f"Total Received: {received}\n"
#            response += f"Total Sent: {sent}\n\n"

        for user, data in sorted_offline_users.items():
            received = format_bytes(data['total_received'])
            sent = format_bytes(data['total_sent'])
            response += f"❌ <b>{user}</b>: {received} / {sent}\n"
#            response += f"User: {user} ❌\n"
#            response += f"Total Received: {received}\n"
#            response += f"Total Sent: {sent}\n"
            response += f"Last Seen: {data['last_seen']}\n\n"

        if message.from_user.id in allowed_users:
            send_long_message(message.chat.id, response)
#            bot.reply_to(message, response)
        else:
            bot.reply_to(message, 'Нет доступа к боту')
        logging.info('Traffic stats sent successfully')
    except Exception as e:
        logging.error(f"Error sending traffic stats: {e}")


# Команда для отображения кнопок
@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        buttons = []
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
        traffic_button = types.KeyboardButton("/traffic")
        buttons.append(traffic_button)

        if os.path.exists(DOWNLOAD_FOLDER):
            for file in sorted(os.listdir(DOWNLOAD_FOLDER)):
                if file.endswith(".log"):
                    server_button = types.KeyboardButton(file.replace(".log", ""))
                    buttons.append(server_button)

        # Добавляем кнопку для status_upd.log
        status_upd_button = types.KeyboardButton("/status_upd")
        buttons.append(status_upd_button)

        if buttons:
            markup.add(*buttons)

        bot.send_message(message.chat.id, "Welcome to the Traffic Monitor Bot. Choose a server or get traffic stats:",
                         reply_markup=markup)
        logging.info('Welcome message sent')
    except Exception as e:
        logging.error(f"Error sending welcome message: {e}")


# Функция для отправки длинных сообщений частями
def send_long_message(chat_id, text):
    max_message_length = 4096
    for i in range(0, len(text), max_message_length):
        bot.send_message(chat_id, text[i:i+max_message_length], parse_mode="HTML")

# Обработка нажатия на кнопку сервера
@bot.message_handler(func=lambda message: message.text in [f.replace(".log", "") for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith(".log")])
def handle_server_callback(message):
    try:
        server_name = message.text
        stats = parse_status_log(server_name)
        file_info = os.path.join(DOWNLOAD_FOLDER, f"{server_name}.log")
        #os.stat(file_info,)

        if isinstance(stats, str):
            bot.send_message(message.chat.id, stats)
            return

        online_users = {user: data for user, data in stats.items() if data['status'] == 'online' and user != 'UNDEF'}
        offline_users = {user: data for user, data in stats.items() if data['status'] == 'offline' and user != 'UNDEF'}

        sorted_online_users = dict(sorted(online_users.items()))
        sorted_offline_users = dict(sorted(offline_users.items()))

        response = f"Traffic statistics for {server_name}:\n\n"

        for user, data in sorted_online_users.items():
            received = format_bytes(data['total_received'])
            sent = format_bytes(data['total_sent'])
            response += f"✅ <b>{user}</b>: {received} / {sent}\n\n"
            #response += f"Total: {received} / {sent}\n\n"
            #response += f"Total Sent: {sent}\n\n"

        for user, data in sorted_offline_users.items():
            received = format_bytes(data['total_received'])
            sent = format_bytes(data['total_sent'])
            response += f"❌ <b>{user}</b>: {received} / {sent}\n"
            #response += f"Total: {received} / {sent}\n"
            #response += f"Total Sent: {sent}\n"
            response += f"Last Seen: {data['last_seen']}\n\n"

        response += f"Total online users: <b> {len(online_users.items())} </b> \n"
        #response += f"Last upd: <b> {time.ctime(os.stat(file_info).st_mtime)} </b> "
        response += f"Last upd: <b> {time.strftime('%d.%m.%Y %H:%M:%S', time.localtime(os.stat(file_info).st_mtime))}</b>"
        if message.from_user.id in allowed_users:
            send_long_message(message.chat.id, response)
            logging.info(f'Server stats for {server_name} sent successfully')
        else:
            bot.send_message(message.chat.id, "У вас нет доступа к этому боту!")
    except Exception as e:
        logging.error(f"Error sending server stats: {e}")
        bot.send_message(message.chat.id, "Error loading server stats")


# Обработка команды /status_upd
@bot.message_handler(commands=['status_upd'])
def send_status_upd_stats(message):
    try:
        stats = parse_status_log(log_type='status_upd')
        if isinstance(stats, str):
            bot.reply_to(message, stats)
            return

        online_users = {user: data for user, data in stats.items() if data['status'] == 'online' and user != 'UNDEF'}
        offline_users = {user: data for user, data in stats.items() if data['status'] == 'offline' and user != 'UNDEF'}

        sorted_online_users = dict(sorted(online_users.items()))
        sorted_offline_users = dict(sorted(offline_users.items()))

        response = "Traffic Statistics (status_upd.log):\n\n"

        for user, data in sorted_online_users.items():
            received = format_bytes(data['total_received'])
            sent = format_bytes(data['total_sent'])
            response += f"✅ <b>{user}</b>: {received} / {sent}\n\n"
#            response += f"User: {user} ✅\n"
#            response += f"Total Received: {received}\n"
#            response += f"Total Sent: {sent}\n\n"

        for user, data in sorted_offline_users.items():
            received = format_bytes(data['total_received'])
            sent = format_bytes(data['total_sent'])
            response += f"❌ <b>{user}</b>: {received} / {sent}\n"
#            response += f"User: {user} ❌\n"
#            response += f"Total Received: {received}\n"
#            response += f"Total Sent: {sent}\n"
            response += f"Last Seen: {data['last_seen']}\n\n"

        if message.from_user.id in allowed_users:
            send_long_message(message.chat.id, response)
#            bot.reply_to(message, response)
        else:
            bot.reply_to(message, 'Нет доступа к боту')
        logging.info('Traffic stats (status_upd.log) sent successfully')
    except Exception as e:
        logging.error(f"Error sending traffic stats (status_upd.log): {e}")


def start_bot():
    while True:
        try:
            logging.info('Bot started polling')
            bot.polling(none_stop=True, interval=1, timeout=20)
        except apihelper.ApiTelegramException as e:
            logging.error(f"ApiTelegramException occurred: {e}")
            time.sleep(15)  # Пауза перед повторной попыткой
        except Exception as e:
            logging.error(f"Unexpected error occurred: {e}")
            time.sleep(15)  # Пауза перед повторной попыткой


if __name__ == '__main__':
    start_bot()
