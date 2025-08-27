import urllib.request
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler
import logging
import textwrap
import re
import json
import os
from groups_cleaned import GROUPS  # Импорт данных о группах из отдельного файла
from preps import PREPS
import asyncio
import urllib
import datetime

# ========== НАСТРОЙКИ ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ========== КОНСТАНТЫ ==========
# верхняя - основная, нижний токен - тестовый
# TOKEN = "7962333071:AAF0wlrEKS9MVbgym_Ws9erYUzucgjVG52w" 
TOKEN = "8039378791:AAE8p6naztH88Me9VsvX-5YlWCUQGUyP-8I"
WAITING_FOR_GROUP = 1  # Состояние ожидания ввода группы
WAITING_FOR_BROADCAST = 2  # Состояние ожидания ввода сообщения для рассылки
WAITING_FOR_TICKET = 3
WAITING_FOR_PREP = 4

reply_keyboard = [[KeyboardButton("Получить расписание")]]
markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

# Заголовки для HTTP-запросов
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
    'Referer': 'https://coworking.tyuiu.ru/',
    "Connection": "keep-alive"
}

# Цветовая схема для изображения расписания
COLORS = {
    'header_bg': (53, 122, 183),      # Цвет фона заголовка
    'first_col_bg': (217, 237, 247),  # Цвет фона первых столбцов
    'text': (0, 0, 0),                # Основной цвет текста
    'border': (100, 100, 100),        # Цвет границ
    'white': (255, 255, 255)          # Белый цвет
}

# Цвета и описания для специальных типов занятий
CLASS_COLORS = {
    'zamena': "#EEDA6C",              # Замены - золотой
    'head_urok_session': "#DF9674FF",             # Сессия - томатный
    'event': '#FA8072',               # Мероприятия - светло-коралловый
    'head_urok_praktik': '#c0d5fa',   # Практика - светло-голубой
    'gia': '#9370DB',                 # ГИА - средне-фиолетовый
    'kanik': '#98FB98',               # Каникулы - бледно-зеленый
    'head_urok_block': '#D3D3D3',     # Неактивный период - светло-серый
    'other_control': "#F77963FF",
    'zachet': "#F77963FF",
    'difzachet': "#E0573FFF",
    'consultation': "#F77963FF",
    'ekzamen': "#E0573FFF",
    't_urok_drob': "drob"

}

CLASS_COLORS_CONS = {
    'nechet': "#D5932F",
    'chet': "#3F8D2A"
}

CLASS_DESCRIPTIONS = {
    'zamena': 'замены',
    'head_urok_session': 'сессия',
    'event': 'праздничные дни',
    'head_urok_praktik': 'практика',
    'gia': 'ГИА',
    'kanik': 'каникулы',
    'head_urok_block': 'неактивный период'
}

CLASS_DESCRIPTIONS_CONS = {
    'nechet': 'Нечётная неделя',
    'chet': 'Чётная неделя'
}

# Настройки для вложенных таблиц
NESTED_TABLE_SETTINGS = {
    'show_borders': False,    # Не показывать границы вложенных таблиц
    'padding': 0,             # Отступ от краев родительской ячейки
    'min_col_width': 70,      # Минимальная ширина колонки
    'font_size': 12,          # Размер шрифта
    'line_spacing': 12,       # Межстрочный интервал
    'border_offset': 5,       # Отступ текста от границ
    'header_height': 65,      # Высота заголовочной строки
    'merge_lines': False       # Объединять строки из разных ячеек
}

# ========== НАСТРОЙКИ АДМИНИСТРАТОРА ==========
ADMIN_IDS = [1805861153]  # Замените на ваш Telegram ID
BROADCAST_LIMIT = 10  # Максимальное количество сообщений в минуту для рассылки

# ========== ДОБАВЛЕННЫЕ ФУНКЦИИ ДЛЯ АДМИНИСТРАТОРА ==========
def is_admin(user_id):
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику бота"""
    
    chat_data = load_chat_data()
    
    # Считаем статистику
    total_users = len([cid for cid in chat_data.keys() if not str(cid).startswith('-100')])
    total_groups = len([cid for cid in chat_data.keys() if str(cid).startswith('-100')])
    total_chats = total_users + total_groups
    
    # Получаем список всех групп с количеством чатов
    group_stats = {}
    for group_id in chat_data.values():
        group_stats[group_id] = group_stats.get(group_id, 0) + 1
    
    # Формируем сообщение
    message = (
        f"📊 Статистика бота:\n"
        f"👤 Всего пользователей: {total_users}\n"
        f"👥 Всего групп/каналов: {total_groups}\n"
        f"💬 Всего чатов: {total_chats}\n\n"
        f"📌 Распределение по группам:\n"
    )
    
    for group_id, count in group_stats.items():
        group_name = next((g['name'] for g in GROUPS.values() if g['id'] == group_id), "Неизвестная группа")
        message += f"  - {group_name}: {count} чат(ов)\n"
    
    await update.message.reply_text(message)

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс рассылки"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return
    
    await update.message.reply_text(
        "Введите сообщение для рассылки. Вы можете использовать разметку Markdown.\n"
        "Формат: \n`текст` - для личных сообщений\n"
        "`группы текст` - для групповых чатов\n"
        "`все текст` - для всех чатов\n\n"
        "Или отправьте /cancel для отмены."
    )
    return WAITING_FOR_BROADCAST

async def broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод сообщения для рассылки"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END
    
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("Рассылка отменена.")
        return ConversationHandler.END
    
    # Определяем тип рассылки
    target = "all"
    message = text
    
    if text.startswith('личные '):
        target = "users"
        message = text[7:]
    elif text.startswith('группы '):
        target = "groups"
        message = text[7:]
    elif text.startswith('все '):
        target = "all"
        message = text[4:]
    
    chat_data = load_chat_data()
    
    if target == "users":
        chat_ids = [int(cid) for cid in chat_data.keys() if not str(cid).startswith('-100')]
    elif target == "groups":
        chat_ids = [int(cid) for cid in chat_data.keys() if str(cid).startswith('-100')]
    else:
        chat_ids = [int(cid) for cid in chat_data.keys()]
    
    total = len(chat_ids)
    success = 0
    failed = 0
    
    await update.message.reply_text(f"Начинаю рассылку для {total} чатов...")
    
    # Рассылаем с ограничением скорости
    for i, chat_id in enumerate(chat_ids):
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown"
            )
            success += 1
            
            # Ограничение скорости (не более BROADCAST_LIMIT сообщений в минуту)
            if (i + 1) % BROADCAST_LIMIT == 0:
                await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"Ошибка при отправке в {chat_id}: {str(e)}")
            failed += 1
            continue
    
    await update.message.reply_text(
        f"Рассылка завершена!\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибок: {failed}"
    )
    
    return ConversationHandler.END

async def ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс создания тикета"""
    await update.message.reply_text(
        "Опишите проблему или вопрос, который вы хотите отправить администраторам.\n"
        "Вы можете приложить скриншот.\n\n"
        "Или отправьте /cancel для отмены."
    )
    return WAITING_FOR_TICKET

