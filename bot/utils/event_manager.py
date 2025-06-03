import json
import os
import time
from datetime import datetime, timezone
from bot.core import profile_manager

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
EVENTS_FILE = os.path.join(DATA_DIR, 'events.json')

def load_events():
    try:
        with open(EVENTS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def get_current_events():
    now = datetime.now(timezone.utc)
    events = load_events()
    active_events = []
    for event in events:
        start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))
        if start <= now <= end:
            active_events.append(event)
    return active_events

def get_user_event_progress(user_id, event_id):
    profile = profile_manager.get_profile(user_id)
    if not profile:
        return {}

    event_progress = profile.get('event_progress', {})
    return event_progress.get(event_id, {})

def update_user_event_progress(user_id, event_id, quest_id, progress):
    profiles = profile_manager.load_profiles()
    user = profiles.get(user_id)
    if not user:
        return False

    event_progress = user.get('event_progress', {})
    event_data = event_progress.get(event_id, {})
    event_data[quest_id] = progress
    event_progress[event_id] = event_data
    user['event_progress'] = event_progress
    profiles[user_id] = user
    profile_manager.save_profiles(profiles)
    return True

def check_quest_completion(user_id, event, quest):
    progress = get_user_event_progress(user_id, event['id'])
    current = progress.get(quest['id'], 0)
    target = quest['target']
    return current >= target

def claim_event_reward(user_id, event_id):
    profile = profile_manager.get_profile(user_id)
    if not profile:
        return False, "No profile found."

    events = load_events()
    event = next((e for e in events if e['id'] == event_id), None)
    if not event:
        return False, "Event not found."

    # Check if event is active
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))
    if not (start <= now <= end):
        return False, "Event is not active."

    # Check if all quests completed
    for quest in event.get('quests', []):
        if not check_quest_completion(user_id, event, quest):
            return False, f"Quest '{quest['description']}' not completed."

    # Check if already claimed
    claimed_events = profile.get('claimed_events', [])
    if event_id in claimed_events:
        return False, "Event reward already claimed."

    # Grant rewards
    for reward in event.get('rewards', []):
        item_id = reward.get('item_id')
        quantity = reward.get('quantity', 1)
        for _ in range(quantity):
            profile_manager.add_item(user_id, item_id)

    # Mark event as claimed
    claimed_events.append(event_id)
    profile['claimed_events'] = claimed_events
    profiles = profile_manager.load_profiles()
    profiles[user_id] = profile
    profile_manager.save_profiles(profiles)

    return True, "Event reward claimed successfully."
