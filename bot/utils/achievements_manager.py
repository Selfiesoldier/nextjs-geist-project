import logging
from bot.core import profile_manager

logger = logging.getLogger(__name__)

ACHIEVEMENTS = {
    "first_message": {
        "name": "First Message",
        "description": "Send your first message",
        "condition": lambda stats: stats.get("messages", 0) >= 1
    },
    "hundred_messages": {
        "name": "Hundred Messages",
        "description": "Send 100 messages",
        "condition": lambda stats: stats.get("messages", 0) >= 100
    },
    "level_5": {
        "name": "Level 5",
        "description": "Reach level 5",
        "condition": lambda stats: stats.get("level", 1) >= 5
    },
    "time_spent_10h": {
        "name": "10 Hours Spent",
        "description": "Spend 10 hours in chat",
        "condition": lambda stats: stats.get("time_spent", 0) >= 600  # 600 minutes = 10 hours
    }
}

def check_and_unlock_achievements(user_id):
    profiles = profile_manager.load_profiles()
    user = profiles.get(user_id)
    if not user:
        logger.warning(f"User {user_id} not found in profiles for achievements check.")
        return []

    stats = user.get("stats", {})
    unlocked = user.get("achievements", [])

    newly_unlocked = []
    for key, achievement in ACHIEVEMENTS.items():
        if key not in unlocked and achievement["condition"](stats):
            unlocked.append(key)
            newly_unlocked.append(achievement["name"])
            logger.info(f"User {user_id} unlocked achievement: {achievement['name']}")

    if newly_unlocked:
        user["achievements"] = unlocked
        profiles[user_id] = user
        profile_manager.save_profiles(profiles)

    return newly_unlocked