async def ticket_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод тикета"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    if update.message.text == '/cancel':
        await update.message.reply_text(
        "Отправка сообщения отменена"
    )
        return ConversationHandler.END
    if update.message.photo:
        # Если есть фото, сохраняем file_id
        photo_id = update.message.photo[-1].file_id
        text = update.message.caption or "Без описания"
    else:
        photo_id = None
        text = update.message.text
    
    # Формируем сообщение для администратора
    admin_message = (
        f"🚨 Новый тикет от пользователя:\n"
        f"👤 ID: {user.id}\n"
        f"📝 Имя: {user.full_name}\n"
        f"✉️ Сообщение:\n{text}"
    )
    
    # Отправляем всем администраторам
    for admin_id in ADMIN_IDS:
        try:
            if photo_id:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo_id,
                    caption=admin_message
                )
            else:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_message
                )
        except Exception as e:
            logging.error(f"Ошибка при отправке тикета администратору {admin_id}: {e}")
    
    await update.message.reply_text(
        "Ваше сообщение отправлено администраторам. Спасибо за обратную связь!"
    )
    
    return ConversationHandler.END

async def reply_to_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Позволяет администратору ответить на тикет"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /reply [ID пользователя] [сообщение]\n"
            "Пример: /reply 1234567 Ваша проблема решена"
        )
        return
    
    user_id = context.args[0]
    message = ' '.join(context.args[1:])
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✉️ Ответ от администратора:\n{message}"
        )
        await update.message.reply_text("Ответ отправлен пользователю.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при отправке: {str(e)}")

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ДАННЫМИ ПОЛЬЗОВАТЕЛЕЙ ==========
def load_chat_data():
    """Загружает данные о выбранных группах из файла"""
    if os.path.exists('chat_data.json'):
        with open('chat_data.json', 'r') as f:
            return json.load(f)
    return {}

def save_chat_data(data):
    """Сохраняет данные о выбранных группах в файл"""
    with open('chat_data.json', 'w') as f:
        json.dump(data, f)

# Загружаем данные о группах чатов
chat_groups = load_chat_data()

def get_chat_group(chat_id):
    """Возвращает данные о группе для указанного чата"""
    group_id = chat_groups.get(str(chat_id), 728)  # 728 - группа по умолчанию
    for group_data in GROUPS.values():
        if group_data['id'] == group_id:
            return group_data
    
def set_chat_group(chat_id, group_id):
    """Устанавливает группу для указанного чата"""
    for key, group_data in GROUPS.items():
        if group_data['id'] == group_id:
            chat_groups[str(chat_id)] = group_id
            save_chat_data(chat_groups)
            return

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def normalize_group_name(text):
    """Нормализует название группы для поиска (удаляет спецсимволы)"""
    return re.sub(r'[^\w]', '', text).lower()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет процесс чего-либо"""
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END
# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def change_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды для изменения группы"""
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
        "Пожалуйста, введите название вашей группы в любом формате:\n"
        "Например, КСт-22-(9)-1 или кст2291\n"
        "Или отправьте /cancel для отмены."
    )
        return WAITING_FOR_GROUP
    
    input_name = ' '.join(context.args)
    normalized = await normalize_group_name(input_name)
    
    selected = None
    for key, group in GROUPS.items():
        if key in normalized or normalized in key:
            selected = group
            break
    
    if selected:
        set_chat_group(chat_id, selected['id'])
        await update.message.reply_text(f"Группа изменена на {selected['name']}")
    else:
        await update.message.reply_text("Группа не найдена. Проверьте название.")

