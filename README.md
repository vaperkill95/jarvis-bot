# 🤖 Jarvis - All-in-One Discord Bot

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Discord.py](https://img.shields.io/badge/discord.py-2.3+-blue.svg)](https://github.com/Rapptz/discord.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Commands](https://img.shields.io/badge/commands-87+-green.svg)](#)

The ultimate all-in-one Discord bot with **87+ commands** featuring competitive queue management, MMR tracking, stream notifications, music playback, welcome messages, role management, and more!

![Jarvis Bot](jarvis-logo.jpg)

## ✨ Features

### 🎮 Queue Management System
- **Multiple queue modes**: Balanced (MMR-based), Random, Captain Draft, Unfair (challenge mode)
- **Interactive buttons**: Join/Leave queue with one click
- **Team size flexibility**: 1v1 up to 20v20
- **Queue locking**: Control when players can join
- **Auto-fill detection**: Matches start automatically when full
- **Sticky queue messages**: Pin queue interface to channel
- **Custom team names**: Set custom names for Team 1 and Team 2

### 📊 Complete MMR & Ranking System
- **Automatic MMR calculation**: +25 for wins, -25 for losses
- **Manual MMR adjustment**: Staff can modify player ratings
- **MMR decay**: Inactive players lose rating over time
- **Grace periods**: Exempt players from decay temporarily
- **Auto-role assignment**: Roles automatically assigned based on MMR ranges
- **5 default ranks**: Bronze, Silver, Gold, Platinum, Diamond (fully customizable)
- **Leaderboard tracking**: View top players by MMR
- **Player comparisons**: Side-by-side stat comparison

### 🏆 Advanced Match Management
- **Full match history**: Track all games with detailed information
- **Match viewing**: See team rosters, scores, maps played
- **Result reporting**: Simple commands to report winners
- **Result modification**: Fix mistakes in past match results
- **Match cancellation**: Cancel matches without affecting stats
- **Player match history**: View recent games for any player
- **Win streaks**: Track current and longest winning streaks
- **Game mode rotation**: HP, SND, or MIX mode (HP→SND→Overload)
- **Map voting**: Let players vote on maps before match

### 🛡️ Teams/Clans System
- **Create teams**: Players can form persistent teams
- **Team invitations**: Invite and manage team members
- **Team statistics**: Track team performance and records
- **Team vs Team**: Clans can queue together for team matches
- **Team management**: Leave, disband, and view team stats

### 📺 Stream Notifications (SXLive Style)
- **Multi-platform support**: Twitch, Kick, YouTube, TikTok
- **Real-time go-live alerts**: Instant notifications when streamers go live
- **Custom messages**: Personalize notification templates
- **Live role assignment**: Auto-assign roles when streamers are live
- **Ping roles**: Mention specific roles on go-live
- **API integration**: Twitch Helix API and YouTube Data API v3
- **No API required**: Kick and TikTok work without API keys
- **Rich embeds**: Game, title, viewer count, thumbnails

### 🎵 Full-Featured Music Player
- **YouTube playback**: Play music from YouTube
- **Queue management**: Add multiple songs to queue
- **Playback controls**: Play, pause, resume, skip, stop
- **Volume control**: Adjust volume (0-100)
- **Loop mode**: Repeat current song
- **Now playing**: See what's currently playing
- **View queue**: See upcoming songs

### 👋 Welcome & Farewell System
- **Custom welcome messages**: Greet new members with style
- **Farewell messages**: Say goodbye to leaving members
- **DM greet**: Send private welcome messages
- **Variable support**: Use {user}, {server}, {count} placeholders
- **Embed customization**: Set titles, descriptions, colors, images
- **Welcome channel**: Dedicated channel for greetings

### 🎭 Advanced Role Management
- **Verification system**: One-click verification panels
- **Role panels**: Create interactive role selection menus
- **Reaction roles**: Assign roles via emoji reactions
- **Role limits per match**: Limit specific roles in queue (e.g., max 2 tanks)
- **Required roles**: Set roles required to join queue
- **Staff roles**: Grant queue admin permissions

### 📋 Server Logging
- **Member events**: Track joins, leaves, nickname changes
- **Message events**: Log edits and deletions
- **Role events**: Track role assignments and removals
- **Channel events**: Monitor channel creation and deletion
- **Voice events**: Track voice channel joins/leaves
- **Ban/Kick tracking**: Log moderation actions
- **Dedicated log channel**: All events in one place

### 🤖 Advanced Automation
- **Auto-create voice channels**: Team channels created automatically for matches
- **Auto-move players**: Players moved to team channels when match starts
- **Results announcements**: Automatic match results posted to dedicated channel
- **Lobby details**: Custom templates with variables (host, password, match number)
- **Channel categories**: Organize team channels in categories
- **Ping players**: Mention players in match announcements

### 🛡️ Admin & Moderation Tools
- **User management**: Add/remove players manually
- **Blacklist system**: Ban toxic players from queues
- **Command logging**: Track all admin command usage
- **Activity logging**: Monitor queue join/leave activity
- **Stats reset**: Reset individual or all player stats
- **Map pool management**: Add/remove maps for voting
- **Message purge**: Bulk delete messages
- **Staff permissions**: Multi-role admin system

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- FFmpeg (for music features)
- Discord Bot Token

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/vaperkill95/jarvis-bot.git
cd jarvis-bot
```

2. **Install dependencies**
```bash
pip install discord.py yt-dlp aiohttp
```

3. **Configure the bot**
```bash
# Create .env file
echo "DISCORD_BOT_TOKEN=your_bot_token_here" > .env
```

4. **Run the bot**
```bash
python jarvis.py
```

5. **Sync commands in Discord**
```
/sync
```

## 📋 Command Categories

**Total Commands: 87+**

### 🎮 Queue Management (11)
- `/setup` - Create a new queue (Interactive Setup)
- `/startqueue` - Display queue interface
- `/clearqueue` - Clear all players from queue
- `/lockqueue` / `/unlockqueue` - Lock/unlock queue
- `/adduser` / `/removeuser` - Manually add/remove players
- `/purge` - Clear channel messages

### ⚙️ Configuration (16)
- `/setteamsize` - Set players per team (1-20)
- `/setteammode` - Set team selection (balanced/random/captains/unfair)
- `/setcaptainmode` - Set captain selection method
- `/setteamnames` - Set custom team names
- `/setmapvoting` - Enable/disable map voting
- `/addmap` / `/removemap` - Manage map pool
- `/setgamemode` - Set HP/SND/MIX rotation
- `/rolelimit` - Limit roles per match
- `/resultschannel` - Set results channel
- `/automove` - Toggle auto-move to voice
- `/createchannels` - Auto-create team channels
- `/channelcategory` - Set channel category
- `/pingplayers` - Toggle player pings
- `/nametype` - Set name display type
- `/stickymessage` - Toggle sticky queue message

### 🏆 Match System (9)
- `/reportwin` - Report match winner
- `/cancelmatch` - Cancel current match
- `/matchhistory` - View recent match history
- `/viewmatch` - View detailed match info
- `/modifyresult` - Change past match results
- `/recentmatches` - Player's recent games
- `/winstreak` - View win streaks

### 📊 Statistics & MMR (11)
- `/stats` - Player statistics
- `/leaderboard` - Top players by MMR
- `/rank` - Player's rank position
- `/compare` - Compare two players
- `/setmmr` - Set player MMR
- `/adjustmmr` - Add/subtract MMR
- `/resetstats` - Reset all stats
- `/resetuser` - Reset player stats
- `/mmrdecay` - Toggle MMR decay
- `/graceperiod` - Grant decay grace period

### 🛡️ Ranks & Auto-Roles (3)
- `/ranks` - List configured ranks
- `/rankadd` - Add MMR rank with auto-role
- `/rankremove` - Remove rank

### 🛡️ Teams/Clans (6)
- `/teamcreate` - Create a team
- `/teaminvite` - Invite to team
- `/teamjoin` - Join a team
- `/teamleave` - Leave team
- `/teamdisband` - Disband team
- `/teamstats` - View team stats

### 🎵 Music Player (11)
- `/join` / `/leave` - Voice channel control
- `/play` - Play a song from YouTube
- `/skip` / `/pause` / `/resume` / `/stop` - Playback controls
- `/nowplaying` - Current song
- `/musicqueue` - View queue
- `/volume` - Set volume (0-100)
- `/loop` - Toggle loop mode

### 📺 Stream Notifications (2)
- `/stream` - Manage streamers (add/remove/list/setchannel/liverole/pingrole/setmessage/test)
- `/streamkey` - Set Twitch/YouTube API keys

### 🎭 Role Management (7)
- `/verify` - Set up verification button
- `/rolepanel` - Create role selection panel
- `/rolepaneladd` - Add role to panel
- `/rolepanelremove` - Remove role from panel
- `/rolepaneldelete` - Delete role panel
- `/rolepanellist` - List all panels
- `/reactionrole` - Manage emoji reaction roles

### 👋 Welcome System (5)
- `/welcomer` - Configure welcome messages
- `/welcomer_channel` - Set welcome channel
- `/welcomer_test` - Preview welcome message
- `/greet` - Configure DM greet messages
- `/farewell` - Configure leave messages

### 📋 Logging (1)
- `/logchannel` - Configure server event logging

### 👥 Admin Tools (5)
- `/requiredrole` - Manage required roles for queue
- `/blacklist` - Ban/unban users from queue
- `/staffroles` - Manage staff permissions
- `/lobbydetails` - Manage lobby details template
- `/lobbydetailsset` - Set lobby details template
- `/commandlog` - View command usage
- `/activitylog` - View queue activity

### 🔧 Utility (3)
- `/help` - Show all commands
- `/ping` - Check bot latency
- `/sync` - Sync slash commands

## 🎮 Usage Examples

### Setting Up a 5v5 Ranked Queue

```bash
# Create the queue
/setup ranked 5

# Configure team mode
/setteammode balanced ranked

# Enable map voting
/setmapvoting true ranked
/addmap de_dust2 ranked
/addmap de_mirage ranked
/addmap de_inferno ranked

# Set game mode rotation
/setgamemode MIX ranked

# Set results channel
/resultschannel set #match-results ranked

# Display queue interface
/startqueue ranked
```

### Configuring Auto-Ranks

```bash
# Set up MMR-based rank roles
/rankadd Bronze 0 999 @Bronze ranked
/rankadd Silver 1000 1499 @Silver ranked
/rankadd Gold 1500 1999 @Gold ranked
/rankadd Platinum 2000 2499 @Platinum ranked
/rankadd Diamond 2500 9999 @Diamond ranked
```

Players automatically get Discord roles based on their MMR!

### Setting Up Stream Notifications

```bash
# Set API keys (Twitch/YouTube)
/streamkey set twitch YOUR_CLIENT_ID YOUR_SECRET
/streamkey set youtube YOUR_API_KEY

# Set notification channel
/stream setchannel #streams

# Add streamers to track
/stream add twitch shroud
/stream add kick trainwreckstv
/stream add youtube @PewDiePie
/stream add tiktok bellapoarch

# Set role to ping when live
/stream pingrole @StreamAlert

# Auto-assign role when live
/stream liverole @Live

# Custom notification message
/stream setmessage {streamer} is now live! 🔴 {title}

# Test notification
/stream test twitch shroud
```

### Creating a Welcome System

```bash
# Configure welcome message
/welcomer enable
/welcomer title Welcome to {server}!
/welcomer description Hey {user}! You're member #{count}
/welcomer color #5865F2
/welcomer image https://your-banner-url.png

# Set welcome channel
/welcomer_channel #welcome

# Test it
/welcomer_test

# Enable DM greet
/greet enable
/greet message Welcome to {server}, {user}! Check out #rules to get started.
```

### Setting Up Role Panels

```bash
# Create a verification panel
/verify #verify-here @Verified

# Create a role selection panel
/rolepanel #roles "Choose Your Roles"

# Add roles to the panel
/rolepaneladd #roles @Notifications "Get notified for events"
/rolepaneladd #roles @Gaming "Join gaming sessions"
/rolepaneladd #roles @Announcements "Server updates"
```

## 🗄️ Database Schema

Jarvis uses SQLite with 27 tables:

- **players** - Global player statistics
- **queue_stats** - Per-queue player statistics  
- **matches** - Complete match history
- **queue_settings** - Queue configurations
- **teams** / **team_members** - Team/clan system
- **ranks** - MMR rank definitions with auto-roles
- **blacklist** - Banned users
- **maps** - Map pools for voting
- **staff_roles** / **required_roles** / **role_limits** - Permission system
- **command_logs** / **activity_logs** - Logging system
- **stream_settings** / **tracked_streamers** - Stream notification system
- **welcomer_settings** / **farewell_settings** / **greet_settings** - Welcome system
- **log_settings** - Server logging configuration
- **reaction_role_panels** / **reaction_roles** - Role panel system
- **emoji_reaction_messages** / **emoji_reaction_pairs** - Emoji reaction roles
- **predictions** / **user_currency** - Future prediction/economy features
- **scheduled_tasks** - Scheduled automation tasks

Database is created automatically on first run.

## 🔧 Configuration

All settings are configured via slash commands in Discord - no manual file editing required!

```bash
# Team settings
/setteamsize 5 ranked          # 5v5 matches
/setteammode balanced ranked   # MMR-balanced teams

# Automation
/createchannels true ranked    # Auto-create voice channels
/automove true ranked          # Auto-move players
/pingplayers true ranked       # Mention players in announcements

# Permissions
/requiredrole add @Verified ranked  # Require role to join
/staffroles add @Moderator          # Grant admin permissions
/rolelimit add @Tank 2 ranked       # Max 2 tanks per match
```

## 🌐 Web Dashboard

Visit the official Jarvis Bot website:
**https://vaperkill95.github.io**

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [discord.py](https://github.com/Rapptz/discord.py)
- Music playback powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- Inspired by competitive gaming communities
- Stream notifications inspired by SXLive

## 📞 Support

- 🌐 **Website**: [https://vaperkill95.github.io](https://vaperkill95.github.io)
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/vaperkill95/jarvis-bot/issues)
- 💬 **Discord Support**: [Join our server](https://discord.gg/your-invite)
- 📊 **Vote on Top.gg**: Coming soon!

## 📊 Stats

- **Lines of Code**: 7,883+
- **Commands**: 87+
- **Database Tables**: 27
- **Features**: Queue management, MMR tracking, stream notifications, music player, welcome system, role management, logging, and more!

## 🚀 Invite Jarvis to Your Server

[**Add to Discord**](https://discord.com/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot%20applications.commands)

---

**Made with ❤️ by vaper**

⭐ Star this repository if you find it useful!
