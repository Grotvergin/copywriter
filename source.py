from dataclasses import dataclass
from typing import List
from telebot import TeleBot
from secret import TOKEN
from datetime import time, datetime
from random import randint
from googleapiclient.errors import HttpError
from httplib2.error import ServerNotFoundError
from socket import gaierror
from ssl import SSLEOFError
from telethon.extensions import markdown
from telethon.types import MessageEntityCustomEmoji, MessageEntityTextUrl


TASKS_FILE = 'tasks.json'
POSTED_FILE = 'posted.json'
ACCOUNTS = []
BOT = TeleBot(TOKEN)
JITTER_LIMIT_MIN = 15
SEND_POST_LIMIT_SEC = 60
MAX_POSTS_TO_CHECK = 10
LONG_SLEEP = 20
NOTIF_TIME_DELTA = 5
CONN_ERRORS = (TimeoutError, ServerNotFoundError, gaierror, HttpError, SSLEOFError)
LAST_TIMETABLE_CHANGE = datetime.now()
LAST_NOTIF_PROCESSOR = datetime.now()
AUTHORIZED_USERS = set()
AUTHORIZED_USERS_FILE = "authorized_users.json"
BTNS = ('Добавление 📌',
        'Удаление ❌',
        'Активные 📅')
CANCEL_BTN = ('Меню ↩️',)


@dataclass
class Post:
    time: time
    posted: bool = False


@dataclass
class Task:
    target: str
    sources: List[str]
    plan: List[time]
    schedule: List[Post]
    document_id: int

    def to_dict(self):
        return {
            "target": self.target,
            "sources": self.sources,
            "plan": [t.isoformat() for t in self.plan],
            "schedule": [
                {"time": p.time.isoformat(), "posted": p.posted}
                for p in self.schedule
            ],
            'document_id': self.document_id
        }

    @staticmethod
    def from_dict(d):
        return Task(
            target=d["target"],
            sources=d["sources"],
            plan=[time.fromisoformat(t) for t in d.get("plan", [])],
            schedule=[
                Post(time.fromisoformat(p["time"]), p["posted"])
                for p in d.get("schedule", [])
            ],
            document_id=d['document_id']
        )

    def get_due_posts(self, now: datetime) -> List[Post]:
        """Вернёт список постов, которые нужно выложить сейчас"""
        return [
            p for p in self.schedule
            if not p.posted and abs((datetime.combine(now.date(), p.time) - now).total_seconds()) <= SEND_POST_LIMIT_SEC
        ]

    def mark_as_posted(self, post: Post):
        for p in self.schedule:
            if p.time == post.time:
                p.posted = True

    def regenerate_schedule(self):
        """Перегенерирует schedule с учётом jitter от plan."""
        self.schedule = []
        for base_time in self.plan:
            minute = base_time.minute + randint(-JITTER_LIMIT_MIN, JITTER_LIMIT_MIN)
            hour = base_time.hour

            if minute < 0:
                minute += 60
                hour = (hour - 1) % 24
            elif minute >= 60:
                minute -= 60
                hour = (hour + 1) % 24

            self.schedule.append(Post(time=time(hour, minute)))


class CustomMarkdown:
    @staticmethod
    def parse(text):
        text, entities = markdown.parse(text)
        for i, e in enumerate(entities):
            if isinstance(e, MessageEntityTextUrl):
                if e.url.startswith('emoji/'):
                    entities[i] = MessageEntityCustomEmoji(e.offset, e.length, int(e.url.split('/')[1]))
        return text, entities

    @staticmethod
    def unparse(text, entities):
        for i, e in enumerate(entities or []):
            if isinstance(e, MessageEntityCustomEmoji):
                entities[i] = MessageEntityTextUrl(e.offset, e.length, f'emoji/{e.document_id}')
        return markdown.unparse(text, entities)
