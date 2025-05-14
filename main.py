from telethon.tl.types import MessageEntityCustomEmoji

import source
from json import load, JSONDecodeError, dump
from re import sub
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from typing import List
from common import BuildService, GetSector, Stamp, ParseAccountRow, ShowButtons
from os.path import join, exists
from os import getcwd, remove
from secret import SHEET_NAME, SHEET_ID, SECRET_CODE, MY_TG_ID, AR_TG_ID
from source import (Task, TASKS_FILE, BOT, MAX_POSTS_TO_CHECK,
                    AUTHORIZED_USERS_FILE, BTNS, LONG_SLEEP, CANCEL_BTN,
                    NOTIF_TIME_DELTA, POSTED_FILE, CustomMarkdown, MEDIA_DIR)
from traceback import format_exc
from threading import Thread
from asyncio import run, sleep as async_sleep
from telebot.types import Message


async def authorizeAccounts():
    srv = BuildService()
    row = len(GetSector('C2', 'C500', srv, SHEET_NAME, SHEET_ID)) + 1
    data = GetSector('A2', f'H{row}', srv, SHEET_NAME, SHEET_ID)

    for index, account in enumerate(data):
        try:
            api_id, api_hash, num, password_tg, ip, port, login, password_proxy = ParseAccountRow(account)
        except IndexError:
            Stamp(f'Invalid account data: {account}', 'e')
            continue
        session = join(getcwd(), 'sessions', f'{num}')
        client = TelegramClient(session, api_id, api_hash, proxy=(2, ip, port, True, login, password_proxy))
        await client.start(phone=num, password=password_tg)
        source.ACCOUNTS.append(client)
        Stamp(f'Account {num} authorized', 's')


def loadTasks() -> List[Task]:
    Stamp('Loading tasks', 'i')
    try:
        with open(TASKS_FILE, 'r') as f:
            data = load(f)
        return [Task.from_dict(d) for d in data]
    except (FileNotFoundError, JSONDecodeError):
        return []


def saveTasks(tasks: List[Task]):
    Stamp('Saving tasks', 'i')
    with open(TASKS_FILE, 'w') as f:
        dump([t.to_dict() for t in tasks], f, indent=2)


def reformatPost(message, task):
    text = message.message or ""
    if task.document_id:
        changed_link = f'\n\n[🌟](emoji/{task.document_id}) @{task.target}'
    else:
        changed_link = f'\n\n@{task.target})'

    split_index = text.rfind('\n\n')
    if split_index != -1:
        Stamp(f'Found blank line at {split_index}', 'i')
        text = text[:split_index].rstrip() + changed_link
    else:
        Stamp('No blank line found', 'w')
        msg = f'🔺 Не нашел пустой строки для обрезания в сообщении для @{task.target}'
        BOT.send_message(MY_TG_ID, msg)
        BOT.send_message(AR_TG_ID, msg)
        text = sub(r'(https://t\.me/\S+|@\w+)', changed_link, text)

    return text


def loadPosted():
    if exists(POSTED_FILE):
        with open(POSTED_FILE, 'r') as f:
            return load(f)
    return {}


def savePosted(channel_name, post_id):
    posted_posts = loadPosted()
    if channel_name not in posted_posts:
        posted_posts[channel_name] = []
    posted_posts[channel_name].append(post_id)
    with open(POSTED_FILE, 'w') as f:
        dump(posted_posts, f, indent=2)


async def getBestPost(source_channels, client):
    Stamp(f"Getting best post among {', '.join(source_channels)}", 'i')
    best_post = None
    best_chan = None
    best_id = None
    max_forwards = -1
    posted = loadPosted()

    for channel in source_channels:
        try:
            entity = await client.get_entity(channel)
            history = await client(GetHistoryRequest(
                peer=entity,
                limit=MAX_POSTS_TO_CHECK,
                offset_date=None,
                offset_id=0,
                max_id=0,
                min_id=0,
                add_offset=0,
                hash=0
            ))

            for msg in history.messages:
                if not (msg.text or msg.message or msg.media):
                    continue

                if msg.id in posted.get(channel, []):
                    continue

                if msg.forwards and msg.forwards > max_forwards:
                    max_forwards = msg.forwards
                    best_post = msg
                    best_chan = channel
                    best_id = msg.id
        except Exception as e:
            Stamp(f'Error fetching channel {channel}: {e}', 'e')

    if best_post:
        savePosted(best_chan, best_id)

    return best_post


def load_authorized_users() -> set:
    """Загружает список авторизованных пользователей из файла."""
    if exists(AUTHORIZED_USERS_FILE):
        with open(AUTHORIZED_USERS_FILE, "r") as f:
            return set(load(f))
    return set()


