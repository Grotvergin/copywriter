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


TASKS_FILE = 'tasks.json'
ACCOUNTS = []
BOT = TeleBot(TOKEN)
JITTER_LIMIT_MIN = 15
SEND_POST_LIMIT_SEC = 60
HOURS_BEFORE_POST = 2
MAX_POSTS_TO_CHECK = 10
LONG_SLEEP = 20
CONN_ERRORS = (TimeoutError, ServerNotFoundError, gaierror, HttpError, SSLEOFError)
LAST_TIMETABLE_CHANGE = datetime.now()
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

    def to_dict(self):
        return {
            "target": self.target,
            "sources": self.sources,
            "plan": [t.isoformat() for t in self.plan],
            "schedule": [
                {"time": p.time.isoformat(), "posted": p.posted}
                for p in self.schedule
            ]
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
            ]
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