async def receive_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает введенное название группы"""
    chat_id = update.effective_chat.id
    input_name = update.message.text.strip()
    
    if input_name.lower() == '/cancel':
        await update.message.reply_text("Изменение группы отменено.")
        return ConversationHandler.END
    
    normalized = await normalize_group_name(input_name)
    
    selected = None
    for key, group in GROUPS.items():
        if key in normalized or normalized in key:
            selected = group
            break
    
    if selected:
        set_chat_group(chat_id, selected['id'])
        await update.message.reply_text(f"Группа изменена на {selected['name']}")
    else:
        await update.message.reply_text(
            "Группа не найдена. Проверьте название и попробуйте еще раз.\n"
            "Или отправьте /cancel для отмены."
        )
        return WAITING_FOR_GROUP
    
    return ConversationHandler.END

async def prep_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашивает ФИО преподавателя"""
    if not context.args:
        await update.message.reply_text(
            "Пожалуйста, введите ФИО преподавателя\n"
            "Например: Проданчук или Ольга Абайдулина или Татьяна Михайловна\n"
            "Или отправьте /cancel для отмены."
        )
        return WAITING_FOR_PREP
    
    # Отправляем временное сообщение
    temp_msg = await update.message.reply_text("Ищу преподавателя...")
    
    # Если имя препода передано сразу с командой (/prep Иванов)
    input_prep = ' '.join(context.args).lower()
    return await find_prep_and_show_schedule(update, context, input_prep, temp_msg)

