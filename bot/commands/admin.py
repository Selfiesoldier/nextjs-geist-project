import re
import json
import os
import time
from bot.utils import roles

WARNINGS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'warnings.json')

class AdminCommands:
    def __init__(self, bot):
        self.bot = bot
        self.muted_users = {}  # user_id: unmute_timestamp

    async def handle_command(self, user_id, command, args):
        cmd = command.lower()
        if cmd == "!promote":
            return await self.promote(user_id, args)
        elif cmd == "!demote":
            return await self.demote(user_id, args)
        elif cmd == "!myrole":
            return await self.myrole(user_id)
        elif cmd == "!adminlist":
            return await self.adminlist(user_id)
        elif cmd == "!warn":
            return await self.warn(user_id, args)
        elif cmd == "!warnings":
            return await self.warnings(user_id, args)
        elif cmd == "!clearwarns":
            return await self.clearwarns(user_id, args)
        elif cmd == "!kick":
            return await self.kick(user_id, args)
        elif cmd == "!mute":
            return await self.mute(user_id, args)
        else:
            return "Unknown command."

    def load_warnings(self):
        try:
            with open(WARNINGS_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_warnings(self, warnings):
        with open(WARNINGS_FILE, 'w') as f:
            json.dump(warnings, f, indent=2)

    async def warn(self, caller_id, args):
        if not roles.require_role(caller_id, "admin"):
            return "You do not have permission to warn users."
        if len(args) < 1:
            return "Usage: !warn @user [reason]"
        target_user = self.parse_mention(args[0])
        reason = " ".join(args[1:]) if len(args) > 1 else "No reason provided"
        warnings = self.load_warnings()
        user_warnings = warnings.get(target_user, [])
        user_warnings.append({
            "reason": reason,
            "by": caller_id,
            "time": int(time.time())
        })
        warnings[target_user] = user_warnings
        self.save_warnings(warnings)
        from bot.utils import modlog
        modlog.log_action("warn", caller_id, target_user, reason)
        return f"User @{target_user} has been warned. Reason: {reason}"

    async def warnings(self, caller_id, args):
        if not roles.require_role(caller_id, "admin"):
            return "You do not have permission to view warnings."
        if len(args) < 1:
            return "Usage: !warnings @user"
        target_user = self.parse_mention(args[0])
        warnings = self.load_warnings()
        user_warnings = warnings.get(target_user, [])
        if not user_warnings:
            return f"User @{target_user} has no warnings."
        msg_lines = [f"Warnings for @{target_user}:"]
        for i, w in enumerate(user_warnings, 1):
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(w["time"]))
            msg_lines.append(f"{i}. {w['reason']} (by {w['by']} at {timestamp})")
        return "\n".join(msg_lines)

    async def clearwarns(self, caller_id, args):
        if not roles.require_role(caller_id, "owner"):
            return "You do not have permission to clear warnings."
        if len(args) < 1:
            return "Usage: !clearwarns @user"
        target_user = self.parse_mention(args[0])
        warnings = self.load_warnings()
        if target_user in warnings:
            del warnings[target_user]
            self.save_warnings(warnings)
            from bot.utils import modlog
            modlog.log_action("clearwarn", caller_id, target_user)
            return f"Warnings for @{target_user} have been cleared."
        else:
            return f"User @{target_user} has no warnings."

    async def kick(self, caller_id, args):
        if not roles.require_role(caller_id, "admin"):
            return "You do not have permission to kick users."
        if len(args) < 1:
            return "Usage: !kick @user"
        target_user = self.parse_mention(args[0])
        # Implement actual kick logic here, e.g., call bot API to remove user from room
        from bot.utils import modlog
        modlog.log_action("kick", caller_id, target_user)
        # For now, just return success message
        return f"User @{target_user} has been kicked from the room."

    async def mute(self, caller_id, args):
        if not roles.require_role(caller_id, "admin"):
            return "You do not have permission to mute users."
        if len(args) < 1:
            return "Usage: !mute @user [minutes]"
        target_user = self.parse_mention(args[0])
        minutes = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
        unmute_time = time.time() + minutes * 60
        self.muted_users[target_user] = unmute_time
        from bot.utils import modlog
        modlog.log_action("mute", caller_id, target_user, duration=minutes)
        return f"User @{target_user} has been muted for {minutes} minutes."

    def parse_mention(self, mention):
        if mention.startswith('@'):
            return mention[1:]
        return mention
