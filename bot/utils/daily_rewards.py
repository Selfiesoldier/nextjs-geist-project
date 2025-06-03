import time
from datetime import datetime, timedelta
from bot.core import profile_manager

DAILY_REWARD_BASE = 10  # base coins rewarded per claim
DAILY_CLAIM_INTERVAL = 24 * 60 * 60  # 24 hours in seconds

def can_claim_daily(user_id):
    profile = profile_manager.get_profile(user_id)
    if not profile:
        return False, "No profile found."

    last_claim = profile.get("last_daily_claim", 0)
    now = time.time()
    if now - last_claim >= DAILY_CLAIM_INTERVAL:
        return True, None
    else:
        next_claim_time = last_claim + DAILY_CLAIM_INTERVAL
        return False, next_claim_time

def claim_daily(user_id):
    profile = profile_manager.get_profile(user_id)
    if not profile:
        return False, "No profile found."

    can_claim, next_claim_time = can_claim_daily(user_id)
    if not can_claim:
        return False, next_claim_time

    now = time.time()
    last_claim = profile.get("last_daily_claim", 0)
    daily_streak = profile.get("daily_streak", 0)

    # Check if claim is within 48 hours to continue streak, else reset
    if now - last_claim <= 2 * DAILY_CLAIM_INTERVAL:
        daily_streak += 1
    else:
        daily_streak = 1

    reward = DAILY_REWARD_BASE * daily_streak

    # Update profile data
    profile["last_daily_claim"] = now
    profile["daily_streak"] = daily_streak

    profiles = profile_manager.load_profiles()
    profiles[user_id] = profile
    profile_manager.save_profiles(profiles)

    return True, reward

def get_next_claim_time(user_id):
    profile = profile_manager.get_profile(user_id)
    if not profile:
        return None

    last_claim = profile.get("last_daily_claim", 0)
    next_claim = last_claim + DAILY_CLAIM_INTERVAL
    return datetime.fromtimestamp(next_claim)