async def prep_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает введенного преподавателя"""
    input_prep = update.message.text.strip().lower()
    
    if input_prep == '/cancel':
        await update.message.reply_text("Действие отменено.")
        return ConversationHandler.END
    
    # Отправляем временное сообщение
    temp_msg = await update.message.reply_text("Ищу преподавателя и получаю расписание...")
    
    # Проверяем, был ли показан список преподавателей
    if 'found_preps' in context.user_data:
        try:
            selected_num = int(input_prep) - 1
            found_preps = context.user_data['found_preps']
            
            if 0 <= selected_num < len(found_preps):
                prep = found_preps[selected_num]
                prep_name = f"{prep['second_name']} {prep['first_name']} {prep['third_name']}"
                
                # Получаем расписание
                img = await get_schedule_image(update.effective_chat.id, action=str(prep['id']))
                
                # Удаляем временное сообщение
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=temp_msg.message_id
                    )
                except Exception as e:
                    logging.error(f"Ошибка при удалении сообщения: {e}")
                
                # Отправляем результат
                if img:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=img,
                        caption=f"Расписание {prep_name}"
                    )
                else:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="Ошибка при получении расписания"
                    )
                
                del context.user_data['found_preps']
                return ConversationHandler.END
        except ValueError:
            pass
    
    # Если не был выбран номер из списка, выполняем обычный поиск
    return await find_prep_and_show_schedule(update, context, input_prep, temp_msg)

async def find_prep_and_show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                     search_query: str, temp_msg=None):
    """Ищет преподавателя и показывает расписание"""
    search_parts = search_query.split()
    found_preps = []
    
    for prep in PREPS:
        full_name = f"{prep['second_name']} {prep['first_name']} {prep['third_name']}".lower()
        match = all(part in full_name for part in search_parts)
        
        if match:
            found_preps.append(prep)
    
    if not found_preps:
        # Удаляем временное сообщение перед отправкой ошибки
        if temp_msg:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=temp_msg.message_id
                )
            except Exception as e:
                logging.error(f"Ошибка при удалении сообщения: {e}")
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Преподаватель не найден. Попробуйте ввести другое ФИО.\n"
                 "Или отправьте /cancel для отмены."
        )
        return WAITING_FOR_PREP
    
    if len(found_preps) > 1:
        # Удаляем временное сообщение перед отправкой списка
        if temp_msg:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=temp_msg.message_id
                )
            except Exception as e:
                logging.error(f"Ошибка при удалении сообщения: {e}")
        
        prep_list = "\n".join(
            f"{i+1}. {prep['second_name']} {prep['first_name']} {prep['third_name']}"
            for i, prep in enumerate(found_preps)
        )
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Найдено несколько преподавателей:\n{prep_list}\n"
                 "Пожалуйста, уточните запрос или введите номер из списка."
        )
        
        context.user_data['found_preps'] = found_preps
        return WAITING_FOR_PREP
    
    # Если найден ровно один преподаватель
    prep = found_preps[0]
    prep_name = f"{prep['second_name']} {prep['first_name']} {prep['third_name']}"
    
    # Удаляем временное сообщение
    if temp_msg:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=temp_msg.message_id
            )
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщения: {e}")
    
    # Получаем и отправляем расписание
    img = await get_schedule_image(update.effective_chat.id, action=str(prep['id']))
    if img:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=img,
            caption=f"Расписание {prep_name}",
            reply_markup=markup
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Ошибка при получении расписания"
        )
    
    return ConversationHandler.END

async def get_schedule_image(chat_id, action='group', cons_sched=False):
    """Получает изображение расписания для указанного чата"""
    if action and action.isdigit():
            def get_schedule_json(teacher_id: int, date: datetime.date, week_type: int = 1):
                timestamp = int(datetime.datetime.combine(date, datetime.time.min).timestamp())
                params = {
                    'task': 'get_urok',
                    'format': 'row',
                    'p': teacher_id,
                    'c': week_type,
                    'r': timestamp
                }
                response = requests.get(
                    'https://coworking.tyuiu.ru/shs/all_t/Model.php',
                    params=params,
                    headers={
                        'User-Agent': 'Mozilla/5.0',
                        'Referer': 'https://coworking.tyuiu.ru/shs/',
                    }
                )
                return response.json()


            # 📥 Получаем исходный HTML
            url = f'https://coworking.tyuiu.ru/shs/all_t/sh.php?action=prep&prep={action}&vr=1&count=6' \
                  '&shed[0]=28708&union[0]=0&year[0]=2025' \
                  '&shed[1]=28710&union[1]=0&year[1]=2025' \
                  '&shed[2]=28711&union[2]=0&year[2]=2025' \
                  '&shed[3]=28714&union[3]=0&year[3]=2025' \
                  '&shed[4]=28713&union[4]=0&year[4]=2025' \
                  '&shed[5]=28709&union[5]=0&year[5]=2025'

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://coworking.tyuiu.ru/shs/"
                }
            )

            with urllib.request.urlopen(req) as response_:
                html = response_.read().decode('cp1251')

            soup = BeautifulSoup(html, 'html.parser')

            # 🧠 Дата начала недели (например, Понедельник)
            start_date = datetime.date.today()
            teacher_id = action
            week_type = 0

            for day_offset in range(8):  # 6 дней в неделе
                date = start_date + datetime.timedelta(days=day_offset)
                if date.weekday() == 6:
                    continue
                data = get_schedule_json(teacher_id, date, week_type)

                for para_num, urok_data in data.items():
                    if not urok_data[1]:  # Пусто — пропускаем
                        continue
                    
                    cell_id = f'ur{para_num}{date.day}{date.month}'  # Пример: ur3236
                    cell = soup.find(id=cell_id)
                    if not cell:
                        continue
                    
                    if urok_data[0] == 'urok':
                        table_html = f"<table class='comm3 {urok_data[4]}'><tr><td><div class='disc'>{urok_data[1]}</div><div class='grupp'>{urok_data[2]}</div></td><td class='cabs'><div class='cab'>{urok_data[3]}</          div></td></tr></table>"
                    elif urok_data[0] == 'ekz':
                        table_html = f"<table class='comm3 {urok_data[4]}'><tr><td class='head_ekz'>{urok_data[1]}</td><td rowspan=2 class='cabs'><div class='cab'>{urok_data[3]}</div></td></          tr><tr><td><div class='disc'>{urok_data[2]}</div></td></tr></table>"
                    else:
                        table_html = ''

                    cell.clear()
                    cell.append(BeautifulSoup(table_html, 'html.parser'))

    else:
        # Оригинальный запрос для групп
        group_data = get_chat_group(chat_id)
        params = {
            'action': 'group',
            'union': 0,
            'sid': group_data['sid'],
            'gr': group_data['id'],
            'year': 2025,
            'vr': 0 if cons_sched else 1
        }
        response = requests.get(
            "https://coworking.tyuiu.ru/shs/all_t/sh.php",
            params=params,
            headers=HEADERS
        )
        
        if cons_sched:
            pattern = r'(</table>)(?!\s*</td>)'
            replacement = r'\1</td>'
            fixed_html = re.sub(pattern, replacement, response.text, flags=re.IGNORECASE)
            soup = BeautifulSoup(fixed_html, 'html.parser')
        else:
            soup = BeautifulSoup(response.text, 'html.parser')
    
    try:
        # Парсинг HTML
        
        header_div = soup.find(lambda tag: tag.name == 'div' and 
                      ("Расписание занятий группы" in tag.text or 
                       "Расписание занятий преподавателя" in tag.text or 
                       "Базовое расписание группы" in tag.text))

        header_text = ""
        if header_div:
            if "Расписание занятий группы" in header_div.text:
                header_text = "Расписание занятий группы"
            elif "Расписание занятий преподавателя" in header_div.text:
                header_text = "Расписание занятий преподавателя"
            elif "Базовое расписание группы" in header_div.text:
                header_text = "Базовое расписание группы"

            if header_div.find('b'):
                header_text += f" {header_div.find('b').get_text(strip=True)}"
        main_table = soup.find('table')
        
        if not main_table:
            return None

        # Загрузка шрифтов
        try:
            font_bold = ImageFont.truetype("arialbd.ttf", 14)
            font_regular = ImageFont.truetype("arial.ttf", 12)
            font_header = ImageFont.truetype("arialbd.ttf", 16)
            font_first_line = ImageFont.truetype("arialbd.ttf", 18)
            font_small = ImageFont.truetype("arial.ttf", NESTED_TABLE_SETTINGS['font_size'])
        except:
            font_bold = font_regular = font_header = font_small = ImageFont.load_default()

        def format_header(text):
            """Форматирует текст заголовка (извлекает дату, день недели и четность)"""
            date_match = re.search(r'\d{1,2}\.\d{1,2}\.\d{4}', text)
            day_match = re.search(r'(Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье)', text)
            parity_match = re.search(r'(Четная|Нечетная)', text)
            
            parts = []
            if date_match:
                parts.append(date_match.group(0))
            if day_match:
                parts.append(day_match.group(0))
            if parity_match:
                parts.append(parity_match.group(0))
            return '\n'.join(parts) if parts else text

        def calculate_table_size(table, level=0, parent_width=None):
            """Вычисляет размеры таблицы и ее столбцов/строк"""
            rows = table.find_all('tr', recursive=False)
            if not rows:
                return (0, 0, [], [])

            num_cols = max(len(row.find_all(['th', 'td'], recursive=False)) for row in rows)
            
            if level == 0:
                # Увеличиваем высоту первой строки
                row_heights = [NESTED_TABLE_SETTINGS['header_height']] + [40] * (len(rows)-1)
                col_widths = [40, 100] + [150] * (num_cols - 2)
            else:
                padding = NESTED_TABLE_SETTINGS['padding']
                available_width = parent_width - 2 * padding if parent_width else 100
                col_width = max(NESTED_TABLE_SETTINGS['min_col_width'], available_width // num_cols)
                col_widths = [col_width] * num_cols
                row_heights = [20] * (len(rows)+1)

            for i, row in enumerate(rows):
                cells = row.find_all(['th', 'td'], recursive=False)
                
                for j, cell in enumerate(cells[:num_cols]):
                    text = cell.get_text(" ", strip=True)
                    
                    if level == 0 and i == 0:
                        text = format_header(text)
                    
                    nested_tables = cell.find_all('table', recursive=False)
                    if nested_tables:
                        nested_height = sum(
                            calculate_table_size(t, level+1, col_widths[j])[1] 
                            + NESTED_TABLE_SETTINGS['padding'] 
                            for t in nested_tables
                        )
                        row_heights[i] = max(row_heights[i], nested_height)
                    else:
                        lines = textwrap.wrap(text, width=40 if level > 0 else 20)
                        line_height = 30 if level > 0 else 20
                        row_heights[i] = max(
                            row_heights[i], 
                            len(lines) * line_height + 15 + NESTED_TABLE_SETTINGS['border_offset']
                        )
            
            return (sum(col_widths), sum(row_heights), col_widths, row_heights)

        def get_cell_color(cell, level, cell_index=None):
            """Определяет цвет ячейки с учетом вложенных таблиц и позиции"""
            # 1. Проверяем классы самой ячейки в первую очередь
            cell_classes = cell.get('class', [])
            for class_name, color in CLASS_COLORS.items():
                if class_name in cell_classes:
                    return color

            # 2. Проверяем вложенные таблицы внутри ячейки
            nested_tables = cell.find_all('table', recursive=False)
            for table in nested_tables:
                table_classes = table.get('class', [])
                    
                for class_name, color in CLASS_COLORS.items():
                    if class_name in table_classes:
                        return color

            # 3. Для вложенных таблиц проверяем родительскую таблицу
            if level > 0:
                parent_table = cell.find_parent('table')
                if parent_table:
                    parent_classes = parent_table.get('class', [])
                    for class_name, color in CLASS_COLORS.items():
                        if class_name in parent_classes:
                            return color

            # 4. Цвет по умолчанию
            if level == 0:
                # Для основных ячеек учитываем позицию (первые два столбца)
                if cell_index is not None and cell_index in (0, 1):
                    return COLORS['first_col_bg']
            return COLORS['white']

        def draw_table(draw, x, y, table, col_widths, row_heights, level=0, parent_width=None, cons_sch=False):
            """Рисует таблицу на изображении с разными шрифтами для разных элементов"""
            # Добавляем шрифт для дисциплин (крупнее обычного)
            font_disc = ImageFont.truetype("arial.ttf", size=font_bold.size)
            
            # Константы для отступов и межстрочного интервала
            PADDING = 4
            LINE_SPACING = 2

            rows = table.find_all('tr', recursive=False)
            current_y = y

            for i, row in enumerate(rows):
                current_x = x
                cells = row.find_all(['th', 'td'], recursive=False)
                
                for j, cell in enumerate(cells[:len(col_widths)]):
                    cell_width = col_widths[j]
                    cell_height = row_heights[i]
                    text = cell.get_text(" ", strip=True)
                    
                    # ОСОБАЯ ОБРАБОТКА ДЛЯ ПЕРВОЙ СТРОКИ ОСНОВНОЙ ТАБЛИЦЫ
                    if level == 0 and i == 0:
                        text = format_header(text)
                        font = font_first_line
                        
                        text_color = COLORS['white']
                        bg_color = COLORS['header_bg']
                        
                        # Рисуем фон ячейки
                        draw.rectangle(
                            [current_x, current_y, current_x + cell_width, current_y + cell_height],
                            fill=bg_color,
                            outline=COLORS['border']
                        )
                        
                        # Рисуем текст с центрированием
                        lines = text.split('\n')
                        # Получаем высоту текста через bbox
                        bbox = draw.textbbox((0, 0), "A", font=font)
                        line_height = (bbox[3] - bbox[1]) + LINE_SPACING
                        text_height = len(lines) * line_height
                        start_y = current_y + (cell_height - text_height) // 2
                        
                        for k, line in enumerate(lines):
                            text_width = font.getlength(line)
                            text_x = current_x + (cell_width - text_width) // 2
                            text_y = start_y + k * line_height
                            draw.text((text_x, text_y), line, fill=text_color, font=font)
                        
                        current_x += cell_width
                        continue
                    
                    # ОБЫЧНЫЕ ЯЧЕЙКИ
                    bg_color = get_cell_color(cell, level, j)
                    if bg_color == 'drob':
                        bg_color = "#D5932F"
                    # Рисуем фон для ячеек основного уровня
                    if level == 0:
                        draw.rectangle(
                            [current_x, current_y, current_x + cell_width, current_y + cell_height],
                            fill=bg_color,
                            outline=COLORS['border']
                        )
                        if bg_color == "#D5932F":
                            draw.rectangle(
                            [current_x, current_y + cell_height / 2, current_x + cell_width, current_y + cell_height],
                            fill="#3F8D2A",
                            outline=COLORS['border']
                            )
                            
                            # text_width = font.getlength('Нечётная неделя')
                            # text_x = current_x + (cell_width - text_width) // 2
                            # draw.text((text_x, current_y + cell_height / 2 - 15), 'Нечётная неделя', fill=text_color, font=font)
                            # text_width = font.getlength('Чётная неделя')
                            # text_x = current_x + (cell_width - text_width) // 2
                            # draw.text((text_x, current_y + cell_height / 2 + 2), 'Чётная неделя', fill=text_color, font=font)

                    # Обработка вложенных таблиц
                    nested_tables = cell.find_all('table', recursive=False)
                    if nested_tables:
                        formatted_lines = []
                        line_types = []
                        line_fonts = []
        
                        for nested_table in nested_tables:
                            rows = nested_table.find_all('tr', recursive=False)
                            row_data = [None] * 4
                            
                            if cons_sch and len(rows)==2:
                                row_data = [None] * 6
                                disc = rows[0].find('div', class_='disc')
                                prep = rows[0].find('div', class_='prep')
                                cab = rows[0].find('div', class_='cab')
                                
                                disc2 = rows[1].find('div', class_='disc')
                                prep2 = rows[1].find('div', class_='prep')
                                cab2 = rows[1].find('div', class_='cab')

                                row_data[0] = disc.get_text(strip=True) if disc else None
                                row_data[1] = prep.get_text(strip=True) if prep else None
                                row_data[2] = cab.get_text(strip=True) if cab else None

                                row_data[3] = disc2.get_text(strip=True) if disc2 else None
                                row_data[4] = prep2.get_text(strip=True) if prep2 else None
                                row_data[5] = cab2.get_text(strip=True) if cab2 else None

                                if row_data[0]: 
                                    formatted_lines.append(row_data[0])
                                    line_types.append('top')
                                    line_fonts.append(font_disc)
                                if row_data[1]: 
                                    formatted_lines.append(row_data[1])
                                    line_types.append('top')
                                    line_fonts.append(font_regular)
                                if row_data[2]: 
                                    formatted_lines.append(row_data[2])
                                    line_types.append('top')
                                    line_fonts.append(font_regular)

                                if row_data[3]: 
                                    
                                    formatted_lines.append(row_data[3])
                                    line_types.append('bottom')
                                    line_fonts.append(font_disc)
                                if row_data[4]: 
                                    formatted_lines.append(row_data[4])
                                    line_types.append('bottom')
                                    line_fonts.append(font_regular)
                                if row_data[5]: 
                                    formatted_lines.append(row_data[5])
                                    line_types.append('bottom')
                                    line_fonts.append(font_regular)

                            elif len(rows) == 1:
                                disc = rows[0].find('div', class_='disc')
                                prep = rows[0].find('div', class_='prep')
                                if prep == None:
                                    prep = rows[0].find('div', class_='grupp')
                                cab = rows[0].find('div', class_='cab')
                                
                                row_data[0] = disc.get_text(strip=True) if disc else None
                                row_data[1] = prep.get_text(strip=True) if prep else None
                                row_data[2] = cab.get_text(strip=True) if cab else None
                                
                                if row_data[0]: 
                                    formatted_lines.append(row_data[0])
                                    line_types.append('top')
                                    line_fonts.append(font_disc)
                                if row_data[1]: 
                                    formatted_lines.append(row_data[1])
                                    line_types.append('bottom')
                                    line_fonts.append(font_regular)
                                if row_data[2]: 
                                    formatted_lines.append(row_data[2])
                                    line_types.append('bottom')
                                    line_fonts.append(font_regular)
                                    
                            elif len(rows) == 2:
                                first_td = rows[0].find('td')
                                row_data[0] = first_td.get_text(strip=True) if first_td else None
                                if row_data[0] and 'Дифференцированный' in row_data[0]:
                                    row_data[0] = row_data[0].replace('Дифференцированный', 'Диф.')
                                cab = rows[0].find('div', class_='cab')
                                row_data[3] = cab.get_text(strip=True) if cab else None
                                
                                disc = rows[1].find('div', class_='disc')
                                prep = rows[1].find('div', class_='prep')
                                row_data[1] = disc.get_text(strip=True) if disc else None
                                row_data[2] = prep.get_text(strip=True) if prep else None
                                
                                if row_data[0]: 
                                    formatted_lines.append(row_data[0])
                                    line_types.append('top')
                                    line_fonts.append(font_regular)
                                if row_data[1]: 
                                    formatted_lines.append(row_data[1])
                                    line_types.append('top')
                                    line_fonts.append(font_disc)
                                if row_data[2]: 
                                    formatted_lines.append(row_data[2])
                                    line_types.append('bottom')
                                    line_fonts.append(font_regular)
                                if row_data[3]: 
                                    formatted_lines.append(row_data[3])
                                    line_types.append('bottom')
                                    line_fonts.append(font_regular)
                        
                        # Разбиваем длинные строки с переносом по словам
                        wrapped_lines = []
                        wrapped_line_types = []
                        wrapped_line_fonts = []
                        max_line_width = cell_width - 2 * PADDING
                        
                        for line, line_type, line_font in zip(formatted_lines, line_types, line_fonts):
                            words = re.split(r'[\s-]+', line)
                            current_line = ""
                            
                            for word in words:
                                test_line = f"{current_line} {word}".strip()
                                if line_font.getlength(test_line) <= max_line_width:
                                    current_line = test_line
                                else:
                                    if current_line:
                                        wrapped_lines.append(current_line)
                                        wrapped_line_types.append(line_type)
                                        wrapped_line_fonts.append(line_font)
                                    current_line = word
                            
                            if current_line:
                                wrapped_lines.append(current_line)
                                wrapped_line_types.append(line_type)
                                wrapped_line_fonts.append(line_font)
                        
                        # Рассчитываем общую высоту текста
                        top_lines = [(line, font) for line, typ, font in zip(wrapped_lines, wrapped_line_types, wrapped_line_fonts) if typ == 'top']
                        bottom_lines = [(line, font) for line, typ, font in zip(wrapped_lines, wrapped_line_types, wrapped_line_fonts) if typ == 'bottom']
                        
                        # Вычисляем высоту для верхней и нижней групп
                        top_height = 0
                        for line, font in top_lines:
                            bbox = draw.textbbox((0, 0), line, font=font)
                            line_height = (bbox[3] - bbox[1]) + LINE_SPACING
                            top_height += line_height
                        
                        bottom_height = 0
                        for line, font in bottom_lines:
                            bbox = draw.textbbox((0, 0), line, font=font)
                            line_height = (bbox[3] - bbox[1]) + LINE_SPACING
                            bottom_height += line_height
                        
                        # Рисуем верхние строки (выравнивание по верху)
                        current_y_top = current_y + PADDING
                        for line, font in top_lines:
                            bbox = draw.textbbox((0, 0), line, font=font)
                            line_height = (bbox[3] - bbox[1]) + LINE_SPACING
                            text_width = font.getlength(line)
                            text_x = current_x + (cell_width - text_width) // 2
                            text_x = max(
                                current_x + PADDING,
                                min(text_x, current_x + cell_width - text_width - PADDING)
                            )
                            draw.text((text_x, current_y_top), line, fill=COLORS['text'], font=font)
                            current_y_top += line_height
                        
                        # Рисуем нижние строки (выравнивание по низу)
                        current_y_bottom = current_y + cell_height - bottom_height - PADDING
                        for line, font in bottom_lines:
                            bbox = draw.textbbox((0, 0), line, font=font)
                            line_height = (bbox[3] - bbox[1]) + LINE_SPACING
                            text_width = font.getlength(line)
                            text_x = current_x + (cell_width - text_width) // 2
                            text_x = max(
                                current_x + PADDING,
                                min(text_x, current_x + cell_width - text_width - PADDING)
                            )
                            draw.text((text_x, current_y_bottom), line, fill=COLORS['text'], font=font)
                            current_y_bottom += line_height
                    
                    else:
                        # Обычная ячейка (не вложенная таблица)
                        font = font_bold if (level == 0 and (i == 0 or cell.name == 'th')) else font_regular
                        text_color = COLORS['white'] if (level == 0 and (i == 0 or cell.name == 'th')) else COLORS['text']
                        
                        # Перенос текста с учетом ширины ячейки
                        max_line_width = cell_width - 2 * PADDING
                        lines = []
                        if level == 0 and i == 0:
                            lines = text.split('\n')
                        else:
                            words = text.split()
                            current_line = ""
                            
                            for word in words:
                                test_line = f"{current_line} {word}".strip()
                                if font.getlength(test_line) <= max_line_width:
                                    current_line = test_line
                                else:
                                    if current_line:
                                        lines.append(current_line)
                                    current_line = word
                            
                            if current_line:
                                lines.append(current_line)
                        
                        # Рассчитываем общую высоту текста
                        total_text_height = 0
                        for line in lines:
                            bbox = draw.textbbox((0, 0), line, font=font)
                            line_height = (bbox[3] - bbox[1]) + LINE_SPACING
                            total_text_height += line_height
                        
                        # Центрируем текст по вертикали
                        start_y = current_y + (cell_height - total_text_height) // 2
                        
                        for line in lines:
                            bbox = draw.textbbox((0, 0), line, font=font)
                            line_height = (bbox[3] - bbox[1]) + LINE_SPACING
                            text_width = font.getlength(line)
                            text_x = current_x + (cell_width - text_width) // 2
                            draw.text((text_x, start_y), line, fill=text_color, font=font)
                            start_y += line_height
                    
                    current_x += cell_width
                current_y += cell_height

        # Основная логика создания изображения
        table_width, table_height, col_widths, row_heights = calculate_table_size(main_table)
        
        img_width = table_width
        img_height = 50 + table_height + 40  # header + table + legend
        
        img = Image.new('RGB', (img_width, img_height), COLORS['white'])
        draw = ImageDraw.Draw(img)
        
        # Заголовок изображения
        if header_text:
            header_lines = textwrap.wrap(header_text, width=60)
            for k, line in enumerate(header_lines):
                text_width = font_header.getlength(line)
                draw.text(((img_width - text_width) / 2, 10 + k * 20), line, fill=COLORS['text'], font=font_header)
        
        # Основная таблица
        draw_table(draw, 0, 50, main_table, col_widths, row_heights, cons_sch=cons_sched)
        
        # Легенда (пояснения цветов)
        legend_y = 50 + table_height + 10
        legend_x = 10
        if cons_sched:
            for i, (cls, desc) in enumerate(zip(CLASS_COLORS_CONS.keys(), CLASS_DESCRIPTIONS_CONS.values())):
                draw.rectangle([legend_x, legend_y, legend_x+15, legend_y+15], fill=CLASS_COLORS_CONS[cls], outline=COLORS['border'])
                draw.text((legend_x+20, legend_y), desc, fill=COLORS['text'], font=font_regular)
                legend_x += font_regular.getlength(desc) + 40
                if legend_x > img_width - 100 and i < len(CLASS_COLORS_CONS)-1:
                    legend_x = 10
                    legend_y += 20
        else:
            for i, (cls, desc) in enumerate(zip(CLASS_COLORS.keys(), CLASS_DESCRIPTIONS.values())):
                draw.rectangle([legend_x, legend_y, legend_x+15, legend_y+15], fill=CLASS_COLORS[cls], outline=COLORS['border'])
                draw.text((legend_x+20, legend_y), desc, fill=COLORS['text'], font=font_regular)
                legend_x += font_regular.getlength(desc) + 40
                if legend_x > img_width - 100 and i < len(CLASS_COLORS)-1:
                    legend_x = 10
                    legend_y += 20
        
        # Сохранение изображения в буфер
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format='PNG', quality=95)
        img_byte_arr.seek(0)
        return img_byte_arr
    
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}", exc_info=True)
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "Привет! Я бот для расписания.\n"
        "Используй /schedule - получить расписание\n"
        "/change_group - изменить группу"
    )

async def send_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /schedule"""
    # Отправляем сообщение "Получаю расписание..." и сохраняем его ID
    sent_message = await update.message.reply_text("Получаю расписание...")
    
    # Получаем расписание
    img = await get_schedule_image(update.effective_chat.id)
    
    # Удаляем сообщение "Получаю расписание..."
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, 
                                       message_id=sent_message.message_id)
    except Exception as e:
        logging.error(f"Не удалось удалить сообщение: {e}")
    
    # Отправляем расписание как новое сообщение
    if img:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img, reply_markup=markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, 
                                     text="Ошибка при получении расписания, скорее всего проблема на стороне ТИУ")