def save_authorized_users(users: set) -> None:
    """Сохраняет список авторизованных пользователей в файл."""
    with open(AUTHORIZED_USERS_FILE, "w") as f:
        dump(list(users), f)


def botPolling():
    while True:
        try:
            BOT.polling(none_stop=True, interval=1)
        except Exception as e:
            Stamp(f'{e}', 'e')
            Stamp(format_exc(), 'e')


def deleteTask(message: Message):
    user_id = message.from_user.id
    target = normalize_channel(message.text)
    tasks = loadTasks()

    task_for_deletion = next((task for task in tasks if task.target == target), None)

    if task_for_deletion:
        tasks.remove(task_for_deletion)
        saveTasks(tasks)
        BOT.send_message(user_id, f"✅ Задача для канала @{target} удалена")
    else:
        BOT.send_message(user_id, f"⚠️ Задача для канала @{target} не найдена.")

    ShowButtons(message, BTNS, '❔ Выберите действие:')


def showTasks(user_id):
    tasks = loadTasks()

    if not tasks:
        BOT.send_message(user_id, "📭 Активных заявок нет.")
        return

    response = "📅 Все активные заявки:\n\n"

    for task in tasks:
        response += f"📍 Канал: @{task.target}\n"
        response += f"📎 Референсы: {' '.join(f'@{s}' for s in task.sources)}\n"
        response += f'🌟 ID эмодзи: {task.document_id}\n'
        response += f"⏰ Расписание на сегодня:\n"

        for post, planned in zip(sorted(task.schedule, key=lambda p: p.time), task.plan):
            status = "✅" if post.posted else "🕒"
            response += f"   {status} {post.time.strftime('%H:%M')} (по плану в {planned.strftime('%H:%M')})\n"

        response += "—" * 24 + "\n"

    BOT.send_message(user_id, response)


def normalize_channel(link: str) -> str:
    """Приводит ссылку к короткому имени канала без @ и без https://t.me/."""
    link = link.strip()
    if link.startswith('https://t.me/'):
        return link[13:]
    if link.startswith('t.me/'):
        return link[6:]
    if link.startswith('@'):
        return link[1:]
    return link


def acceptTask(message: Message):
    user_id = message.from_user.id
    lines = message.text.strip().split('\n')
    document_id = 0

    if message.text == CANCEL_BTN[0]:
        ShowButtons(message, BTNS, '❔ Выберите действие:')
        return

    if len(lines) < 3 or len(lines) > 4:
        ShowButtons(message, CANCEL_BTN, "❌ Неверный формат. Отправьте данные в 3 или 4 строках")
        BOT.register_next_step_handler(message, acceptTask)
        return

    try:
        target = normalize_channel(lines[0])
        sources = [normalize_channel(s) for s in lines[1].strip().split()]

        time_strings = lines[2].strip().split()
        plan = []
        for t in time_strings:
            parsed = datetime.strptime(t, "%H:%M").time()
            plan.append(parsed)

        if len(lines) == 4:
            for entity in message.entities:
                if entity.type == 'custom_emoji':
                    document_id = int(entity.custom_emoji_id)

    except ValueError:
        ShowButtons(message, CANCEL_BTN, "❌ Ошибка: время должно быть в формате HH:MM (например, 10:15 14:00 18:45)")
        BOT.register_next_step_handler(message, acceptTask)
        return

    tasks = loadTasks()

    if any(task.target == target for task in tasks):
        ShowButtons(message, CANCEL_BTN, f'‼️ Заявка на канал {target} уже существует')
        BOT.register_next_step_handler(message, acceptTask)
        return

    new_task = Task(
        target=target,
        sources=sources,
        plan=plan,
        schedule=[],
        document_id=document_id
    )

    new_task.regenerate_schedule()
    tasks.append(new_task)
    saveTasks(tasks)

    BOT.send_message(user_id, f"✅ Задача для @{target} добавлена.")
    ShowButtons(message, BTNS, '❔ Что дальше?')


def sendNotificationAboutWork():
    if datetime.now() - source.LAST_NOTIF_PROCESSOR > timedelta(minutes=NOTIF_TIME_DELTA):
        tasks = loadTasks()
        total_count = sum(1 for task in tasks for post in task.schedule)
        posted_count = sum(1 for task in tasks for post in task.schedule if post.posted)
        msg = (f'🆗 Заявок: {len(tasks)}\n'
               f'📍 Запланировано постов: {total_count}\n'
               f'✅ Выложено: {posted_count}\n'
               f'💢 Ожидается: {total_count - posted_count}')
        BOT.send_message(MY_TG_ID, msg)
        BOT.send_message(AR_TG_ID, msg)
        source.LAST_NOTIF_PROCESSOR = datetime.now()


