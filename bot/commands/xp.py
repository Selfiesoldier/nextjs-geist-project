from bot.utils.xp_manager import get_xp, calculate_level, get_leaderboard
from ..core.profile_manager import has_profile

def generate_progress_bar(percentage):
    total_blocks = 10
    filled_blocks = int(percentage * total_blocks)
    empty_blocks = total_blocks - filled_blocks
    return "▓" * filled_blocks + "░" * empty_blocks

class XPCommands:
    def __init__(self, bot):
        self.bot = bot

    async def xp(self, user_id):
        if not has_profile(user_id):
            return "You need to create a profile to view your XP and level."

        xp, level = get_xp(user_id)
        next_level_xp = (level + 1) * 100
        progress = (xp - (level * 100)) / 100 if level > 0 else xp / 100
        progress = max(0, min(progress, 1))  # Clamp between 0 and 1

        progress_bar = generate_progress_bar(progress)
        percent_display = int(progress * 100)

        return f"Your XP: {xp}\nLevel: {level} {progress_bar} ({percent_display}%)"

    async def level(self, user_id):
        # Alias for xp command
        return await self.xp(user_id)

    async def leaderboard(self):
        leaderboard = get_leaderboard(10)
        if not leaderboard:
            return "No users found in leaderboard."

        lines = []
        rank = 1
        for user_id, stats in leaderboard:
            xp = stats.get('xp', 0)
            level = stats.get('level', 1)
            lines.append(f"{rank}. {user_id} — L{level} ({xp} XP)")
            rank += 1

        return "\n".join(lines)

    async def rank(self, user_id):
        if not has_profile(user_id):
            return "You need to create a profile to view your rank."

        leaderboard = get_leaderboard(1000)  # Get top 1000 for ranking
        sorted_users = sorted(leaderboard, key=lambda x: x[1].get('xp', 0), reverse=True)
        total_users = len(sorted_users)

        user_rank = None
        for idx, (uid, stats) in enumerate(sorted_users, start=1):
            if uid == user_id:
                user_rank = idx
                break

        if user_rank is None:
            return "You are not ranked yet."

        return f"You're rank {user_rank} out of {total_users} players."