async def send_schedule_const(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /schedule_const"""
    # Отправляем сообщение "Получаю расписание..." и сохраняем его ID
    sent_message = await update.message.reply_text("Получаю расписание...")
    
    # Получаем расписание
    img = await get_schedule_image(update.effective_chat.id, cons_sched=True)
    
    # Удаляем сообщение "Получаю расписание..."
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, 
                                       message_id=sent_message.message_id)
    except Exception as e:
        logging.error(f"Не удалось удалить сообщение: {e}")
    
    # Отправляем расписание как новое сообщение
    if img:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img, reply_markup=markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, 
                                     text="Ошибка при получении расписания, скорее всего проблема на стороне ТИУ")

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение при добавлении бота в группу"""
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            # Создаем Reply-клавиатуру с одной кнопкой
            
            
            await update.message.reply_text(
                "Спасибо за добавление! Чтобы начать работу:\n"
                "1. Установите группу командой /change_group [название группы]\n"
                "2. Получайте расписание командой /schedule или кнопкой ниже\n"
                "3. Получайте расписание преподавателей командой /prep\n\n"
                "Для наилучшей работы бота ему нужны админ-права!",
                reply_markup=markup
            )
            break



async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для кнопки"""
    if update.message.text == "Получить расписание":
        # Отправляем сообщение "Получаю расписание..." и сохраняем его ID
        sent_message = await update.message.reply_text("Получаю расписание...")
        
        # Получаем расписание
        img = await get_schedule_image(update.effective_chat.id)
        
        # Удаляем сообщение "Получаю расписание..."
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, 
                                           message_id=sent_message.message_id)
        except Exception as e:
            logging.error(f"Не удалось удалить сообщение: {e}")
        
        # Отправляем расписание как новое сообщение
        if img:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img, reply_markup=markup)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, 
                                         text="Ошибка при получении расписания, скорее всего проблема на стороне ТИУ")

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Основная функция запуска бота"""
    application = Application.builder().token(TOKEN).build()
    
    # Создаем ConversationHandler для обработки изменения группы
    conv_handler_group = ConversationHandler(
        entry_points=[CommandHandler("change_group", change_group)],
        states={
            WAITING_FOR_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_group_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Создаем ConversationHandler для рассылки
    conv_handler_broadcast = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            WAITING_FOR_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Создаем ConversationHandler для обработки тикетов
    conv_handler_ticket = ConversationHandler(
        entry_points=[CommandHandler("ticket", ticket_start)],
        states={
            WAITING_FOR_TICKET: [
                MessageHandler(filters.TEXT | filters.PHOTO, ticket_receive)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Создаем ConversationHandler для обработки расписания преподов
    conv_handler_prep = ConversationHandler(
        entry_points=[CommandHandler("prep", prep_start)],
        states={
            WAITING_FOR_PREP: [MessageHandler(filters.TEXT & ~filters.COMMAND, prep_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("schedule", send_schedule))
    application.add_handler(CommandHandler("schedule_const", send_schedule_const))
    application.add_handler(CommandHandler("stats", get_stats))  # Новая команда статистики
    application.add_handler(CommandHandler("reply", reply_to_ticket))  # Команда для ответа на тикеты
    application.add_handler(conv_handler_group)
    application.add_handler(conv_handler_broadcast)  # Добавляем обработчик рассылки
    application.add_handler(conv_handler_ticket)
    application.add_handler(conv_handler_prep)
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    application.run_polling()


if __name__ == '__main__':
    main()