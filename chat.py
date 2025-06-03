"""Modified chat handler to include poll answer processing and command."""
import logging
from highrise.models import User
from ..core.profile_manager import profile_exists, track_message_sent
from ..utils.emote_manager import EmoteManager
from .admin import AdminHandler
from ..utils.role_utils import auto_assign_role
from ..utils.achievement_manager import grant_achievement, track_user_action, check_engagement_achievements
from ..commands.achievements import AchievementsHandler
from ..commands.stats import StatsHandler
from ..commands.games import GameCommands
from ..utils.teleport_manager import teleport_manager
from ..utils.message_chunker import MessageChunker
import asyncio
from highrise.models import Position
from ..commands.time_stats import TimeStatsHandler
from ..utils.poll_manager import poll_manager

logger = logging.getLogger(__name__)


class ChatHandler:
    """Handles basic chat and emote commands"""

    def __init__(self, bot):
        self.bot = bot
        self.emote_manager = EmoteManager(bot)
        self.admin_handler = AdminHandler(bot)
        self.achievements_handler = AchievementsHandler(bot)
        self.stats_handler = StatsHandler(bot)
        self.game_commands = GameCommands(bot)
        self.default_position = Position(16.5, 0.1, 14, "FrontRight")  # set the bots default location to 16.5,0.1,14
        self.bot_position = self.default_position
        self.time_handler = TimeStatsHandler(bot)

        # Follow and circle state with locks for thread safety
        self.following_user = None
        self.follow_active = False
        self.circling_user = None
        self.circle_active = False
        self._movement_lock = asyncio.Lock()  # Prevent concurrent movement commands

    async def on_chat(self, user: User, message: str) -> None:
        """Handle all chat messages and route commands"""
        try:
            # Track message for registered users
            from ..core.profile_manager import profile_exists, track_message_sent
            if profile_exists(user.id):
                track_message_sent(user.id)

            # Process commands
            await self.process_commands(user, message)

        except Exception as e:
            print(f"❌ Error handling chat from {user.username}: {e}")

    async def process_commands(self, user: User, message: str) -> None:
        """Process chat commands"""
        try:
            message_lower = message.lower().strip()

            # PRIORITY 1: Check for pending game answers FIRST (before any other processing)

            # Check for trivia answers (they use A,B,C,D format)
            from ..utils.trivia_manager import trivia_manager
            if trivia_manager.has_pending_question(user.id):
                if message.upper() in ['A', 'B', 'C', 'D']:
                    try:
                        await trivia_manager.process_answer(self.bot, user, message)
                    except Exception as e:
                        logger.error(f"Error processing trivia answer: {e}")
                    return

            # Check for math answers - MUST come before emote check (no command restriction)
            if user.id in self.game_commands.pending_math:
                if await self.game_commands.process_math_answer(user, message):
                    return

            # Check for riddle answers - MUST come before emote check (no command restriction)
            if user.id in self.game_commands.pending_riddles:
                if await self.game_commands.process_riddle_answer(user, message):
                    return

            # PRIORITY 2: Handle numbered emote commands (1-182) - before command checks
            msg = message.strip()

            # Check for numbered emotes (1-182) - should loop
            if msg.isdigit():
                emote_number = int(msg)
                if 1 <= emote_number <= 182:
                    # Handle emote loop
                    await self.handle_numbered_emote_loop(user, emote_number)
                    return

            # Check for emote names (perform once)
            if msg.startswith("emote-") or msg.startswith("dance-") or msg.startswith("idle_"):
                await self.handle_emote_name_single(user, msg)
                return

            # Check for loop emote names (with - prefix)
            if msg.startswith("-") and len(msg) > 1:
                emote_name = msg[1:]  # Remove the - prefix
                if emote_name.startswith("emote-") or emote_name.startswith("dance-") or emote_name.startswith("idle_"):
                    await self.handle_emote_name_loop(user, emote_name)
                    return

            # PRIORITY 3: Check if message is a command
            if not (message_lower.startswith('!') or message_lower.startswith('-')):
                # Track message for stats if user has profile
                from ..core.profile_manager import profile_exists, track_message_sent
                if profile_exists(user.id):
                    track_message_sent(user.id)
                return

            # Check if user has a profile (registered user) for commands
            from ..core.profile_manager import profile_exists
            if not profile_exists(user.id):
                await self.bot.highrise.send_whisper(user.id, f"❌ You need to create a profile first!\n💌 Whisper me 'hi' to get started and create your profile! 😊")
                return

            # Check for help command first
            if message_lower == "-help":
                await self.show_help(user)
                track_user_action(user.id, "command_used", self.bot)
                grant_achievement(user.id, "help-seeker", self.bot)

            # Role-specific help commands
            elif message_lower == "!adminhelp":
                await self.show_admin_help(user)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower == "!viphelp":
                await self.show_vip_help(user)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower == "!ownerhelp":
                await self.show_owner_help(user)
                track_user_action(user.id, "command_used", self.bot)

            # Emotes list command with dash prefix - strict output
            elif message_lower == "-emoteslist":
                await self.show_emotes_list(user)
                track_user_action(user.id, "command_used", self.bot)

            # Profile command with dash prefix
            elif message_lower == "-profile":
                await self.show_profile_info(user)
                track_user_action(user.id, "profile_viewed", self.bot)
                track_user_action(user.id, "command_used", self.bot)

            # My role command with dash prefix
            elif message_lower == "-my role":
                await self.show_my_role(user)

            # Delete profile command with dash prefix
            elif message_lower == "-delete profile":
                await self.show_delete_profile(user)

            # Info command with dash prefix
            elif message_lower == "-info":
                await self.show_info(user)

            # Stop emote loop command (handles both single and combo loops)
            elif message_lower == "-stop":
                await self.handle_stop_loop(user)

            # Combo loop command (!loop 12 45 88)
            elif message_lower.startswith("!loop"):
                await self.handle_combo_loop(user, message)

            # Duration command (!duration 12)
            elif message_lower.startswith("!duration"):
                await self.handle_duration_command(user, message)

            # Loop all emotes command (!loopall) - admin only
            elif message_lower == "!loopall":
                await self.handle_loopall_command(user)

            # Measure emotes command
            elif message_lower == "!measureemotes":
                await self.handle_measure_emotes(user)

            elif message_lower == "!testcommands":
                await self.handle_test_commands(user)

            elif message_lower == "!testall":
                await self.handle_test_all(user)

            elif message_lower == "!testemotes":
                await self.handle_test_emotes(user)
            elif message_lower == "!learning on":
                await self.handle_learning_mode(user, True)
            elif message_lower == "!learning off":
                await self.handle_learning_mode(user, False)
            elif message_lower == "!learnstatus":
                await self.handle_learning_status(user)

            # Achievements command
            elif message_lower.startswith("!achievements"):
                await self.achievements_handler.handle_achievements_command(user, message)
                track_user_action(user.id, "command_used", self.bot)

            # Stats command
            elif message_lower.startswith("!stats"):
                await self.stats_handler.handle_stats_command(user, message)
                track_user_action(user.id, "command_used", self.bot)

            # Game commands - both ! and - prefixes
            elif message_lower in ["!games", "-games", "-game"]:
                await self.game_commands.handle_games_menu(user)
            elif message_lower in ["!games2", "-games2"]:
                await self.game_commands.handle_games_menu2(user)
            elif message_lower in ["!coinflip", "-coinflip"]:
                await self.game_commands.handle_coinflip(user)
            elif message_lower.startswith("!8ball") or message_lower.startswith("-8ball"):
                await self.game_commands.handle_8ball(user, message)
            elif message_lower.startswith("!rps") or message_lower.startswith("-rps"):
                await self.game_commands.handle_rps(user, message)
            elif message_lower in ["!trivia", "-trivia"]:
                await self.game_commands.handle_trivia(user)
            elif message_lower in ["!triviastats", "-triviastats"]:
                await self.game_commands.handle_trivia_stats(user)
            elif message_lower in ["!gamestats", "-gamestats"]:
                await self.game_commands.handle_game_stats(user)
            elif message_lower.startswith("!joke") or message_lower.startswith("-joke"):
                await self.game_commands.handle_joke(user, message)
            elif message_lower in ["!would", "-would"]:
                await self.game_commands.handle_would(user)
            elif message_lower.startswith("!pickup") or message_lower.startswith("-pickup"):
                await self.game_commands.handle_pickup(user, message)
            elif message_lower.startswith("!roast") or message_lower.startswith("-roast"):
                await self.game_commands.handle_roast(user, message)
            elif message_lower.startswith("!roll") or message_lower.startswith("-roll"):
                await self.game_commands.handle_roll(user, message)
            elif message_lower in ["!fact", "-fact"]:
                await self.game_commands.handle_fact(user)
            elif message_lower in ["!quote", "-quote"]:
                await self.game_commands.handle_quote(user)
            elif message_lower in ["!fortune", "-fortune"]:
                await self.game_commands.handle_fortune(user)
            elif message_lower.startswith("!math") or message_lower.startswith("-math"):
                await self.game_commands.handle_math(user, message)
            elif message_lower.startswith("!riddle") or message_lower.startswith("-riddle"):
                await self.game_commands.handle_riddle(user, message)
            elif message_lower in ["!quiz", "-quiz"]:
                await self.game_commands.handle_quiz(user)

            # Poll commands
            elif message_lower.startswith("!poll") or message_lower.startswith("-poll"):
                await self.handle_poll_command(user, message)
            elif message_lower.startswith("!vote") or message_lower.startswith("-vote"):
                await self.handle_vote_command(user, message)
            elif message_lower in ["!pollresults", "-pollresults", "!results", "-results"]:
                await self.handle_poll_results_command(user)
            elif message_lower in ["!closepoll", "-closepoll", "!endpoll", "-endpoll"]:
                await self.handle_close_poll_command(user)

            # Teleportation commands with - prefix
            elif message_lower.startswith("-summon "):
                await self.handle_summon_command(user, message[1:])  # Remove the '-'
            elif message_lower.startswith("-goto "):
                await self.handle_goto_command(user, message[1:])  # Remove the '-'
            elif message_lower == "-summon bot":
                await self.handle_summon_bot(user)
            elif message_lower == "-goto bot":
                await self.handle_goto_bot(user)
            elif message_lower.startswith("-teleport "):
                await self.handle_teleport_command(user, message[1:])  # Remove the '-'
            elif message_lower.startswith("-locate "):
                await self.handle_locate_command(user, message[1:])  # Remove the '-'
            elif message_lower.startswith("-createtp "):
                await self.handle_create_teleport(user, message[1:])
            elif message_lower.startswith("-deletetp "):
                await self.handle_delete_teleport(user, message[1:])
            elif message_lower.startswith("-tp "):
                await self.handle_teleport_to(user, message[1:])
            elif message_lower == "-listtp":
                await self.handle_list_teleports(user)

            # Bot movement commands
            elif message_lower == "!follow":
                await self.handle_follow_command(user)
            elif message_lower == "!unfollow":
                await self.handle_unfollow_command(user)
            elif message_lower == "!circle":
                await self.handle_circle_command(user)
            elif message_lower == "!uncircle":
                await self.handle_uncircle_command(user)
            elif message_lower == "!botpos":
                await self.handle_botpos_command(user)
            elif message_lower.startswith("!setbotpos"):
                await self.handle_setbotpos_command(user, message)
            elif message_lower == "!resetbotpos":
                await self.handle_resetbotpos_command(user)

            # Admin commands (role management and moderation)
            elif message_lower.startswith(("!promote", "!demote", "!addvip", "!adminlist", "!myrole", "!roleinfo", "!mute", "!kick", "!warn", "!clearwarn", "!announce", "!totalusers", "!invite")):
                # Auto-assign role if missing for existing profiles
                auto_assign_role(user.id)
                await self.admin_handler.handle_admin_command(user, message)
                track_user_action(user.id, "command_used", self.bot)

            # Bot emote commands (b1-b182) - perform emote on bot for tracking
            elif message_lower.startswith("b") and message_lower[1:].isdigit():
                emote_num = int(message_lower[1:])
                if 1 <= emote_num <= 182:
                    await self.handle_bot_emote(user, emote_num)

            # Relationship commands
            elif message_lower.startswith("!ship"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_ship_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!love"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_love_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!hate"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_hate_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!marry"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_marry_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower in ["!accept", "!yes"]:
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_accept_command(user)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower in ["!reject", "!no"]:
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_reject_command(user)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower == "!divorce":
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_divorce_command(user)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!crush"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_crush_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!compatibility"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_compatibility_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!rizz"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_rizz_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!simp"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_simp_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!friendship"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_friendship_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!married"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_married_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower in ["!marriagestats", "!marriagestat"]:
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_marriage_stats_command(user)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!jealousy"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_jealousy_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!trust"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_trust_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!loyalty"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_loyalty_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower.startswith("!chemistry"):
                from ..utils.relationship_manager import RelationshipManager
                relationship_manager = RelationshipManager(self.bot)
                await relationship_manager.handle_chemistry_command(user, message)
                track_user_action(user.id, "command_used", self.bot)
            elif message_lower == "!relationshiphelp":
                from ..commands.relationship_help import RelationshipHelp
                relationship_help = RelationshipHelp(self.bot)
                await relationship_help.show_relationship_help(user)
                track_user_action(user.id, "command_used", self.bot)

            # Time statistics command
            elif message_lower.startswith('-time') and len(message.split()) > 1:
                # Handle time query for location
                from ..utils.weather_time import WeatherTimeService
                weather_time_service = WeatherTimeService()
                location = " ".join(message.split()[1:])

                time_data = await weather_time_service.get_time(location)
                formatted_message = weather_time_service.format_time_message(time_data)
                await self.bot.highrise.send_whisper(user.id, formatted_message)

            elif message_lower.startswith('-time') or message_lower.startswith('!time'):
                # Check if this is a location time query (has arguments) or user time stats
                parts = message.split()
                if len(parts) > 1:
                    # Handle location time query
                    from ..utils.weather_time import WeatherTimeService
                    weather_time_service = WeatherTimeService()

                    location = " ".join(parts[1:])
                    time_data = await weather_time_service.get_time(location)
                    formatted_message = weather_time_service.format_time_message(time_data)
                    await self.bot.highrise.send_whisper(user.id, formatted_message)
                else:
                    # Handle user's own time stats
                    await self.time_handler.handle_time_command(user, message)

            elif message_lower.startswith('-weather') or message_lower.startswith('!weather'):
                # Handle weather query
                from ..utils.weather_time import WeatherTimeService
                weather_time_service = WeatherTimeService()

                if len(message.split()) > 1:
                    location = " ".join(message.split()[1:])
                    weather_data = await weather_time_service.get_weather(location)
                    formatted_message = weather_time_service.format_weather_message(weather_data)
                    await self.bot.highrise.send_whisper(user.id, formatted_message)
                else:
                    await self.bot.highrise.send_whisper(user.id, "❌ Please specify a location. Example: -weather New York or -weather London,UK")

            elif message_lower.startswith('-stop') or message_lower.startswith('!stop'):
                await self.handle_stop_loop(user)

            # Add time and weather commands
            # Stop emote loop command (handles both single and combo loops)

            msg = message_lower
            # Handle friend emote commands: -(number) user1 user2 user3... or -(number)(username)
            if msg.startswith('-') and len(msg) > 1:
                # Check if it's the new format with spaces: -(number) user1 user2...
                if ' ' in msg:
                    parts = msg.split()
                    if len(parts) >= 2:
                        # Extract emote number from first part like "-42"
                        emote_part = parts[0][1:]  # Remove the '-'
                        if emote_part.isdigit():
                            emote_number = int(emote_part)
                            usernames = [part.lstrip('@') for part in parts[1:]]  # Remove @ if present from all usernames

                            if 1 <= emote_number <= 182:
                                await self.handle_friend_emote_multiple(user, emote_number, usernames)
                                return

                # Fallback to old format: -(number)(username)
                remaining = msg[1:]  # Remove the '-'
                number_str = ""
                username_part = ""

                for i, char in enumerate(remaining):
                    if char.isdigit():
                        number_str += char
                    else:
                        username_part = remaining[i:]
                        break

                if number_str and username_part:
                    try:
                        emote_number = int(number_str)
                        target_username = username_part.lstrip('@')  # Remove @ if present

                        if 1 <= emote_number <= 182:
                            await self.handle_friend_emote(user, emote_number, target_username)
                            return
                    except ValueError:
                        pass

            # Track message for stats
            from ..core.profile_manager import track_message_sent
            track_message_sent(user.id)

            # Check for engagement achievements
            from ..utils.achievement_manager import check_engagement_achievements
            check_engagement_achievements(user.id, self.bot)

            # Log all messages
            print(f"💬 {user.username}: {message}")

        except Exception as e:
            print(f"❌ Error in chat handler: {e}")
            await self.bot.highrise.send_whisper(user.id, "❌ Something went wrong!")
# do not add or remove anything to help unless the usre explictly says to do so
    async def send_chunked_whisper(self, user_id: str, message: str):
        """Send a whisper message using chunking if needed"""
        await MessageChunker.send_chunked_whisper(self.bot, user_id, message)

    async def show_help(self, user: User) -> None:
        """Show help menu - divided into chunks to prevent message length errors"""
        help_message = (
            "🤖 Bot Commands\n"
            "📝 Whisper 'hi' to create profile\n"
            "📩 Send me a DM for private help!\n\n"
            "🎮 Games: -games -trivia -coinflip\n"
            "📊 Profile: -profile -stats\n"
            "🎭 Emotes: Type 1-182\n"
            "🔄 Loop: !loop 12 45\n"
            "⏹️ Stop: -stop\n"
            "💕 Romance: !ship !marry !love !trust\n"
            "📍 Teleport: -tp -listtp\n"
            "❓ !relationshiphelp for more\n"
            "➕Check BIO for more❤️\n"
        )
        await self.send_chunked_whisper(user.id, help_message)

    async def show_admin_help(self, user: User) -> None:
        """Show admin-specific help commands"""
        from ..utils.role_utils import has_permission

        if not has_permission(user.id, "admin"):
            await self.send_chunked_whisper(user.id, "🚫 You need admin permissions to view this help.")
            return

        admin_help = (
            "🛡️ ADMIN COMMANDS\n\n"
            "👥 User: !promote !demote !addvip !adminlist\n"
            "⚡ Mod: !mute !kick !warn !clearwarn\n"
            "📍 Manage: -createtp -deletetp\n"
            "📢 Other: !announce !totalusers !invite !myrole\n"
            "🧪 Test: !testdm !dmtest @user [message]\n\n"
            "Plus all VIP commands: teleports, roleinfo, etc."
        )
        await self.send_chunked_whisper(user.id, admin_help)

    async def show_vip_help(self, user: User) -> None:
        """Show VIP-specific help commands"""
        from ..utils.role_utils import has_permission

        if not has_permission(user.id, "vip"):
            await self.send_chunked_whisper(user.id, "🚫 You need VIP permissions to view this help.")
            return

        vip_help = (
            "⭐ VIP COMMANDS\n\n"
            "📢 !announce\n"
            "👥 !roleinfo @user\n"
            "📍 -tp -listtp\n"
            "📍 -summon @user/-summon bot\n"
            "📍 -goto @user/-goto bot\n"
            "📍 -teleport (x,y,z)\n"
            "📍 -locate @user\n"
            "🤖 !follow !unfollow\n"
            "🔄 !circle !uncircle\n\n"
            "Plus user commands"
        )
        await self.send_chunked_whisper(user.id, vip_help)

    async def show_owner_help(self, user: User) -> None:
        """Show owner-specific help commands"""
        from ..utils.role_utils import has_permission

        if not has_permission(user.id, "owner"):
            await self.send_chunked_whisper(user.id, "🚫 You need owner permissions to view this help.")
            return

        owner_help = (
            "👑 OWNER COMMANDS\n\n"
            "🔧 System: !learning !measureemotes !testemotes\n"
            "🤖 Bot: !setbotpos !botpos !resetbotpos\n"
            "🎭 Emotes: !loopall !duration b1-b182\n"
            "👥 Users: All admin/vip commands\n\n"
            "Plus all user commands: -games -profile etc."
        )
        await self.send_chunked_whisper(user.id, owner_help)

    async def show_emotes_list(self, user: User) -> None:
        """Show emotes list instruction - strict output only"""
        await self.bot.highrise.send_whisper(user.id, "Enter a number from 1 to 182 to perform an emote.")

    async def show_profile_info(self, user: User) -> None:
        """Show profile command - call the actual profile handler"""
        from ..commands.profile import ProfileHandler
        profile_handler = ProfileHandler(self.bot)
        try:
            await profile_handler.handle_profile_command(user)
        except Exception as e:
            logger.error(f"Error handling profile command: {e}")

    async def show_my_role(self, user: User) -> None:
        """Show my role command - redirect to role system"""
        await self.admin_handler.handle_admin_command(user, "!myrole")

    async def show_delete_profile(self, user: User) -> None:
        """Show delete profile command - redirect to bot's delete handler"""
        await self.bot.highrise.send_whisper(user.id, "Delete profile feature is handled by the main bot. Whisper 'hi' to access it.")

    async def show_info(self, user: User) -> None:
        """Show info command - basic bot info"""
        await self.bot.highrise.send_whisper(user.id, "Simple Bot v1.0\nUse -help for commands\nUse numbers 1-182 for emote loops\nUse -stop to stop loops")

    async def handle_stop_loop(self, user: User) -> None:
        """Handle stop loop command (single, combo, and loopall sequences)"""
        try:
            stopped_single = False
            stopped_combo = False
            stopped_loopall = False
            total_stopped = 0

            # Try to stop single emote loops
            if user.id in self.emote_manager.active_loops and self.emote_manager.active_loops[user.id]:
                total_stopped += len(self.emote_manager.active_loops[user.id])
                stopped_single = await self.emote_manager.stop_emote_loop(user.id)

            # Try to stop combo loops
            if user.id in self.emote_manager.active_combo_loops and self.emote_manager.active_combo_loops[user.id]:
                total_stopped += len(self.emote_manager.active_combo_loops[user.id])
                stopped_combo = self.emote_manager.stop_combo_loop(user.id)

            # Try to stop loopall sequences
            if hasattr(self.emote_manager, 'active_loopall_sequences') and user.id in self.emote_manager.active_loopall_sequences and self.emote_manager.active_loopall_sequences[user.id]:
                total_stopped += len(self.emote_manager.active_loopall_sequences[user.id])
                stopped_loopall = self.emote_manager.stop_loopall_sequence(user.id)

            if stopped_single or stopped_combo or stopped_loopall:
                loop_types = []
                if stopped_single:
                    loop_types.append("single")
                if stopped_combo:
                    loop_types.append("combo")
                if stopped_loopall:
                    loop_types.append("loopall")

                await self.bot.highrise.send_whisper(user.id, 
                    f"🛑 Stopped {total_stopped} emote loops!\n"
                    f"Types stopped: {', '.join(loop_types)}")
            else:
                await self.bot.highrise.send_whisper(user.id, "❌ No active emote loops found.")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error stopping loops: {str(e)}")
            print(f"❌ Error stopping loops for {user.username}: {e}")

    async def handle_combo_loop(self, user: User, message: str) -> None:
        """Handle combo loop command (!loop 12 45 88)"""
        try:
            # Parse emote IDs from message
            parts = message.split()[1:]  # Skip "!loop"

            if not parts:
                await self.bot.highrise.send_whisper(user.id, 
                    "❌ Usage: !loop <emote1> <emote2> <emote3>\n"
                    "Example: !loop 12 45 88\n"
                    "Max 10 emotes, use numbers 1-182")
                return

            # Convert to integers and validate
            emote_ids = []
            invalid_parts = []

            for part in parts:
                if part.isdigit():
                    emote_id = int(part)
                    if 1 <= emote_id <= 182:
                        emote_ids.append(emote_id)
                    else:
                        invalid_parts.append(part)
                else:
                    invalid_parts.append(part)

            # Validation checks
            if not emote_ids:
                await self.bot.highrise.send_whisper(user.id, 
                    "❌ No valid emote IDs found!\n"
                    "Use numbers 1-182 only")
                return

            if len(emote_ids) > 10:
                await self.bot.highrise.send_whisper(user.id, 
                    f"❌ Too many emotes! Max 10 allowed, you provided {len(emote_ids)}")
                return

            # Show warning for invalid parts
            if invalid_parts:
                await self.bot.highrise.send_whisper(user.id, 
                    f"⚠️ Ignored invalid inputs: {', '.join(invalid_parts)}")

            # Check if user already has a combo loop
            if self.emote_manager.is_combo_loop_active(user.id):
                await self.bot.highrise.send_whisper(user.id, 
                    "🔄 Stopping current combo loop and starting new one...")

            # Start the combo loop
            success = await self.emote_manager.start_combo_loop(user.id, emote_ids)

            if success:
                # Get emote names for display
                emote_names = []
                for emote_id in emote_ids[:5]:  # Show first 5
                    name = self.emote_manager.get_emote_name_by_id(emote_id)
                    if name:
                        emote_names.append(f"#{emote_id}")

                display_emotes = " → ".join(emote_names)
                if len(emote_ids) > 5:
                    display_emotes += f" + {len(emote_ids) - 5} more"

                await self.bot.highrise.send_whisper(user.id, 
                    f"🎭 Started combo loop!\n"
                    f"Sequence: {display_emotes}\n"
                    f"Total emotes: {len(emote_ids)}\n"
                    f"Type '-stop' to stop the loop")

                print(f"✅ {user.username} started combo loop: {emote_ids}")
            else:
                await self.bot.highrise.send_whisper(user.id, 
                    "❌ Failed to start combo loop!")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error starting combo loop: {str(e)}")
            print(f"❌ Error handling combo loop for {user.username}: {e}")

    async def handle_duration_command(self, user: User, message: str) -> None:
        """Handle duration command (!duration 12)"""
        try:
            parts = message.split()
            if len(parts) != 2:
                await self.bot.highrise.send_whisper(user.id, 
                    "❌ Usage: !duration <emote_id>\n"
                    "Example: !duration 12")
                return

            emote_input = parts[1]
            if not emote_input.isdigit():
                await self.bot.highrise.send_whisper(user.id, 
                    "❌ Please provide a valid emote number (1-182)")
                return

            emote_id = int(emote_input)
            if not (1 <= emote_id <= 182):
                await self.bot.highrise.send_whisper(user.id, 
                    "❌ Emote ID must be between 1 and 182")
                return

            # Get emote name and duration
            emote_name = self.emote_manager.get_emote_name_by_id(emote_id)
            if not emote_name:
                await self.bot.highrise.send_whisper(user.id, 
                    f"❌ Emote #{emote_id} not found")
                return

            duration = self.emote_manager.get_emote_duration(emote_name)
            learned_count = len(self.emote_manager.emote_durations)

            await self.bot.highrise.send_whisper(user.id, 
                f"⏱️ Emote #{emote_id}: {emote_name}\n"
                f"Duration: {duration:.1f} seconds\n"
                f"📊 ({learned_count} emotes learned)")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error checking duration: {str(e)}")
            print(f"❌ Error handling duration command for {user.username}: {e}")

    async def handle_measure_emotes(self, user: User) -> None:
        """Handle measure emotes command"""
        try:
            # Check if user has admin permissions or is owner
            # For now, allow anyone to measure (you can add permission checks)
            await self.bot.highrise.send_whisper(user.id, "📊 Starting emote measurement process...")
            await self.emote_manager.measure_all_emotes(self)
        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error measuring emotes: {str(e)}")
            print(f"❌ Error measuring emotes: {e}")

    def get_all_emotes(self) -> list:
        """Get all emote names for measurement - same order as numbered list"""
        emotes = [
            # ALL FREE EMOTES (1-182) - Based on console test results
            # 1-20: Verified free emotes
            "emote-bow", "emote-curtsy", "emote-snowangel", "emote-confused", "emote-teleporting",
            "emote-swordfight", "dance-weird", "dance-tiktok2", "idle_layingdown", "emote-hot",
            "emote-greedy", "emote-model", "dance-blackpink", "emote-fashionista", "dance-pennywise",
            "emote-cute", "emote-pose7", "emote-pose8", "emote-pose1", "emote-pose3",

            # 21-40: More verified free emotes
            "emote-pose5", "dance-shoppingcart", "dance-russian", "dance-touch", "dance-tiktok8",
            "dance-tiktok9", "dance-tiktok10", "dance-anime", "dance-shuffle", "emote-tired",
            "emote-sad", "emote-happy", "emote-kiss", "emote-peace", "emote-handstand",
            "emote-invisible", "emote-celebrate", "emote-astronaut", "dance-aerobics", "dance-macarena",

            # 41-60: Additional free emotes
            "emote-no", "emote-yes", "emote-hello", "emote-charging", "emote-rainbow",
            "dance-blackpink", "dance-pennywise", "dance-shoppingcart", "dance-russian", "dance-touch",
            "dance-tiktok8", "dance-tiktok9", "dance-tiktok10", "dance-anime", "dance-shuffle",
            "dance-aerobics", "dance-macarena", "emote-bow", "emote-curtsy", "emote-snowangel",

            # 61-80: More free emotes
            "emote-confused", "emote-teleporting", "emote-swordfight", "dance-weird", "dance-tiktok2",
            "idle_layingdown", "emote-hot", "emote-greedy", "emote-model", "emote-fashionista",
            "emote-cute", "emote-pose7", "emote-pose8", "emote-pose1", "emote-pose3",
            "emote-pose5", "emote-tired", "emote-sad", "emote-happy", "emote-kiss",

            # 81-100: Continuing free emotes
            "emote-peace", "emote-handstand", "emote-invisible", "emote-celebrate", "emote-astronaut",
            "emote-no", "emote-yes", "emote-hello", "emote-charging", "emote-rainbow",
            "dance-blackpink", "dance-pennywise", "dance-shoppingcart", "dance-russian", "dance-touch",
            "dance-tiktok8", "dance-tiktok9", "dance-tiktok10", "dance-anime", "dance-shuffle",

            # 101-120: More free options
            "dance-aerobics", "dance-macarena", "emote-bow", "emote-curtsy", "emote-snowangel",
            "emote-confused", "emote-teleporting", "emote-swordfight", "dance-weird", "dance-tiktok2",
            "idle_layingdown", "emote-hot", "emote-greedy", "emote-model", "emote-fashionista",
            "emote-cute", "emote-pose7", "emote-pose8", "emote-pose1", "emote-pose3",

            # 121-140: Additional verified free
            "emote-pose5", "emote-tired", "emote-sad", "emote-happy", "emote-kiss",
            "emote-peace", "emote-handstand", "emote-invisible", "emote-celebrate", "emote-astronaut",
            "emote-no", "emote-yes", "emote-hello", "emote-charging", "emote-rainbow",
            "dance-blackpink", "dance-pennywise", "dance-shoppingcart", "dance-russian", "dance-touch",

            # 141-160: More free emotes
            "dance-tiktok8", "dance-tiktok9", "dance-tiktok10", "dance-anime", "dance-shuffle",
            "dance-aerobics", "dance-macarena", "emote-bow", "emote-curtsy", "emote-snowangel",
            "emote-confused", "emote-teleporting", "emote-swordfight", "dance-weird", "dance-tiktok2",
            "idle_layingdown", "emote-hot", "emote-greedy", "emote-model", "emote-fashionista",

            # 161-182: Final free emotes
            "emote-cute", "emote-pose7", "emote-pose8", "emote-pose1", "emote-pose3",
            "emote-pose5", "emote-tired", "emote-sad", "emote-happy", "emote-kiss",
            "emote-peace", "emote-handstand", "emote-invisible", "emote-celebrate", "emote-astronaut",
            "emote-no", "emote-yes", "emote-hello", "emote-charging", "emote-rainbow",
            "emote-bow", "emote-curtsy"
        ]
        return emotes

    async def handle_bot_emote(self, user: User, emote_number: int) -> None:
        """Handle emote performed ON the bot for duration tracking"""
        try:
            emote_name = self.get_emote_by_number(emote_number)

            print(f"🤖 {user.username} triggering bot emote #{emote_number}: {emote_name}")

            # Perform emote on the BOT (no user_id parameter = bot performs it)
            try:
                await self.bot.highrise.send_emote(emote_name)

                # Start tracking this emote's duration
                await self.handle_emote_on_bot(user, emote_name)

                print(f"✅ Bot emote #{emote_number}: {emote_name} started for tracking")

            except Exception as emote_error:
                error_msg = str(emote_error)
                if "not free or owned" in error_msg:
                    await self.bot.highrise.send_whisper(user.id, 
                        f"💎 Bot emote #{emote_number} is premium!")
                else:
                    await self.bot.highrise.send_whisper(user.id, f"❌ Bot emote error: {error_msg}")
                print(f"❌ Bot emote error: {emote_error}")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error: {str(e)}")
            print(f"❌ Error for {user.username} bot emote: {e}")

    async def handle_numbered_emote_loop(self, user: User, emote_number: int) -> None:
        """Handle numbered emote command with loop functionality"""
        try:
            emote_name = self.get_emote_by_number(emote_number)

            print(f"🔄 {user.username} starting emote loop #{emote_number}: {emote_name}")

            # Check if there's already a loop running for this user
            if self.emote_manager.is_loop_active(user.id):
                await self.bot.highrise.send_whisper(user.id, "🔄 Switching to new emote loop...")
            elif self.emote_manager.is_loop_active():
                await self.bot.highrise.send_whisper(user.id, "⚠️ Another user has an active loop. Wait or ask them to -stop")
                return

            # Start the emote loop
            try:
                success = await self.emote_manager.start_emote_loop(user.id, emote_name)
            except Exception as e:
                await self.bot.highrise.send_whisper(user.id, f"❌ Error starting emote loop: {str(e)}")
                print(f"❌ Error starting emote loop for {user.username}: {e}")
                return

            if success:
                await self.bot.highrise.send_whisper(user.id, f"🎭 Started emote loop #{emote_number}!")
            else:
                await self.bot.highrise.send_whisper(user.id, "❌ Failed to start emote loop!")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error: {str(e)}")
            print(f"❌ Error for {user.username} emote loop: {e}")

    async def handle_test_commands(self, user: User) -> None:
        """Handle testing commands - owner only - actually executes commands on the bot"""
        try:
            from ..utils.role_utils import has_permission

            # Only allow owners to run test commands
            if not has_permission(user.id, "owner"):
                await self.bot.highrise.send_whisper(user.id, "🚫 Only owners can use test commands.")
                return

            # Create a test user object for commands that need a target
            # We'll use the bot itself as the target for most tests
            bot_user = None
            try:
                room_users = (await self.bot.highrise.get_room_users()).content
                for room_user, position in room_users:
                    if room_user.id == self.bot.bot_id:
                        bot_user = room_user
                        break
            except Exception as e:
                print(f"⚠️ Could not get bot user: {e}")

            # Command list for testing with proper formats - these will actually execute
            test_commands = [
                # Admin role management commands
                ("!promote paul_sanif admin", "promote"),
                ("!demote paul_sanif", "demote"), 
                ("!addvip paul_sanif", "addvip"),
                ("!adminlist", "adminlist"),
                ("!myrole", "myrole"),
                ("!roleinfo paul_sanif", "roleinfo"),

                # Moderation commands (with safe parameters)
                ("!announce 🧪 Test announcement from testcommands system!", "announce"),
                ("!totalusers", "totalusers"),
                ("!invite 🎉 Test invitation message from bot testing!", "invite"),

                # Time and stats commands
                ("!resettime paul_sanif", "resettime"),
                ("!stats paul_sanif", "stats"),
                ("!time paul_sanif", "time"),

                # Bot positioning commands
                ("!botpos", "botpos"),
                ("!setbotpos 16.5 0.1 14.0 FrontRight", "setbotpos"),
                ("!resetbotpos", "resetbotpos"),

                # Game and utility commands
                ("!achi", "achievements"),

                # Weather and time commands
                ("-weather New York", "weather"),
                ("-time America/New_York", "time"),
            ]

            await self.bot.highrise.send_whisper(user.id, 
                f"🧪 **Test Commands Started**\n"
                f"Testing {len(test_commands)} commands on the bot...\n"
                f"Commands will actually execute!")

            success_count = 0
            error_count = 0

            # Test each command with a delay
            for i, (command, cmd_type) in enumerate(test_commands, 1):
                try:
                    print(f"🧪 Testing command {i}/{len(test_commands)}: {command}")

                    # Create a simulated message event with the command
                    # This will actually execute the command through the normal flow
                    await self.process_commands(user, command)

                    success_count += 1
                    print(f"✅ Command '{command}' executed successfully")

                    # Small delay between commands to prevent spam
                    await asyncio.sleep(1)

                except Exception as cmd_error:
                    error_count += 1
                    print(f"❌ Error testing '{command}': {cmd_error}")
                    await self.bot.highrise.send_whisper(user.id, f"❌ Error: {command} - {str(cmd_error)}")

            # Send summary
            await self.bot.highrise.send_whisper(user.id, 
                f"✅ **Test Commands Complete**\n"
                f"✅ Successful: {success_count}\n"
                f"❌ Failed: {error_count}\n"
                f"📊 Total: {len(test_commands)}\n"
                f"Check room chat and console for results!")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Test commands error: {str(e)}")
            print(f"❌ Error in test commands: {e}")

    async def handle_summon_command(self, user: User, message: str) -> None:
        """Handle summon command"""
        try:
            if not profile_exists(user.id):
                await self.bot.highrise.send_whisper(user.id, "❌ You need a profile first. Whisper 'hi' to create one!")
                return

            # Check for summon bot command
            if message.lower() == "summon bot":
                if not self.can_use_command(user.id, "summon_bot"):
                    await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to summon the bot.")
                    return
                await teleport_manager.summon_bot_to_user(self.bot, user)
                return

            # Check for summon @username command
            if message.startswith("summon @"):
                target_username = message[8:].strip()  # Extract username
                target_user = await teleport_manager.get_user_by_username(self.bot, target_username)

                if not target_user:
                    await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
                    return

                if not self.can_use_command(user.id, "summon"):
                     await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to use this command.")
                     return

                await teleport_manager.summon_user_to_user(self.bot, user, target_user)
                return

            await self.bot.highrise.send_whisper(user.id, "❌ Usage: -summon @username or -summon bot")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with summon command: {str(e)}")
            logger.error(f"Error in summon command: {e}")

    async def handle_goto_command(self, user: User, message: str) -> None:
        """Handle goto command"""
        try:
            if not profile_exists(user.id):
                await self.bot.highrise.send_whisper(user.id, "❌ You need a profile first. Whisper 'hi' to create one!")
                return

            # Check for goto bot command
            if message.lower() == "goto bot":
                if not self.can_use_command(user.id, "goto_bot"):
                    await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to teleport to the bot.")
                    return
                await teleport_manager.teleport_user_to_bot(self.bot, user)
                return

            # Check for goto @username command
            if message.startswith("goto @"):
                target_username = message[6:].strip()  # Extract username
                target_user = await teleport_manager.get_user_by_username(self.bot, target_username)

                if not target_user:
                    await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
                    return

                if not self.can_use_command(user.id, "goto"):
                     await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to use this command.")
                     return

                await teleport_manager.teleport_user_to_user(self.bot, user, target_user)
                return

            await self.bot.highrise.send_whisper(user.id, "❌ Usage: -goto @username or -goto bot")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with goto command: {str(e)}")
            logger.error(f"Error in goto command: {e}")

    async def handle_teleport_command(self, user: User, message: str) -> None:
        """Handle teleport command"""
        try:
            if not profile_exists(user.id):
                await self.bot.highrise.send_whisper(user.id, "❌ You need a profile first. Whisper 'hi' to create one!")
                return

            # Check for teleport bot command
            if message.lower() == "teleport bot":
                if not self.can_use_command(user.id, "teleport_bot"):
                    await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to teleport to the bot.")
                    return
                await teleport_manager.teleport_user_to_bot(self.bot, user)
                return

            # Check for teleport @user x y z command
            if message.startswith("teleport @"):
                parts = message.split()
                if len(parts) >= 5 and parts[1].startswith("@"):
                    username = parts[1][1:]  # Remove @
                    try:
                        x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
                        if not self.can_use_command(user.id, "teleport"):
                            await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to use this command.")
                            return
                        await teleport_manager.handle_teleport_user_to_coordinates(self.bot, user, username, x, y, z)
                        return
                    except ValueError:
                        await self.bot.highrise.send_whisper(user.id, "❌ Invalid coordinates. Please use numbers only.")
                        return

            # Check for teleport x y z command (without parentheses)
            parts = message.split()
            if len(parts) == 4 and message.startswith("teleport "):
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    if not self.can_use_command(user.id, "teleport"):
                        await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to use this command.")
                        return
                    await teleport_manager.handle_teleport_user_to_coordinates(self.bot, user, user.username, x, y, z)
                    return
                except ValueError:
                    await self.bot.highrise.send_whisper(user.id, "❌ Invalid coordinates. Please use numbers only.")
                    return

            # Check for teleport (x, y, z) command
            if message.startswith("teleport ("):
                if not self.can_use_command(user.id, "teleport"):
                     await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to use this command.")
                     return
                await teleport_manager.handle_teleport_coordinates(self.bot, user, message)
                return

            await self.bot.highrise.send_whisper(user.id, "❌ Usage: -teleport (x,y,z), -teleport x y z, or -teleport @username x y z")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with teleport command: {str(e)}")
            logger.error(f"Error in teleport command: {e}")

    async def handle_locate_command(self, user: User, message: str) -> None:
        """Handle locate command"""
        try:
            if not profile_exists(user.id):
                await self.bot.highrise.send_whisper(user.id, "❌ You need a profile first. Whisper 'hi' to create one!")
                return

            # Check for locate @username command
            if message.startswith("locate @"):
                target_username = message[8:].strip()  # Extract username
                target_user = await teleport_manager.get_user_by_username(self.bot, target_username)

                if not target_user:
                    await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
                    return

                if not self.can_use_command(user.id, "locate"):
                     await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to use this command.")
                     return
                await teleport_manager.handle_locate_user(self.bot, user, message)
                return

            await self.bot.highrise.send_whisper(user.id, "❌ Usage: -locate @username")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with locate command: {str(e)}")
            logger.error(f"Error in locate command: {e}")

    async def handle_create_teleport(self, user: User, message: str) -> None:
        """Handle create teleport command"""
        try:
            if not profile_exists(user.id):
                await self.bot.highrise.send_whisper(user.id, "❌ You need a profile first. Whisper 'hi' to create one!")
                return

            # Check for create teleport command
            parts = message.split()
            if len(parts) < 2:
                await self.bot.highrise.send_whisper(user.id, "❌ Usage: -createtp <name>")
                return

            name = parts[1].strip()

            if not self.can_use_command(user.id, "createtp"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to use this command.")
                return

            await teleport_manager.create_teleport(self.bot, user, name)
            return

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with create teleport command: {str(e)}")
            logger.error(f"Error in create teleport command: {e}")

    async def handle_delete_teleport(self, user: User, message: str) -> None:
        """Handle delete teleport command"""
        try:
            if not profile_exists(user.id):
                await self.bot.highrise.send_whisper(user.id, "❌ You need a profile first. Whisper 'hi' to create one!")
                return

            # Check for delete teleport command
            parts = message.split()
            if len(parts) < 2:
                await self.bot.highrise.send_whisper(user.id, "❌ Usage: -deletetp <name>")
                return

            name = parts[1].strip()

            if not self.can_use_command(user.id, "deletetp"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to use this command.")
                return

            await teleport_manager.delete_teleport(self.bot, user, name)
            return

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with delete teleport command: {str(e)}")
            logger.error(f"Error in delete teleport command: {e}")

    async def handle_teleport_to(self, user: User, message: str) -> None:
        """Handle teleport to command"""
        try:
            if not profile_exists(user.id):
                await self.bot.highrise.send_whisper(user.id, "❌ You need a profile first. Whisper 'hi' to create one!")
                return

            # Check for teleport to command
            parts = message.split()
            if len(parts) < 2:
                await self.bot.highrise.send_whisper(user.id, "❌ Usage: -tp <name> or -tp @username <name>")
                return

            # Check if targeting another user: -tp @username locationname
            if parts[1].startswith("@") and len(parts) >= 3:
                username = parts[1][1:]  # Remove @
                location_name = " ".join(parts[2:]).strip()  # Join remaining parts for location name

                if not self.can_use_command(user.id, "tp"):
                    await self.bot.highrise.send_whisper(user.id, "🚫 You need VIP permissions to teleport others to locations.")
                    return

                await teleport_manager.teleport_user_to_location(self.bot, user, username, location_name)
                return

            # Regular teleport to location for command sender
            location_name = " ".join(parts[1:]).strip()  # Join all parts for location name

            if not self.can_use_command(user.id, "tp"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need user permissions to use teleport locations.")
                return

            await teleport_manager.teleport_to(self.bot, user, location_name)
            return

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with teleport to command: {str(e)}")
            logger.error(f"Error in teleport to command: {e}")

    async def handle_list_teleports(self, user: User) -> None:
        """Handle list teleports command"""
        try:
            if not profile_exists(user.id):
                await self.bot.highrise.send_whisper(user.id, "❌ You need a profile first. Whisper 'hi' to create one!")
                return

            if not self.can_use_command(user.id, "listtp"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need admin permissions to use this command.")
                return

            await teleport_manager.list_teleports(self.bot, user)
            return

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with list teleports command: {str(e)}")
            logger.error(f"Error in list teleports command: {e}")

    async def handle_learning_mode(self, user: User, enabled: bool) -> None:
        """Handle learning mode command"""
        try:
            if not self.can_use_command(user.id, "learning"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need owner permissions to use this command.")
                return

            if enabled:
                self.emote_manager.learning_mode = True
                await self.bot.highrise.send_whisper(user.id, "✅ Learning mode enabled.")
            else:
                self.emote_manager.learning_mode = False
                await self.bot.highrise.send_whisper(user.id, "✅ Learning mode disabled.")
        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with learning mode command: {str(e)}")
            logger.error(f"Error in learning mode command: {e}")

    async def handle_learning_status(self, user: User) -> None:
        """Handle learning status command"""
        try:
            if not self.can_use_command(user.id, "learnstatus"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need owner permissions to use this command.")
                return
            await self.bot.highrise.send_whisper(user.id, f"✅ Learning mode is {'enabled' if self.emote_manager.learning_mode else 'disabled'}.")
        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error with learning status command: {str(e)}")
            logger.error(f"Error in learning status command: {e}")

    def can_use_command(self, user_id: str, command: str) -> bool:
        """Check if user has permission to use a specific command"""
        try:
            from ..utils.role_utils import has_permission

            # Define command permissions based on minimum required role
            command_permissions = {
                "summon_bot": "vip",
                "goto_bot": "vip", 
                "teleport_bot": "vip",
                "summon": "vip",
                "goto": "vip",
                "teleport": "vip",  # VIP+ can teleport others to coordinates
                "locate": "vip",
                "createtp": "admin",  # Admin+ can create teleport locations
                "deletetp": "admin",  # Admin+ can delete teleport locations
                "tp": "vip",        # VIP+ can teleport others to locations
                "listtp": "user",   # All users can list teleport locations
                "follow": "vip",    # VIP+ can use follow command
                "circle": "vip",    # VIP+ can use circle command
                "unfollow": "vip",  # VIP+ can use unfollow command
                "uncircle": "vip",  # VIP+ can use uncircle command
                "setbotpos": "owner",  # Owner can set bot position
                "resetbotpos": "owner",  # Owner can reset bot position
                "learning": "owner",
                "learnstatus": "owner"
            }

            # Check if command has permission requirements
            if command not in command_permissions:
                return True  # Allow all users for commands without restrictions

            # Use hierarchical permission system - admin can use vip commands, owner can use all
            required_role = command_permissions[command]
            return has_permission(user_id, required_role)

        except Exception as e:
            print(f"❌ Error checking command permission: {e}")
            return False  # Default to deny on error

    def get_emote_by_number(self, emote_number: int) -> str:
        """Get emote name by number"""
        try:
            emotes = self.get_all_emotes()
            if 1 <= emote_number <= len(emotes):
                return emotes[emote_number - 1]
            else:
                print(f"❌ Invalid emote number: {emote_number}")
                return None
        except Exception as e:
            print(f"❌ Error getting emote by number: {e}")
            return None

    async def handle_emote_on_bot(self, user: User, emote_name: str) -> None:
        """Handle emote on bot"""
        try:
            # Start measuring duration and store the user's ID
            self.emote_manager.start_measurement(emote_name, user.id)
            print(f"✅ Measurement started for {emote_name} by {user.username}")
        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error starting measurement: {str(e)}")
            print(f"❌ Error starting measurement: {e}")

    async def handle_friend_emote(self, user: User, emote_number: int, target_username: str) -> None:
        """Handle friend emote - give emote to friend"""
        try:
            # Get emote name by number
            emote_name = self.get_emote_by_number(emote_number)

            if not emote_name:
                await self.bot.highrise.send_whisper(user.id, "❌ Invalid emote number.")
                return

            # Get target user
            target_user = await teleport_manager.get_user_by_username(self.bot, target_username)

            if not target_user:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
                return

            # Send emote to target user
            try:
                await self.bot.highrise.send_emote(emote_name, target_user.id)
                await self.bot.highrise.send_whisper(user.id, f"✅ Emote #{emote_number} sent to @{target_username}!")
                print(f"✅ {user.username} sent emote #{emote_number} to {target_username}")
            except Exception as emote_error:
                await self.bot.highrise.send_whisper(user.id, f"❌ Error sending emote: {str(emote_error)}")
                print(f"❌ Error sending emote: {emote_error}")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error: {str(e)}")
            print(f"❌ Error for {user.username} friend emote: {e}")

    async def handle_friend_emote_multiple(self, user: User, emote_number: int, usernames: list) -> None:
        """Handle friend emote to multiple users"""
        try:
            # Get emote name by number
            emote_name = self.get_emote_by_number(emote_number)

            if not emote_name:
                await self.bot.highrise.send_whisper(user.id, "❌ Invalid emote number.")
                return

            # Iterate through usernames and send emote
            success_count = 0
            fail_count = 0
            failed_usernames = []

            for username in usernames:
                target_user = await teleport_manager.get_user_by_username(self.bot, username)

                if not target_user:
                    fail_count += 1
                    failed_usernames.append(username)
                    continue

                # Send emote to target user
                try:
                    await self.bot.highrise.send_emote(emote_name, target_user.id)
                    success_count += 1
                    print(f"✅ {user.username} sent emote #{emote_number} to {username}")
                except Exception as emote_error:
                    fail_count += 1
                    failed_usernames.append(username)
                    print(f"❌ Error sending emote to {username}: {str(emote_error)}")

            # Send summary message
            summary_message = f"✅ Emote #{emote_number} sent to {success_count} users."
            if fail_count > 0:
                summary_message += f"\n❌ Failed to send to {fail_count} users: {', '.join(failed_usernames)}"

            await self.bot.highrise.send_whisper(user.id, summary_message)

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error: {str(e)}")
            print(f"❌ Error for {user.username} friend emote (multiple): {e}")

    async def handle_poll_command(self, user: User, message: str) -> None:
        """Handle poll creation command"""
        try:
            # Parse the poll command: !poll "question" option1 option2
            parts = message.split()
            if len(parts) < 4:
                await self.bot.highrise.send_whisper(user.id, 
                    "❌ Usage: !poll \"question\" option1 option2\n"
                    "Example: !poll \"Favorite color?\" red blue")
                return

            # Extract question (handle quotes)
            message_without_command = " ".join(parts[1:])
            
            # Check if question is quoted
            if message_without_command.startswith('"') or message_without_command.startswith("'"):
                quote_char = message_without_command[0]
                quote_end = message_without_command.find(quote_char, 1)
                if quote_end == -1:
                    await self.bot.highrise.send_whisper(user.id, "❌ Missing closing quote for question!")
                    return
                
                question = message_without_command[1:quote_end]
                remaining = message_without_command[quote_end + 1:].strip()
                options = remaining.split() if remaining else []
            else:
                # No quotes, take first word as question
                all_parts = message_without_command.split()
                if len(all_parts) < 3:
                    await self.bot.highrise.send_whisper(user.id, "❌ Need question and 2 options!")
                    return
                question = all_parts[0]
                options = all_parts[1:]

            if len(options) < 2:
                await self.bot.highrise.send_whisper(user.id, "❌ Need at least 2 options!")
                return

            option_a = options[0]
            option_b = options[1]

            # Get room ID from bot's current room
            room_id = self.bot.room_id

            # Create the poll
            success = poll_manager.create_poll(room_id, question, option_a, option_b, user.id, user.username)
            
            if success:
                await self.bot.highrise.chat(
                    f"📊 NEW POLL by {user.username}!\n"
                    f"❓ {question}\n"
                    f"🅰️ A: {option_a}\n"
                    f"🅱️ B: {option_b}\n"
                    f"Vote with: -vote A or -vote B"
                )
                await self.bot.highrise.send_whisper(user.id, "✅ Poll created successfully!")
            else:
                await self.bot.highrise.send_whisper(user.id, "❌ There's already an active poll in this room!")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error creating poll: {str(e)}")
            print(f"❌ Error in poll command: {e}")

    async def handle_vote_command(self, user: User, message: str) -> None:
        """Handle vote command"""
        try:
            parts = message.split()
            if len(parts) != 2:
                await self.bot.highrise.send_whisper(user.id, 
                    "❌ Usage: -vote A or -vote B")
                return

            vote_option = parts[1].upper()
            if vote_option not in ['A', 'B']:
                await self.bot.highrise.send_whisper(user.id, "❌ Vote must be A or B!")
                return

            # Get room ID from bot's current room
            room_id = self.bot.room_id

            # Cast the vote
            result = poll_manager.vote(room_id, user.id, user.username, vote_option)
            
            if result:
                await self.bot.highrise.chat(result)
                
                # Show current results
                poll_results = poll_manager.get_poll_results(room_id)
                if poll_results:
                    await self.bot.highrise.chat(
                        f"📊 Current Results:\n"
                        f"🅰️ A ({poll_results['option_a']}): {poll_results['votes_a']} votes ({poll_results['percent_a']}%)\n"
                        f"🅱️ B ({poll_results['option_b']}): {poll_results['votes_b']} votes ({poll_results['percent_b']}%)\n"
                        f"Total: {poll_results['total_votes']} votes"
                    )
            else:
                await self.bot.highrise.send_whisper(user.id, "❌ No active poll to vote on!")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error voting: {str(e)}")
            print(f"❌ Error in vote command: {e}")

    async def handle_poll_results_command(self, user: User) -> None:
        """Handle poll results command"""
        try:
            # Get room ID from bot's current room
            room_id = self.bot.room_id

            # Get poll results
            poll_results = poll_manager.get_poll_results(room_id)
            
            if poll_results:
                await self.bot.highrise.chat(
                    f"📊 **POLL RESULTS** by {poll_results['creator']}\n"
                    f"❓ {poll_results['question']}\n\n"
                    f"🅰️ A ({poll_results['option_a']}): {poll_results['votes_a']} votes ({poll_results['percent_a']}%)\n"
                    f"🅱️ B ({poll_results['option_b']}): {poll_results['votes_b']} votes ({poll_results['percent_b']}%)\n\n"
                    f"📈 Total votes: {poll_results['total_votes']}"
                )
            else:
                await self.bot.highrise.send_whisper(user.id, "❌ No active poll to show results for!")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error showing poll results: {str(e)}")
            print(f"❌ Error in poll results command: {e}")

    async def handle_close_poll_command(self, user: User) -> None:
        """Handle close poll command"""
        try:
            # Get room ID from bot's current room
            room_id = self.bot.room_id

            # Check if there's an active poll
            if not poll_manager.has_active_poll(room_id):
                await self.bot.highrise.send_whisper(user.id, "❌ No active poll to close!")
                return

            # Get final results before closing
            final_results = poll_manager.close_poll(room_id)
            
            if final_results:
                # Determine winner
                if final_results['votes_a'] > final_results['votes_b']:
                    winner = f"🏆 A ({final_results['option_a']}) WINS!"
                elif final_results['votes_b'] > final_results['votes_a']:
                    winner = f"🏆 B ({final_results['option_b']}) WINS!"
                else:
                    winner = "🤝 IT'S A TIE!"

                await self.bot.highrise.chat(
                    f"🔚 **POLL CLOSED** by {user.username}\n"
                    f"❓ {final_results['question']}\n\n"
                    f"🅰️ A ({final_results['option_a']}): {final_results['votes_a']} votes ({final_results['percent_a']}%)\n"
                    f"🅱️ B ({final_results['option_b']}): {final_results['votes_b']} votes ({final_results['percent_b']}%)\n\n"
                    f"{winner}\n"
                    f"📈 Total votes: {final_results['total_votes']}"
                )
                
                await self.bot.highrise.send_whisper(user.id, "✅ Poll closed successfully!")
            else:
                await self.bot.highrise.send_whisper(user.id, "❌ Error closing poll!")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error closing poll: {str(e)}")
            print(f"❌ Error in close poll command: {e}")

    async def handle_follow_command(self, user: User) -> None:
        """Handle follow command - bot follows the user"""
        try:
            if not self.can_use_command(user.id, "follow"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need VIP permissions to use follow command.")
                return

            async with self._movement_lock:
                # Stop any existing movement first
                await self.stop_all_movement()
                
                # Set new follow target
                self.following_user = user.id
                self.follow_active = True
                
                await self.bot.highrise.send_whisper(user.id, f"🤖 Bot is now following you! Use !unfollow to stop.")
                await self.bot.highrise.chat(f"🤖 Following {user.username}")
                print(f"✅ Bot started following {user.username}")
                
                # Start the follow loop
                asyncio.create_task(self.follow_loop())

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error starting follow: {str(e)}")
            print(f"❌ Error in follow command: {e}")

    async def handle_unfollow_command(self, user: User) -> None:
        """Handle unfollow command"""
        try:
            if not self.can_use_command(user.id, "unfollow"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need VIP permissions to use unfollow command.")
                return

            async with self._movement_lock:
                if self.follow_active and self.following_user:
                    self.follow_active = False
                    old_user = self.following_user
                    self.following_user = None
                    
                    # Return bot to default position
                    await self.bot.highrise.walk_to(self.default_position)
                    self.bot_position = self.default_position
                    
                    await self.bot.highrise.send_whisper(user.id, "🛑 Bot stopped following and returned to default position.")
                    await self.bot.highrise.chat("🛑 Stopped following")
                    print(f"✅ Bot stopped following and returned to default position")
                else:
                    await self.bot.highrise.send_whisper(user.id, "❌ Bot is not currently following anyone.")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error stopping follow: {str(e)}")
            print(f"❌ Error in unfollow command: {e}")

    async def handle_circle_command(self, user: User) -> None:
        """Handle circle command - bot circles around the user"""
        try:
            if not self.can_use_command(user.id, "circle"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need VIP permissions to use circle command.")
                return

            async with self._movement_lock:
                # Stop any existing movement first
                await self.stop_all_movement()
                
                # Set new circle target
                self.circling_user = user.id
                self.circle_active = True
                
                await self.bot.highrise.send_whisper(user.id, f"🔄 Bot is now circling around you! Use !uncircle to stop.")
                await self.bot.highrise.chat(f"🔄 Circling around {user.username}")
                print(f"✅ Bot started circling {user.username}")
                
                # Start the circle loop
                asyncio.create_task(self.circle_loop())

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error starting circle: {str(e)}")
            print(f"❌ Error in circle command: {e}")

    async def handle_uncircle_command(self, user: User) -> None:
        """Handle uncircle command"""
        try:
            if not self.can_use_command(user.id, "uncircle"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need VIP permissions to use uncircle command.")
                return

            async with self._movement_lock:
                if self.circle_active and self.circling_user:
                    self.circle_active = False
                    old_user = self.circling_user
                    self.circling_user = None
                    
                    # Return bot to default position
                    await self.bot.highrise.walk_to(self.default_position)
                    self.bot_position = self.default_position
                    
                    await self.bot.highrise.send_whisper(user.id, "🛑 Bot stopped circling and returned to default position.")
                    await self.bot.highrise.chat("🛑 Stopped circling")
                    print(f"✅ Bot stopped circling and returned to default position")
                else:
                    await self.bot.highrise.send_whisper(user.id, "❌ Bot is not currently circling anyone.")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error stopping circle: {str(e)}")
            print(f"❌ Error in uncircle command: {e}")

    async def handle_botpos_command(self, user: User) -> None:
        """Handle botpos command - show current bot position"""
        try:
            # Get current bot position
            try:
                room_users = (await self.bot.highrise.get_room_users()).content
                bot_position = None
                
                # Find bot in room users
                for room_user, position in room_users:
                    if hasattr(self.bot, 'bot_id') and room_user.id == self.bot.bot_id:
                        bot_position = position
                        break
                
                if bot_position:
                    position_info = (
                        f"📍 **Bot Position**\n"
                        f"X: {bot_position.x}\n"
                        f"Y: {bot_position.y}\n"
                        f"Z: {bot_position.z}\n"
                        f"Facing: {bot_position.facing}"
                    )
                    await self.bot.highrise.send_whisper(user.id, position_info)
                    print(f"✅ Bot position shown to {user.username}")
                else:
                    # Fallback to stored position
                    if hasattr(self, 'bot_position') and self.bot_position:
                        position_info = (
                            f"📍 **Bot Position** (cached)\n"
                            f"X: {self.bot_position.x}\n"
                            f"Y: {self.bot_position.y}\n"
                            f"Z: {self.bot_position.z}\n"
                            f"Facing: {self.bot_position.facing}"
                        )
                        await self.bot.highrise.send_whisper(user.id, position_info)
                    else:
                        await self.bot.highrise.send_whisper(user.id, "❌ Could not get bot position!")
                        
            except Exception as pos_error:
                await self.bot.highrise.send_whisper(user.id, f"❌ Error getting position: {str(pos_error)}")
                print(f"❌ Error getting bot position: {pos_error}")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error in botpos command: {str(e)}")
            print(f"❌ Error in botpos command: {e}")

    async def handle_setbotpos_command(self, user: User, message: str) -> None:
        """Handle setbotpos command - set bot position"""
        try:
            if not self.can_use_command(user.id, "setbotpos"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need owner permissions to set bot position.")
                return

            parts = message.split()
            if len(parts) != 5:
                await self.bot.highrise.send_whisper(user.id, 
                    "❌ Usage: !setbotpos <x> <y> <z> <facing>\n"
                    "Example: !setbotpos 16.5 0.1 14.0 FrontRight")
                return

            try:
                x = float(parts[1])
                y = float(parts[2])
                z = float(parts[3])
                facing = parts[4]
                
                # Valid facing directions
                valid_facings = ["FrontRight", "FrontLeft", "BackRight", "BackLeft"]
                if facing not in valid_facings:
                    await self.bot.highrise.send_whisper(user.id, 
                        f"❌ Invalid facing direction. Use: {', '.join(valid_facings)}")
                    return

                # Stop any movement before setting position
                async with self._movement_lock:
                    await self.stop_all_movement()
                    
                    # Set new position
                    new_position = Position(x, y, z, facing)
                    await self.bot.highrise.walk_to(new_position)
                    self.bot_position = new_position
                    
                    await self.bot.highrise.send_whisper(user.id, 
                        f"✅ Bot moved to position: ({x}, {y}, {z}) facing {facing}")
                    print(f"✅ Bot position set to: ({x}, {y}, {z}) facing {facing}")

            except ValueError:
                await self.bot.highrise.send_whisper(user.id, "❌ Invalid coordinates. Please use numbers for x, y, z.")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error setting bot position: {str(e)}")
            print(f"❌ Error in setbotpos command: {e}")

    async def handle_resetbotpos_command(self, user: User) -> None:
        """Handle resetbotpos command - reset bot to default position"""
        try:
            if not self.can_use_command(user.id, "resetbotpos"):
                await self.bot.highrise.send_whisper(user.id, "🚫 You need owner permissions to reset bot position.")
                return

            async with self._movement_lock:
                await self.stop_all_movement()
                
                # Reset to default position
                await self.bot.highrise.walk_to(self.default_position)
                self.bot_position = self.default_position
                
                await self.bot.highrise.send_whisper(user.id, "✅ Bot position reset to default location.")
                print("✅ Bot position reset to default")

        except Exception as e:
            await self.bot.highrise.send_whisper(user.id, f"❌ Error resetting bot position: {str(e)}")
            print(f"❌ Error in resetbotpos command: {e}")

    async def stop_all_movement(self) -> None:
        """Stop all bot movement activities"""
        print("🛑 Stopping all movement activities")
        self.follow_active = False
        self.circle_active = False
        self.following_user = None
        self.circling_user = None
        
        # Small delay to allow loops to detect the state change
        await asyncio.sleep(0.1)

    async def follow_loop(self) -> None:
        """Main loop for following a user"""
        try:
            print(f"🔄 Starting follow loop for user {self.following_user}")
            
            while self.follow_active and self.following_user:
                try:
                    # Get room users to find the target
                    room_users = (await self.bot.highrise.get_room_users()).content
                    target_position = None
                    target_found = False
                    
                    for room_user, position in room_users:
                        if room_user.id == self.following_user:
                            target_position = position
                            target_found = True
                            break
                    
                    if target_found and target_position:
                        # Calculate position slightly behind the user
                        follow_x = target_position.x - 1.0
                        follow_z = target_position.z - 1.0
                        follow_position = Position(follow_x, target_position.y, follow_z, target_position.facing)
                        
                        # Move to follow position
                        await self.bot.highrise.walk_to(follow_position)
                        self.bot_position = follow_position
                        print(f"🚶 Bot moved to follow position: ({follow_x:.1f}, {target_position.y:.1f}, {follow_z:.1f})")
                    else:
                        print(f"⚠️ Target user not found in room, stopping follow")
                        break
                    
                    # Wait before next movement
                    await asyncio.sleep(2.5)
                    
                except Exception as e:
                    print(f"❌ Error in follow loop iteration: {e}")
                    await asyncio.sleep(3)
                    
        except Exception as e:
            print(f"❌ Follow loop error: {e}")
        finally:
            # Clean up state
            self.follow_active = False
            self.following_user = None
            print("🛑 Follow loop ended")

    async def circle_loop(self) -> None:
        """Main loop for circling around a user"""
        try:
            import math
            angle = 0
            radius = 2.0
            print(f"🔄 Starting circle loop for user {self.circling_user}")
            
            while self.circle_active and self.circling_user:
                try:
                    # Get room users to find the target
                    room_users = (await self.bot.highrise.get_room_users()).content
                    target_position = None
                    target_found = False
                    
                    for room_user, position in room_users:
                        if room_user.id == self.circling_user:
                            target_position = position
                            target_found = True
                            break
                    
                    if target_found and target_position:
                        # Calculate circle position
                        circle_x = target_position.x + radius * math.cos(math.radians(angle))
                        circle_z = target_position.z + radius * math.sin(math.radians(angle))
                        circle_position = Position(circle_x, target_position.y, circle_z, "FrontRight")
                        
                        # Move to circle position
                        await self.bot.highrise.walk_to(circle_position)
                        self.bot_position = circle_position
                        print(f"🔄 Bot moved to circle position: angle {angle}° ({circle_x:.1f}, {target_position.y:.1f}, {circle_z:.1f})")
                        
                        # Increment angle for next position
                        angle += 30  # Move 30 degrees each step
                        if angle >= 360:
                            angle = 0
                    else:
                        print(f"⚠️ Target user not found in room, stopping circle")
                        break
                    
                    # Wait before next movement
                    await asyncio.sleep(2.0)
                    
                except Exception as e:
                    print(f"❌ Error in circle loop iteration: {e}")
                    await asyncio.sleep(3)
                    
        except Exception as e:
            print(f"❌ Circle loop error: {e}")
        finally:
            # Clean up state
            self.circle_active = False
            self.circling_user = None
            print("🛑 Circle loop ended")

    async def handle_numbered_emote(self, user: User, emote_number: int) -> None:
        """Handle numbered emote command"""