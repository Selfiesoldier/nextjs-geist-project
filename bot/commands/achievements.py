from bot.core import profile_manager
from bot.utils import achievements_manager

class AchievementCommands:
    def __init__(self, bot):
        self.bot = bot

    async def achievements(self, user_id, target_user_id=None):
        # If target_user_id is provided and user is admin, show other's achievements
        if target_user_id and not await self.is_admin(user_id):
            return "You do not have permission to view other users' achievements."

        user_to_check = target_user_id or user_id

        if not profile_manager.has_profile(user_to_check):
            return "User does not have a profile."

        profile = profile_manager.get_profile(user_to_check)
        unlocked_keys = profile.get("achievements", [])
        if not unlocked_keys:
            return "No achievements unlocked yet."

        achievement_names = []
        for key in unlocked_keys:
            achievement = achievements_manager.ACHIEVEMENTS.get(key)
            if achievement:
                achievement_names.append(f"🏆 {achievement['name']}")

        return "Unlocked Achievements:\n" + "\n".join(achievement_names)

    async def achievement(self, user_id, achievement_key):
        # Show description and progress of a specific achievement
        if not profile_manager.has_profile(user_id):
            return "You do not have a profile."

        profile = profile_manager.get_profile(user_id)
        stats = profile.get("stats", {})
        achievement = achievements_manager.ACHIEVEMENTS.get(achievement_key)
        if not achievement:
            return f"Achievement '{achievement_key}' not found."

        unlocked = achievement_key in profile.get("achievements", [])
        progress = "Unlocked" if unlocked else "Locked"

        # Optionally, show progress details if applicable
        description = achievement.get("description", "")
        return f"{achievement['name']} - {description}\nStatus: {progress}"

    async def is_admin(self, user_id):
        # Placeholder for admin check logic
        # Replace with your actual admin role check
        profile = profile_manager.get_profile(user_id)
        if profile and profile.get("role") in ["admin", "owner"]:
            return True
        return False
