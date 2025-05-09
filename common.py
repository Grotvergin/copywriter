from source import CONN_ERRORS, LONG_SLEEP, BOT
# ---
from typing import Any, Callable
from datetime import datetime
from time import sleep
from functools import wraps
from random import randint
from asyncio import sleep as async_sleep
# ---
from googleapiclient.discovery import Resource, build
from colorama import Fore, Style
from telebot.types import Message, ReplyKeyboardMarkup, KeyboardButton
from google.oauth2.service_account import Credentials


def Sleep(timer: int, ratio: float = 0.0) -> None:
    rand_time = randint(int((1 - ratio) * timer), int((1 + ratio) * timer))
    Stamp(f'Sleeping {rand_time} seconds', 'l')
    sleep(rand_time)


def GetSector(start: str, finish: str, service: Resource, sheet_name: str, sheet_id: str) -> list:
    Stamp(f'Trying to get sector from {start} to {finish} from sheet {sheet_name}', 'i')
    try:
        res = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=f'{sheet_name}!{start}:{finish}').execute().get('values', [])
    except CONN_ERRORS as err:
        Stamp(f'Status = {err} on getting sector from {start} to {finish} from sheet {sheet_name}', 'e')
        Sleep(LONG_SLEEP)
        res = GetSector(start, finish, service, sheet_name, sheet_id)
    else:
        if not res:
            Stamp(f'No elements in sector from {start} to {finish} sheet {sheet_name} found', 'w')
        else:
            Stamp(f'Found {len(res)} rows from sector from {start} to {finish} sheet {sheet_name}', 's')
    return res


def Stamp(message: str, level: str) -> None:
    time_stamp = datetime.now().strftime('[%m-%d|%H:%M:%S]')
    match level:
        case 'i':
            print(Fore.LIGHTBLUE_EX + time_stamp + '[INF] ' + message + '.' + Style.RESET_ALL)
        case 'w':
            print(Fore.LIGHTMAGENTA_EX + time_stamp + '[WAR] ' + message + '!' + Style.RESET_ALL)
        case 's':
            print(Fore.LIGHTGREEN_EX + time_stamp + '[SUC] ' + message + '.' + Style.RESET_ALL)
        case 'e':
            print(Fore.RED + time_stamp + '[ERR] ' + message + '!!!' + Style.RESET_ALL)
        case 'l':
            print(Fore.WHITE + time_stamp + '[SLE] ' + message + '...' + Style.RESET_ALL)
        case 'b':
            print(Fore.LIGHTYELLOW_EX + time_stamp + '[BOR] ' + message + '.' + Style.RESET_ALL)
        case _:
            print(Fore.WHITE + time_stamp + '[UNK] ' + message + '?' + Style.RESET_ALL)


def BuildService() -> Resource:
    Stamp(f'Trying to build service', 'i')
    try:
        service = build('sheets', 'v4',
                        credentials=Credentials.from_service_account_file('keys.json', scopes=['https://www.googleapis.com/auth/spreadsheets']))
    except CONN_ERRORS as err:
        Stamp(f'Status = {err} on building service', 'e')
        Sleep(LONG_SLEEP)
        BuildService()
    else:
        Stamp('Built service successfully', 's')
        return service


def ParseAccountRow(account: list) -> tuple:
    api_id = account[0]
    api_hash = account[1]
    num = account[2]
    password_tg = account[3] if account[3] != '-' else None
    ip = account[4]
    port = int(account[5])
    login = account[6]
    password_proxy = account[7]
    return api_id, api_hash, num, password_tg, ip, port, login, password_proxy


def ShowButtons(message: Message | int, buttons: tuple, answer: str, parse_mode: str = None) -> None:
    markup = ReplyKeyboardMarkup(one_time_keyboard=True)
    if type(message) == Message:
        user_id = message.from_user.id
    else:
        user_id = message
    if len(buttons) % 2 == 0:
        for i in range(0, len(buttons), 2):
            row_buttons = buttons[i:i + 2]
            markup.row(*[KeyboardButton(btn) for btn in row_buttons])
    else:
        for i in range(0, len(buttons) - 1, 2):
            row_buttons = buttons[i:i + 2]
            markup.row(*[KeyboardButton(btn) for btn in row_buttons])
        markup.row(KeyboardButton(buttons[-1]))
    BOT.send_message(user_id, answer, reply_markup=markup, parse_mode=parse_mode)