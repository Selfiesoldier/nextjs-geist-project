from bot.utils import event_manager

class EventCommands:
    def __init__(self, bot):
        self.bot = bot

    async def events(self, user_id):
        active_events = event_manager.get_current_events()
        if not active_events:
            return "No active events at the moment."

        lines = ["Current Active Events:"]
        for event in active_events:
            lines.append(f"{event['id']}: {event['name']} (Ends: {event['end']})")
        return "\n".join(lines)

    async def event(self, user_id):
        active_events = event_manager.get_current_events()
        if not active_events:
            return "No active events at the moment."

        lines = []
        for event in active_events:
            progress = event_manager.get_user_event_progress(user_id, event['id'])
            lines.append(f"Event: {event['name']}")
            for quest in event.get('quests', []):
                current = progress.get(quest['id'], 0)
                target = quest['target']
                lines.append(f" - {quest['description']}: {current}/{target}")
        return "\n".join(lines)

    async def claim(self, user_id, event_id):
        success, message = event_manager.claim_event_reward(user_id, event_id)
        return message
