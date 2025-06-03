from datetime import datetime
import logging
from bot.utils.xp_manager import add_xp
from bot.core import profile_manager
from bot.core import profile_manager

logger = logging.getLogger(__name__)

class EventHandler:
    def __init__(self, bot):
        self.bot = bot
        self.join_times = {}

    async def on_user_join(self, user):
        """Record join time for session tracking"""
        self.join_times[user.id] = datetime.utcnow()
        logger.info(f"User {user.id} joined at {self.join_times[user.id]}")

        # Optional: send welcome message or log

    async def on_user_leave(self, user):
        """Calculate session duration and add XP"""
        join_time = self.join_times.pop(user.id, None)
        if join_time is None:
            logger.warning(f"No join time recorded for user {user.id} on leave")
            return

        leave_time = datetime.utcnow()
        session_duration = (leave_time - join_time).total_seconds() / 60  # minutes
        xp_to_add = int(session_duration)  # 1 XP per full minute

        if profile_manager.has_profile(user.id) and xp_to_add > 0:
            xp, level = add_xp(user.id, xp_to_add)
            logger.info(f"Added {xp_to_add} XP to user {user.id} for session. Total XP: {xp}, Level: {level}")

            # Update time_spent in profile stats
            profile = profile_manager.get_profile(user.id)
            if profile:
                stats = profile.get('stats', {})
                stats['time_spent'] = stats.get('time_spent', 0) + xp_to_add
                profile['stats'] = stats
                profiles = profile_manager.load_profiles()
                profiles[user.id] = profile
                profile_manager.save_profiles(profiles)

    async def on_game_correct_answer(self, user_id):
        if profile_manager.has_profile(user_id):
            # Add XP and coins for correct answer
            add_xp(user_id, 10)
            profile_manager.add_coins(user_id, 20)

    async def on_game_participation(self, user_id):
        if profile_manager.has_profile(user_id):
            # Add XP and coins for participation
            add_xp(user_id, 3)
            profile_manager.add_coins(user_id, 5)

        # Optional: add rare chance to win item (e.g. rose)
        import random
        if profile_manager.has_profile(user_id) and random.random() < 0.05:  # 5% chance
            profile_manager.add_item(user_id, "rose")
            logger.info(f"User {user_id} won a rare item: rose")
