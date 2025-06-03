import json
import os
from threading import Lock

PROFILES_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'profiles.json')
_lock = Lock()

def load_profiles():
    try:
        with open(PROFILES_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_profiles(profiles):
    with _lock:
        with open(PROFILES_FILE, 'w') as f:
            json.dump(profiles, f, indent=2)

def has_profile(user_id):
    profiles = load_profiles()
    return user_id in profiles

def get_profile(user_id):
    profiles = load_profiles()
    return profiles.get(user_id)

def create_profile(user_id, name, birthday=None, age=None):
    profiles = load_profiles()
    if user_id in profiles:
        return False  # Profile already exists
    profiles[user_id] = {
        "name": name,
        "birthday": birthday,
        "age": age,
        "stats": {
            "messages": 0,
            "time_spent": 0,
            "xp": 0,
            "level": 1,
            "games_played": 0,
            "room_joins": 0
        },
        "wallet": {
            "coins": 0
        }
    }
    save_profiles(profiles)
    return True

def delete_profile(user_id):
    profiles = load_profiles()
    if user_id in profiles:
        del profiles[user_id]
        save_profiles(profiles)
        return True
    return False

def get_inventory(user_id):
    profiles = load_profiles()
    user = profiles.get(user_id)
    if not user:
        return []
    inventory = user.get("inventory", [])
    return inventory

def add_item(user_id, item_id):
    profiles = load_profiles()
    user = profiles.get(user_id)
    if not user:
        return False
    inventory = user.get("inventory", [])
    inventory.append(item_id)
    user["inventory"] = inventory
    profiles[user_id] = user
    save_profiles(profiles)
    return True

def has_item(user_id, item_id):
    inventory = get_inventory(user_id)
    return item_id in inventory

def get_wallet(user_id):
    profiles = load_profiles()
    user = profiles.get(user_id)
    if not user:
        return None
    wallet = user.get("wallet", {})
    return wallet.get("coins", 0)

def add_coins(user_id, amount):
    profiles = load_profiles()
    user = profiles.get(user_id)
    if not user:
        return False
    wallet = user.get("wallet", {})
    wallet["coins"] = wallet.get("coins", 0) + amount
    user["wallet"] = wallet
    profiles[user_id] = user
    save_profiles(profiles)
    return True

def remove_coins(user_id, amount):
    profiles = load_profiles()
    user = profiles.get(user_id)
    if not user:
        return False
    wallet = user.get("wallet", {})
    current_coins = wallet.get("coins", 0)
    if current_coins < amount:
        return False
    wallet["coins"] = current_coins - amount
    user["wallet"] = wallet
    profiles[user_id] = user
    save_profiles(profiles)
    return True

def transfer_coins(from_id, to_id, amount):
    if amount <= 0:
        return False
    profiles = load_profiles()
    from_user = profiles.get(from_id)
    to_user = profiles.get(to_id)
    if not from_user or not to_user:
        return False
    from_wallet = from_user.get("wallet", {})
    to_wallet = to_user.get("wallet", {})
    if from_wallet.get("coins", 0) < amount:
        return False
    from_wallet["coins"] -= amount
    to_wallet["coins"] = to_wallet.get("coins", 0) + amount
    from_user["wallet"] = from_wallet
    to_user["wallet"] = to_wallet
    profiles[from_id] = from_user
    profiles[to_id] = to_user
    save_profiles(profiles)
    return True