async def processRequests():
    while True:
        now = datetime.now()
        sendNotificationAboutWork()
        if source.LAST_TIMETABLE_CHANGE.date() < now.date():
            tasks = loadTasks()
            for task in tasks:
                task.regenerate_schedule()
            saveTasks(tasks)
            source.LAST_TIMETABLE_CHANGE = now
            Stamp("Timetables were renewed", 's')

        tasks = loadTasks()

        for i, task in enumerate(tasks):
            for post in task.get_due_posts(now):
                try:
                    if not source.ACCOUNTS:
                        Stamp("No authorized accounts", 'e')
                        continue

                    sender = source.ACCOUNTS[0]
                    sender.parse_mode = CustomMarkdown()
                    readers = source.ACCOUNTS[1:] if len(source.ACCOUNTS) > 1 else [sender]
                    reader = readers[i % len(readers)]

                    best_msg = await getBestPost(task.sources, reader)

                    if not best_msg:
                        Stamp(f"Have not found post for @{task.target}", 'w')
                        continue

                    entity = await sender.get_entity(task.target)

                    if best_msg.media:
                        try:
                            file_name = f'./{MEDIA_DIR}/{task.target}_{best_msg.id}_{datetime.now().strftime('%H_%M_%S')}'
                            file_path = await reader.download_media(best_msg, file=file_name)
                            await sender.send_file(entity, file_path, caption=reformatPost(best_msg, task))
                            remove(file_path)
                        except Exception as e:
                            Stamp(f"Unable to download file: {e}", 'w')
                    else:
                        await sender.send_message(entity, reformatPost(best_msg, task))

                    task.mark_as_posted(post)
                    Stamp(f"Post sent to @{task.target}", 's')

                except Exception as e:
                    Stamp(f"Error sending to @{task.target}: {e}", 'e')

        saveTasks(tasks)
        await async_sleep(LONG_SLEEP)


@BOT.message_handler(commands=['start'])
def startHandler(message: Message):
    user_id = message.from_user.id
    text_parts = message.text.split()

    if len(text_parts) == 2 and text_parts[1] == SECRET_CODE:
        if user_id not in source.AUTHORIZED_USERS:
            source.AUTHORIZED_USERS.add(user_id)
            save_authorized_users(source.AUTHORIZED_USERS)
            BOT.send_message(user_id, "✅ Вы успешно авторизованы! Добро пожаловать!")
            ShowButtons(message, BTNS, '❔ Выберите действие:')
        else:
            BOT.send_message(user_id, "🔓 Вы уже авторизованы.")
            ShowButtons(message, BTNS, '❔ Выберите действие:')
    else:
        BOT.send_message(user_id, "❌ Неверный или отсутствующий код доступа.")


@BOT.message_handler(content_types=['text'])
def MessageAccept(message: Message) -> None:
    user_id = message.from_user.id
    Stamp(f'User {user_id} requested {message.text}', 'i')

    if user_id not in source.AUTHORIZED_USERS:
        BOT.send_message(user_id, "⛔️ Нет доступа. Используйте ссылку с кодом для входа.")
        return

    if message.text == BTNS[0]:
        BOT.send_message(user_id,  "❔ Пришлите данные в формате:\n\n"
                                   "📍 Целевой канал\n"
                                   "📎 Ссылки на каналы-референсы через пробел\n"
                                   "⏰ Часы публикаций через пробел\n"
                                   "🌟 Кастомный эмодзи\n\n"
                                   "ℹ️ Пример:\n@mychannel\n@ref1 @ref2 @ref3\n10:15 12:22 14:00\n🌟")
        BOT.register_next_step_handler(message, acceptTask)
    elif message.text == BTNS[1]:
        BOT.send_message(user_id, '❔ Введите ссылку на канал в формате @name')
        BOT.register_next_step_handler(message, deleteTask)
    elif message.text == BTNS[2]:
        showTasks(user_id)
        ShowButtons(message, BTNS, '❔ Выберите действие:')
    else:
        BOT.send_message(user_id, '❌ Я вас не понял...')
        ShowButtons(message, BTNS, '❔ Выберите действие:')


async def main():
    source.AUTHORIZED_USERS = load_authorized_users()
    await authorizeAccounts()
    await processRequests()


if __name__ == '__main__':
    Thread(target=botPolling, daemon=True).start()
    run(main())
