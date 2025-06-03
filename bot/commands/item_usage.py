from bot.core import profile_manager
from bot.utils import emote_manager
from bot.utils.xp_manager import add_xp
import asyncio

class ItemUsageCommands:
    def __init__(self, bot):
        self.bot = bot
        self.emote_manager = emote_manager.EmoteManager(bot)

    async def use(self, user_id, item_id):
        if not profile_manager.has_profile(user_id):
            return "You need to create a profile to use items."

        if not profile_manager.has_item(user_id, item_id):
            return f"You do not own the item '{item_id}'."

        # Define item effects
        if item_id == "rose":
            # Perform emote "happy" as example
            await self.emote_manager.play_emote(user_id, "happy")
            effect_msg = "You used a 🌹 Rose and performed a happy emote!"
        elif item_id == "vip-token":
            # Grant VIP role (assuming role management elsewhere)
            profile = profile_manager.get_profile(user_id)
            if profile:
                profile["role"] = "vip"
                profiles = profile_manager.load_profiles()
                profiles[user_id] = profile
                profile_manager.save_profiles(profiles)
            effect_msg = "You used a 🎟️ VIP Token and gained VIP role!"
        elif item_id == "xp-book":
            # Add 100 XP
            xp, level = add_xp(user_id, 100)
            effect_msg = f"You used a 📘 XP Book and gained 100 XP! Total XP: {xp}, Level: {level}"
        else:
            effect_msg = f"You used the item '{item_id}', but it has no effect."

        # Remove item after use (consumable)
        inventory = profile_manager.get_inventory(user_id)
        if item_id in inventory:
            inventory.remove(item_id)
            profiles = profile_manager.load_profiles()
            profiles[user_id]["inventory"] = inventory
            profile_manager.save_profiles(profiles)

        return effect_msg
