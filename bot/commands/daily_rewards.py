from bot.core import profile_manager
from bot.utils import daily_rewards
import datetime

class DailyRewardsCommands:
    def __init__(self, bot):
        self.bot = bot

    async def daily(self, user_id):
        if not profile_manager.has_profile(user_id):
            return "You need to create a profile to claim daily rewards."

        can_claim, result = daily_rewards.can_claim_daily(user_id)
        if not can_claim:
            next_claim_time = datetime.datetime.fromtimestamp(result)
            return f"You have already claimed your daily reward. Next claim available at {next_claim_time.strftime('%Y-%m-%d %H:%M:%S')}."

        success, reward = daily_rewards.claim_daily(user_id)
        if success:
            return f"Daily reward claimed! You received {reward} coins. Keep your streak going!"
        else:
            return "Failed to claim daily reward. Please try again later."

    async def streak(self, user_id):
        if not profile_manager.has_profile(user_id):
            return "You need to create a profile to view your streak."

        profile = profile_manager.get_profile(user_id)
        daily_streak = profile.get("daily_streak", 0)
        next_claim_time = daily_rewards.get_next_claim_time(user_id)
        next_claim_str = next_claim_time.strftime('%Y-%m-%d %H:%M:%S') if next_claim_time else "N/A"

        return f"Your current daily streak is {daily_streak} days. Next claim available at {next_claim_str}."
