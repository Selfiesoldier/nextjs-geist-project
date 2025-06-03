"""
Event handlers for user join/leave events with personalized messages.
"""
import time
import logging
from typing import Optional
from highrise.models import User, Position
from ..core.profile_manager import (
    profile_exists, get_profile, load_profiles, save_profiles, 
    track_user_join, track_user_leave, get_user_role
)
from ..utils.role_utils import auto_assign_role
from ..utils.time_formatter import format_time
from ..utils.achievement_manager import get_user_achievements, grant_achievement

logger = logging.getLogger(__name__)

class EventHandler:
    """Handles user join/leave events with personalized messages"""

    def __init__(self, bot):
        self.bot = bot

    async def on_user_join(self, user: User, position: Position) -> None:
        """Handle user joining the room"""
        try:
            print(f"✅ EVENT HANDLER: {user.username} joined the room")

            # Start time tracking
            if hasattr(self.bot, 'chat_handler') and hasattr(self.bot.chat_handler, 'time_handler'):
                self.bot.chat_handler.time_handler.start_session(user.id)

            # Track join in profile system
            track_user_join(user.id)

            # Auto-assign role if they have a profile but no role
            auto_assign_role(user.id)

            # Check if user has a profile
            if profile_exists(user.id):
                # Grant join achievement
                grant_achievement(user.id, "welcome-back", self.bot)

                # Get user's profile and role for personalized message
                profile = get_profile(user.id)
                user_name = profile.get('name', user.username)
                role = get_user_role(user.id)
                
                # Get stats for the welcome message
                stats = profile.get("stats", {})
                total_visits = stats.get("room_joins", 0)
                
                # Calculate total time spent (convert seconds to readable format) 
                total_seconds = int(stats.get("total_time", 0))
                if total_seconds >= 3600:
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    total_time = f"{hours}h {minutes}m"
                elif total_seconds >= 60:
                    minutes = total_seconds // 60
                    total_time = f"{minutes}m"
                else:
                    total_time = f"{total_seconds}s"

                # Get last seen time
                last_seen = stats.get("last_seen", None)
                
                # Generate role-based welcome message
                welcome_msg = self.generate_role_based_welcome(user_name, role, total_time, total_visits, last_seen)

                try:
                    await self.bot.highrise.chat(welcome_msg)
                    print(f"📨 Sent {role} welcome message for {user.username}")
                except Exception as e:
                    print(f"❌ Failed to send welcome message for {user.username}: {e}")
            else:
                # New user - encourage profile creation
                try:
                    new_user_msg = (
                        f"👋 Hello {user.username}!\n"
                        f"💌 Whisper me 'hi' to create your profile and unlock features! ✨"
                    )
                    await self.bot.highrise.send_whisper(user.id, new_user_msg)
                    print(f"📨 Sent new user message to {user.username}")
                except Exception as e:
                    print(f"❌ Failed to send new user message to {user.username}: {e}")

            print(f"✅ EVENT HANDLER: Finished processing join for {user.username}")

        except Exception as e:
            print(f"❌ EVENT HANDLER ERROR: Error handling user join for {user.username}: {e}")

    def generate_role_based_welcome(self, user_name: str, role: str, total_time: str, total_visits: int, last_seen: str = None) -> str:
        """Generate attractive, modular role-based welcome messages"""
        import random
        
        # Get formatted components
        role_message = self._get_role_welcome_message(user_name, role)
        stats_section = self._format_stats_section(total_time, total_visits)
        last_seen_section = self._format_last_seen_section(last_seen, total_visits)
        
        # Build the complete welcome message
        welcome_parts = [role_message, stats_section]
        if last_seen_section:
            welcome_parts.append(last_seen_section)
            
        return "\n".join(welcome_parts)
    
    def _get_role_welcome_message(self, user_name: str, role: str) -> str:
        """Get role-specific welcome message with emojis and flair"""
        import random
        
        role_messages = {
            "owner": [
                f"👑✨ **THE OWNER HAS ARRIVED** ✨👑\n🔥 All hail {user_name}, master of this realm! 🔥",
                f"🌟👑 **ROYAL ENTRANCE** 👑🌟\n⚡ {user_name} graces us with their presence! ⚡",
                f"🔥💎 **SUPREME LEADER DETECTED** 💎🔥\n👑 {user_name} has entered their domain! 👑"
            ],
            "admin": [
                f"🛡️⚔️ **ADMIN ON DUTY** ⚔️🛡️\n🌟 {user_name} the guardian has arrived! 🌟",
                f"⚡🛡️ **PROTECTOR PRESENT** 🛡️⚡\n🔥 {user_name} stands ready to serve! 🔥",
                f"🌟⚔️ **ADMIN ACTIVATED** ⚔️🌟\n💎 {user_name} brings order to the chaos! 💎"
            ],
            "vip": [
                f"💎✨ **VIP EXCLUSIVE ACCESS** ✨💎\n🌟 Everyone welcome {user_name}! 🌟",
                f"🌟💎 **PREMIUM MEMBER SPOTTED** 💎🌟\n✨ {user_name} brings the sparkle! ✨",
                f"💫🔥 **VIP TREATMENT ACTIVATED** 🔥💫\n💎 {user_name} deserves the red carpet! 💎"
            ],
            "user": [
                f"👋✨ **WELCOME ABOARD** ✨👋\n🌟 Great to see you, {user_name}! 🌟",
                f"🎉🌟 **AWESOME ARRIVAL** 🌟🎉\n💫 {user_name} just made our day brighter! 💫",
                f"✨🎊 **FANTASTIC TO SEE YOU** 🎊✨\n🌈 {user_name} brings good vibes! 🌈"
            ]
        }
        
        messages = role_messages.get(role, role_messages["user"])
        return random.choice(messages)
    
    def _format_stats_section(self, total_time: str, total_visits: int) -> str:
        """Format the stats section with attractive styling"""
        # Add visit milestone badges
        visit_badge = self._get_visit_badge(total_visits)
        time_badge = self._get_time_badge(total_time)
        
        return f"📊 **YOUR JOURNEY** 📊\n{time_badge} ⏰ **{total_time}** spent here\n{visit_badge} 🚪 **{total_visits}** visits completed"
    
    def _get_visit_badge(self, visits: int) -> str:
        """Get appropriate badge based on visit count"""
        if visits >= 100: return "🏆"
        elif visits >= 50: return "🥇"
        elif visits >= 25: return "🥈"
        elif visits >= 10: return "🥉"
        elif visits >= 5: return "⭐"
        else: return "🌟"
    
    def _get_time_badge(self, total_time: str) -> str:
        """Get appropriate badge based on time spent"""
        if "h" in total_time:
            hours = int(total_time.split("h")[0])
            if hours >= 24: return "👑"
            elif hours >= 12: return "🔥"
            elif hours >= 6: return "💎"
            elif hours >= 3: return "⚡"
            elif hours >= 1: return "✨"
        return "🌟"
    
    def _format_last_seen_section(self, last_seen: str, total_visits: int) -> str:
        """Format the last seen section with attractive styling"""
        if not last_seen or total_visits <= 1:
            return ""
            
        try:
            from datetime import datetime, timedelta
            
            # Handle different timestamp formats
            if last_seen.endswith('.%f'):
                last_seen = last_seen.replace('.%f', '')
            
            # Parse the timestamp
            if 'T' in last_seen:
                if last_seen.endswith('Z'):
                    last_time = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                else:
                    last_time = datetime.fromisoformat(last_seen)
            else:
                last_time = datetime.fromisoformat(last_seen)
            
            # Convert to IST (+5:30)
            ist_offset = timedelta(hours=5, minutes=30)
            ist_time = last_time + ist_offset
            
            # Format as exact date and time
            formatted_time = ist_time.strftime('%d %b %Y at %I:%M %p')
            return f"🕐 **LAST VISIT** 🕐\n📅 {formatted_time} IST"
            
        except Exception as e:
            print(f"Error parsing last seen time: {e}")
            return ""

    async def on_user_leave(self, user: User) -> None:
        """Handle user leaving the room"""
        try:
            print(f"🚪 EVENT HANDLER: {user.username} left the room")

            # End time tracking
            if hasattr(self.bot, 'chat_handler') and hasattr(self.bot.chat_handler, 'time_handler'):
                duration = self.bot.chat_handler.time_handler.end_session(user.id)
                if duration > 0:
                    print(f"⏰ Tracked {duration:.1f}s for {user.username}")

            # Track leave in profile system
            track_user_leave(user.id)

            # Send farewell message if user has profile
            if profile_exists(user.id):
                try:
                    farewell_msg = await self.generate_farewell_message(user)
                    await self.bot.highrise.chat(farewell_msg)
                    print(f"📨 Sent farewell message for {user.username}")
                except Exception as e:
                    print(f"❌ Failed to send farewell message for {user.username}: {e}")

            # Stop any active emote loops
            if hasattr(self.bot, 'chat_handler') and hasattr(self.bot.chat_handler, 'emote_manager'):
                try:
                    await self.bot.chat_handler.emote_manager.stop_emote_loop(user.id)
                    await self.bot.chat_handler.emote_manager.stop_combo_loop(user.id)
                    if hasattr(self.bot.chat_handler.emote_manager, 'stop_loopall_sequence'):
                        self.bot.chat_handler.emote_manager.stop_loopall_sequence(user.id)
                    print(f"🛑 Stopped emote loops for {user.username}")
                except Exception as e:
                    print(f"⚠️ Error stopping emote loops for {user.username}: {e}")

            print(f"✅ EVENT HANDLER: Finished processing leave for {user.username}")

        except Exception as e:
            print(f"❌ EVENT HANDLER ERROR: Error handling user leave for {user.username}: {e}")

    async def send_new_user_welcome(self, user: User) -> None:
        """Send enhanced welcome message for new users without profiles"""
        # Send public welcome
        public_message = f"🎉 Welcome {user.username}! Whisper 'hi' to start! 🚀"
        await self.bot.highrise.chat(public_message)

        # Send private onboarding whisper
        private_message = (
            f"🌟 Hey {user.username}! Welcome!\n"
            f"• Whisper 'hi' to create profile\n"
            f"• Try '!help' for commands\n"
            f"• Play '!trivia' to earn XP\n"
            f"Ready to begin? 🚀"
        )
        await self.bot.highrise.send_whisper(user.id, private_message)

    def generate_welcome_message(self, username: str, role: str, stats: dict, achievement: Optional[str]) -> str:
        """Generate enhanced level-based welcome message with progression tracking"""
        joins = stats.get("room_joins", 0)
        messages = stats.get("message_count", 0)
        level = self.get_user_level(stats)
        xp = stats.get("xp", 0)
        achievement_text = achievement or "Ready to start your journey!"

        # Get personalized welcome based on role and level
        if role == "owner":
            return self.generate_owner_welcome(username, joins, level, achievement_text)
        elif role == "admin":
            return self.generate_admin_welcome(username, joins, level, achievement_text)
        elif role == "vip":
            return self.generate_vip_welcome(username, joins, level, achievement_text, xp)
        else:
            return self.generate_user_welcome(username, joins, level, achievement_text, xp, messages)

    def get_user_level(self, stats: dict) -> int:
        """Calculate user level based on XP"""
        xp = stats.get("xp", 0)
        if xp >= 1000: return 10
        elif xp >= 800: return 9
        elif xp >= 600: return 8
        elif xp >= 450: return 7
        elif xp >= 350: return 6
        elif xp >= 250: return 5
        elif xp >= 150: return 4
        elif xp >= 100: return 3
        elif xp >= 50: return 2
        else: return 1

    def get_next_level_xp(self, current_level: int) -> int:
        """Get XP needed for next level"""
        level_requirements = {1: 50, 2: 100, 3: 150, 4: 250, 5: 350, 6: 450, 7: 600, 8: 800, 9: 1000, 10: 0}
        return level_requirements.get(current_level + 1, 0)

    def generate_owner_welcome(self, username: str, joins: int, level: int, achievement: str) -> str:
        """Generate owner welcome with command overview"""
        return f"👑 {username} • Lv{level} • #{joins} ✨"

    def generate_admin_welcome(self, username: str, joins: int, level: int, achievement: str) -> str:
        """Generate admin welcome with moderation focus"""
        return f"🛡️ {username} • Lv{level} • #{joins} 🧩"

    def generate_vip_welcome(self, username: str, joins: int, level: int, achievement: str, xp: int) -> str:
        """Generate VIP welcome with special perks highlighted"""
        next_level_xp = self.get_next_level_xp(level)
        progress = ""
        if next_level_xp > 0:
            remaining = next_level_xp - xp
            progress = f" • {remaining}XP"

        return f"💎 {username} • Lv{level} • #{joins}{progress} 💖"

    def generate_user_welcome(self, username: str, joins: int, level: int, achievement: str, xp: int, messages: int) -> str:
        """Generate user welcome with progression guidance"""
        next_level_xp = self.get_next_level_xp(level)

        # Determine welcome tier based on level and engagement
        if level >= 8:
            return self.generate_veteran_welcome(username, joins, level, achievement, xp, next_level_xp)
        elif level >= 5:
            return self.generate_experienced_welcome(username, joins, level, achievement, xp, next_level_xp)
        elif level >= 3:
            return self.generate_developing_welcome(username, joins, level, achievement, xp, next_level_xp)
        else:
            return self.generate_newcomer_welcome(username, joins, level, achievement, xp, next_level_xp, messages)

    def generate_veteran_welcome(self, username: str, joins: int, level: int, achievement: str, xp: int, next_level_xp: int) -> str:
        """Welcome for veteran users (Level 8+)"""
        progress = f" • {next_level_xp - xp}XP" if next_level_xp > 0 else " • MAX!"
        return f"🌟 {username} • Lv{level} • #{joins}{progress} 👑"

    def generate_experienced_welcome(self, username: str, joins: int, level: int, achievement: str, xp: int, next_level_xp: int) -> str:
        """Welcome for experienced users (Level 5-7)"""
        remaining = next_level_xp - xp
        return f"⭐ {username} • Lv{level} • #{joins} • {remaining}XP 🎮"

    def generate_developing_welcome(self, username: str, joins: int, level: int, achievement: str, xp: int, next_level_xp: int) -> str:
        """Welcome for developing users (Level 3-4)"""
        remaining = next_level_xp - xp
        return f"🌱 {username} • Lv{level} • #{joins} • {remaining}XP 🎯"

    def generate_newcomer_welcome(self, username: str, joins: int, level: int, achievement: str, xp: int, next_level_xp: int, messages: int) -> str:
        """Welcome for newcomers (Level 1-2)"""
        remaining = next_level_xp - xp

        if joins == 1:
            # First-time visitor
            return f"🎉 Welcome {username}! • Lv{level} • First! ✨"
        elif messages < 5:
            # Low engagement newcomer
            return f"👋 {username} • Lv{level} • #{joins} • {remaining}XP 🎮"
        else:
            # Engaged newcomer
            return f"🌟 {username} • Lv{level} • #{joins} • {remaining}XP 🎪"

    async def generate_farewell_message(self, user: User) -> str:
        """Generate attractive role-based farewell message"""
        import random
        
        try:
            # Get user data if profile exists
            if not profile_exists(user.id):
                return f"👋✨ Goodbye, {user.username}! Thanks for visiting! ✨"

            profile = get_profile(user.id)
            role = get_user_role(user.id)

            # Ensure role is valid
            if role not in ["user", "vip", "admin", "owner"]:
                role = "user"

            # Get role-specific farewell message
            farewell_message = self._get_role_farewell_message(user.username, role)
            
            print(f"🎭 Generated farewell for {user.username} (role: {role})")
            return farewell_message

        except Exception as e:
            logger.error(f"Error generating farewell message: {e}")
            return f"👋✨ Goodbye, {user.username}! Thanks for visiting! ✨"
    
    def _get_role_farewell_message(self, username: str, role: str) -> str:
        """Get role-specific farewell message with attractive styling"""
        import random
        
        role_farewells = {
            "owner": [
                f"👑💫 **ROYAL DEPARTURE** 💫👑\n🌟 The mighty {username} has left their throne!\n🔥 The realm awaits your return, Your Majesty! 🔥",
                f"🌌👑 **THE CROWN DEPARTS** 👑🌌\n⚡ {username} vanishes into legend...\n✨ Until the sovereign returns! ✨"
            ],
            "admin": [
                f"🛡️⚡ **GUARDIAN OFFLINE** ⚡🛡️\n🌟 Admin {username} has completed their watch!\n💎 The realm is secure in your absence! 💎",
                f"⚔️🌟 **PROTECTOR DEPARTING** 🌟⚔️\n🔥 {username} leaves the battlefield!\n🛡️ Until duty calls again! 🛡️"
            ],
            "vip": [
                f"💎✨ **VIP CHECKOUT** ✨💎\n🌟 Our precious {username} has departed!\n💫 The spotlight dims until your return! 💫",
                f"🌟💎 **PREMIUM EXIT** 💎🌟\n✨ {username} takes their sparkle with them!\n🔥 Come back and light up our world! 🔥"
            ],
            "user": [
                f"👋🌟 **AWESOME DEPARTURE** 🌟👋\n💫 {username} has left the building!\n✨ Hope to see you again soon! ✨",
                f"🎊✨ **UNTIL NEXT TIME** ✨🎊\n🌈 {username} spreads good vibes on the way out!\n🌟 Thanks for making our day brighter! 🌟"
            ]
        }
        
        messages = role_farewells.get(role, role_farewells["user"])
        return random.choice(messages)

    def get_top_achievement(self, user_id: str) -> Optional[str]:
        """Get user's most impressive or recent achievement"""
        try:
            achievements = get_user_achievements(user_id)
            if not achievements:
                return None

            # Priority order for achievements (most impressive first)
            priority_order = [
                "engage-time24h", "engage-join100", "engage-chat500",
                "admin-helper", "vip-status", "loop-master",
                "social-butterfly", "emote-enthusiast", "engage-time6h",
                "engage-join25", "engage-chat200", "engage-time1h",
                "engage-join5", "engage-chat50", "engage-chat10",
                "profile-viewer", "first-emote", "help-seeker", "first-profile"
            ]

            # Find the highest priority achievement the user has
            achievement_ids = [ach.get("id", "") for ach in achievements]
            for priority_id in priority_order:
                if priority_id in achievement_ids:
                    # Find the achievement details
                    for ach in achievements:
                        if ach.get("id") == priority_id:
                            return ach.get("title", "Achievement Unlocked")

            # If no priority match, return the first achievement
            return achievements[0].get("title", "Achievement Unlocked")

        except Exception as e:
            logger.error(f"Error getting top achievement for {user_id}: {e}")
            return None