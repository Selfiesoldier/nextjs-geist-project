import json
import os
from threading import Lock
from bot.core import profile_manager

_lock = Lock()

def load_user_stats():
    profiles = profile_manager.load_profiles()
    return profiles

def save_user_stats(profiles):
    with _lock:
        profile_manager.save_profiles(profiles)

def calculate_level(xp):
    # Level formula: level = floor(xp / 100)
    return max(1, xp // 100)

def add_xp(user_id, amount):
    profiles = load_user_stats()
    user = profiles.get(user_id, {})
    stats = user.get('stats', {})
    stats['xp'] = stats.get('xp', 0) + amount
    stats['level'] = calculate_level(stats['xp'])
    user['stats'] = stats
    profiles[user_id] = user
    save_user_stats(profiles)
    return stats['xp'], stats['level']

def get_xp(user_id):
    profiles = load_user_stats()
    user = profiles.get(user_id, {})
    stats = user.get('stats', {})
    return stats.get('xp', 0), stats.get('level', 1)

def get_leaderboard(top_n=10):
    profiles = load_user_stats()
    leaderboard = []
    for user_id, user in profiles.items():
        stats = user.get('stats', {})
        leaderboard.append((user_id, stats))
    leaderboard = sorted(leaderboard, key=lambda x: x[1].get('xp', 0), reverse=True)
    return leaderboard[:top_n]
