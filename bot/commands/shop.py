import json
import os
from bot.core import profile_manager

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
SHOP_ITEMS_FILE = os.path.join(DATA_DIR, 'shop_items.json')

class ShopCommands:
    def __init__(self, bot):
        self.bot = bot

    def load_shop_items(self):
        try:
            with open(SHOP_ITEMS_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    async def shop(self, user_id):
        items = self.load_shop_items()
        if not items:
            return "Shop is currently empty."

        lines = ["Available Shop Items:"]
        for item in items:
            lines.append(f"{item['id']}: {item['name']} - {item['price']} coins")
        return "\n".join(lines)

    async def buy(self, user_id, item_id):
        items = self.load_shop_items()
        item = next((i for i in items if i['id'] == item_id), None)
        if not item:
            return f"Item '{item_id}' not found in shop."

        price = item['price']
        balance = profile_manager.get_wallet(user_id)
        if balance is None:
            return "You need to create a profile to buy items."

        if balance < price:
            return f"Insufficient coins to buy {item['name']}. You have {balance} coins."

        # Deduct coins and add item to inventory
        if not profile_manager.remove_coins(user_id, price):
            return "Failed to deduct coins. Please try again."

        if not profile_manager.add_item(user_id, item_id):
            return "Failed to add item to your inventory."

        return f"You have successfully purchased {item['name']} for {price} coins."

    async def inventory(self, user_id):
        if not profile_manager.has_profile(user_id):
            return "You need to create a profile to view your inventory."

        inventory = profile_manager.get_inventory(user_id)
        if not inventory:
            return "Your inventory is empty."

        items = self.load_shop_items()
        item_map = {item['id']: item['name'] for item in items}

        lines = ["Your Inventory:"]
        for item_id in inventory:
            item_name = item_map.get(item_id, item_id)
            lines.append(f"- {item_name}")
        return "\n".join(lines)

    async def gift(self, user_id, target_user_id, item_id):
        # Admin only command
        profile = profile_manager.get_profile(user_id)
        if not profile or profile.get("role") not in ["admin", "owner"]:
            return "You do not have permission to use this command."

        if not profile_manager.has_profile(target_user_id):
            return "The target user does not have a profile."

        inventory = profile_manager.get_inventory(user_id)
        if item_id not in inventory:
            return "You do not own this item to gift."

        # Remove item from sender
        inventory.remove(item_id)
        profiles = profile_manager.load_profiles()
        profiles[user_id]['inventory'] = inventory

        # Add item to recipient
        recipient_inventory = profile_manager.get_inventory(target_user_id)
        recipient_inventory.append(item_id)
        profiles[target_user_id]['inventory'] = recipient_inventory

        profile_manager.save_profiles(profiles)
        return f"You have gifted {item_id} to user {target_user_id}."
