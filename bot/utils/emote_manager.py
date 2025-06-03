import asyncio
import json
import os
from threading import Lock

EMOTE_DURATIONS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'emote_durations.json')

class EmoteManager:
    def __init__(self, bot):
        self.bot = bot
        self.emote_durations = self.load_emote_durations()
        self.user_locks = {}  # user_id -> asyncio.Lock
        self.user_tasks = {}  # user_id -> asyncio.Task
        self.lock = Lock()

    def load_emote_durations(self):
        try:
            with open(EMOTE_DURATIONS_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get_emote_duration(self, emote_name):
        return self.emote_durations.get(emote_name, 3000) / 1000  # default 3 seconds, convert ms to s

    async def play_emote(self, user_id, emote_name):
        async with self.get_user_lock(user_id):
            duration = self.get_emote_duration(emote_name)
            await self.bot.send_emote(user_id, emote_name)
            await asyncio.sleep(duration)

    def get_user_lock(self, user_id):
        with self.lock:
            if user_id not in self.user_locks:
                self.user_locks[user_id] = asyncio.Lock()
            return self.user_locks[user_id]

    def is_user_looping(self, user_id):
        return user_id in self.user_tasks and not self.user_tasks[user_id].done()

    def stop_user_loop(self, user_id):
        task = self.user_tasks.get(user_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def loop_emote(self, user_id, emote_name):
        if self.is_user_looping(user_id):
            return False  # already looping

        async def loop():
            try:
                while True:
                    await self.play_emote(user_id, emote_name)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(loop())
        self.user_tasks[user_id] = task
        return True

    async def combo_emotes(self, user_id, emote_list):
        if self.is_user_looping(user_id):
            return False  # already looping

        async def combo_loop():
            try:
                while True:
                    for emote in emote_list:
                        await self.play_emote(user_id, emote)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(combo_loop())
        self.user_tasks[user_id] = task
        return True

    async def measure_emotes(self, user_id):
        # Admin command to measure emote durations
        # For now, just return the loaded durations
        return self.emote_durations
