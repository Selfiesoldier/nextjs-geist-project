from bot.core import profile_manager

class WalletCommands:
    def __init__(self, bot):
        self.bot = bot

    async def wallet(self, user_id):
        if not profile_manager.has_profile(user_id):
            return "You need to create a profile to view your wallet."

        balance = profile_manager.get_wallet(user_id)
        return f"Your wallet balance: {balance} coins."

    async def tip(self, user_id, target_user_id, amount):
        if not profile_manager.has_profile(user_id):
            return "You need to create a profile to send coins."

        if not profile_manager.has_profile(target_user_id):
            return "The target user does not have a profile."

        if amount <= 0:
            return "Invalid amount to tip."

        if profile_manager.remove_coins(user_id, amount):
            profile_manager.add_coins(target_user_id, amount)
            return f"You have tipped {amount} coins to user {target_user_id}."
        else:
            return "Insufficient coins to tip."

    async def give(self, user_id, target_user_id, amount):
        # Admin only command
        profile = profile_manager.get_profile(user_id)
        if not profile or profile.get("role") not in ["admin", "owner"]:
            return "You do not have permission to use this command."

        if not profile_manager.has_profile(target_user_id):
            return "The target user does not have a profile."

        if amount <= 0:
            return "Invalid amount to give."

        profile_manager.add_coins(target_user_id, amount)
        return f"You have given {amount} coins to user {target_user_id}."
