import asyncio
import logging
from ..core import profile_manager
from ..utils.xp_manager import add_xp
from ..utils import achievements_manager
from ..commands.admin import AdminHandler
from ..utils import emote_manager
import asyncio

logger = logging.getLogger(__name__)

class ChatHandler:
    def __init__(self, bot):
        self.bot = bot
        self.admin_handler = AdminHandler(bot)
        self.emote_manager = emote_manager.EmoteManager(bot)
        self.muted_users = set()  # Optional: track muted users here

    async def on_message(self, user_id: str, message: str):
        # Ignore messages from muted users (optional)
        if user_id in self.muted_users:
            logger.info(f"Ignored message from muted user {user_id}")
            return

        # Check if message is a command (starts with ! or -)
        if message.startswith('!') or message.startswith('-'):
            # Route to command handler
            await self.handle_command(user_id, message)
            return

        # If user has a profile, add XP and increment messages count
        if profile_manager.has_profile(user_id):
            xp, level = add_xp(user_id, 1)
            logger.info(f"Added 1 XP to user {user_id}. Total XP: {xp}, Level: {level}")

            # Increment messages count in profile stats
            profile = profile_manager.get_profile(user_id)
            if profile:
                stats = profile.get('stats', {})
                stats['messages'] = stats.get('messages', 0) + 1
                profile['stats'] = stats
                profiles = profile_manager.load_profiles()
                profiles[user_id] = profile
                profile_manager.save_profiles(profiles)

            # Check and unlock achievements
            newly_unlocked = achievements_manager.check_and_unlock_achievements(user_id)
            if newly_unlocked:
                logger.info(f"User {user_id} unlocked achievements: {newly_unlocked}")

        # Additional chat processing can be added here

    async def handle_command(self, user_id: str, message: str):
        # Emote commands handling
        if message.startswith('!loop'):
            emote_name = message[len('!loop'):].strip()
            if not emote_name:
                logger.info(f"User {user_id} sent !loop without emote name")
                return
            if self.emote_manager.is_user_looping(user_id):
                logger.info(f"User {user_id} already looping an emote")
                return
            await self.emote_manager.loop_emote(user_id, emote_name)
            logger.info(f"User {user_id} started looping emote {emote_name}")
            return

        if message.startswith('!combo'):
            emote_list_str = message[len('!combo'):].strip()
            emote_list = [e.strip() for e in emote_list_str.split(',') if e.strip()]
            if not emote_list:
                logger.info(f"User {user_id} sent !combo without emotes")
                return
            if self.emote_manager.is_user_looping(user_id):
                logger.info(f"User {user_id} already looping an emote combo")
                return
            await self.emote_manager.combo_emotes(user_id, emote_list)
            logger.info(f"User {user_id} started emote combo: {emote_list}")
            return

        if message.startswith('!stop'):
            stopped = self.emote_manager.stop_user_loop(user_id)
            if stopped:
                logger.info(f"User {user_id} stopped emote loop/combo")
            else:
                logger.info(f"User {user_id} tried to stop emote loop/combo but none active")
            return

        if message.startswith('!measureemotes'):
            # Admin only command
            profile = profile_manager.get_profile(user_id)
            if not profile or profile.get('role') not in ['admin', 'owner']:
                logger.info(f"User {user_id} unauthorized to use !measureemotes")
                return
            durations = await self.emote_manager.measure_emotes(user_id)
            logger.info(f"User {user_id} measured emotes: {durations}")
            return

        if message.startswith('!use'):
            item_id = message[len('!use'):].strip()
            if not item_id:
                logger.info(f"User {user_id} sent !use without item id")
                return
            from bot.commands import item_usage
            item_usage_cmds = item_usage.ItemUsageCommands(self.bot)
            result = await item_usage_cmds.use(user_id, item_id)
            logger.info(f"User {user_id} used item {item_id}: {result}")
            return

        if message.startswith('!events'):
            from bot.commands import events
            events_cmds = events.EventCommands(self.bot)
            result = await events_cmds.events(user_id)
            logger.info(f"User {user_id} requested events: {result}")
            return

        if message.startswith('!event'):
            from bot.commands import events
            events_cmds = events.EventCommands(self.bot)
            result = await events_cmds.event(user_id)
            logger.info(f"User {user_id} requested event progress: {result}")
            return

        if message.startswith('!claim'):
            event_id = message[len('!claim'):].strip()
            if not event_id:
                logger.info(f"User {user_id} sent !claim without event id")
                return
            from bot.commands import events
            events_cmds = events.EventCommands(self.bot)
            result = await events_cmds.claim(user_id, event_id)
            logger.info(f"User {user_id} claimed event {event_id}: {result}")
            return

        # For other commands, delegate to admin handler
        if message.startswith(('!warn', '!kick', '!mute', '!clearwarn')):
            response = await self.admin_handler.handle_admin_command(user_id, message)
            logger.info(f"Admin command response: {response}")
        else:
            # Handle other commands or ignore
            logger.info(f"Received command from user {user_id}: {message}")
