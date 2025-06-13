from dataclasses import dataclass
from typing import List
from telebot import TeleBot
from secret import TOKEN
from datetime import time, datetime
from random import randint, sample, uniform
from googleapiclient.errors import HttpError
from httplib2.error import ServerNotFoundError
from socket import gaierror
from ssl import SSLEOFError
from datetime import timedelta
from telethon.extensions import markdown
from telethon.types import MessageEntityCustomEmoji, MessageEntityTextUrl


TASKS_FILE = 'tasks.json'
MEDIA_DIR = 'media'
POSTED_FILE = 'posted.json'
ACCOUNTS = []
BOT = TeleBot(TOKEN)
BUFFER_LINK_IS_AT_END = 7
JITTER_LIMIT_MIN = 15
SEND_POST_LIMIT_SEC = 60
MAX_POSTS_TO_CHECK = 10
LONG_SLEEP = 20
NOTIF_TIME_DELTA = 5
WEEKEND_SKIP_FACTOR = 0.5
TO_SKIP_FACTOR = 0.33
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
    skipped: bool = False


@dataclass
class Task:
    target: str
    sources: List[str]
    start: time
    end: time
    amount: int
    schedule: List[Post]
    document_id: int
    signature: str

    def to_dict(self):
        return {
            "target": self.target,
            "sources": self.sources,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "amount": self.amount,
            "schedule": [
                {
                    "time": p.time.isoformat(),
                    "posted": p.posted,
                    "skipped": p.skipped
                }
                for p in self.schedule
            ],
            "document_id": self.document_id,
            "signature": self.signature
        }

    @staticmethod
    def from_dict(d):
        return Task(
            target=d["target"],
            sources=d["sources"],
            start=time.fromisoformat(d["start"]),
            end=time.fromisoformat(d["end"]),
            amount=d["amount"],
            schedule=[
                Post(
                    time=time.fromisoformat(p["time"]),
                    posted=p.get("posted", False),
                    skipped=p.get("skipped", False)
                )
                for p in d.get("schedule", [])
            ],
            document_id=d["document_id"],
            signature=d["signature"]
        )

    def get_due_posts(self, now: datetime) -> List[Post]:
        """Вернёт список постов, которые нужно выложить сейчас (не пропущенные)"""
        return [
            p for p in self.schedule
            if not p.posted and not p.skipped
               and abs((datetime.combine(now.date(), p.time) - now).total_seconds()) <= SEND_POST_LIMIT_SEC
        ]

    def mark_as_posted(self, post: Post):
        for p in self.schedule:
            if p.time == post.time:
                p.posted = True

    def regenerate_schedule(self, date: datetime.date):
        """Генерирует расписание на один день (по дате), учитывая выходные и пропуски."""
        self.schedule = []

        is_weekend = date.weekday() >= 5
        amount_today = self.amount
        if is_weekend:
            amount_today = max(1, int(amount_today * WEEKEND_SKIP_FACTOR))

        seconds_range = (
            datetime.combine(date, self.end) - datetime.combine(date, self.start)
        ).seconds

        base_times = []
        for i in range(amount_today):
            base_second = int((i + 0.5) * seconds_range / amount_today)
            base_time = (datetime.combine(date, self.start) + timedelta(seconds=base_second)).time()
            base_times.append(base_time)

        for bt in base_times:
            minute = bt.minute + randint(-JITTER_LIMIT_MIN, JITTER_LIMIT_MIN)
            hour = bt.hour

            if minute < 0:
                minute += 60
                hour = (hour - 1) % 24
            elif minute >= 60:
                minute -= 60
                hour = (hour + 1) % 24

            self.schedule.append(Post(time=time(hour, minute)))

        max_to_skip = int(len(self.schedule) * uniform(0, TO_SKIP_FACTOR))
        indices = list(range(len(self.schedule)))
        candidates = sample(indices, max_to_skip)
        candidates.sort()
        final_skip = []

        for idx in candidates:
            if (idx - 1 in final_skip) or (idx + 1 in final_skip):
                continue
            final_skip.append(idx)

        for idx in final_skip:
            self.schedule[idx].skipped = True

        return self.schedule
