import os
print("="*50)
print("ENVIRONMENT VARIABLES:")
for key, value in os.environ.items():
    if 'TOKEN' in key or 'DISCORD' in key:
        print(f"{key} = {value[:20]}...")
print("="*50)

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import random
import asyncio
import yt_dlp
import logging
import os
import json
import string
from datetime import datetime, timedelta
from collections import deque
from typing import Optional, List, Dict, Tuple
from logging.handlers import RotatingFileHandler
from io import BytesIO
import aiohttp
from PIL import Image, ImageDraw, ImageFont
# Manual .env loader (avoids python-dotenv encoding issues on Windows)
def load_env_file():
    """Load .env file manually to avoid encoding issues"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, 'r', encoding='utf-8-sig', newline='') as f:
            for line in f:
                # Remove ALL whitespace including \r\n
                line = line.replace('\r', '').replace('\n', '').strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                # Clean key and value of any remaining whitespace or special chars
                key = key.strip().replace('\r', '').replace('\n', '')
                value = value.strip().replace('\r', '').replace('\n', '')
                if key and not any(ord(c) < 32 for c in key):  # Ensure no control chars
                    os.environ[key] = value
                    print(f"âœ“ Loaded environment variable: {key}")
    except Exception as e:
        print(f"Warning: Could not read .env file: {e}")

# ============================================================================
# CONFIGURATION & SETUP
# ============================================================================

load_env_file()
print(f"TOKEN AFTER LOAD: {os.environ.get('DISCORD_BOT_TOKEN', 'NOT FOUND')}")

# Logging Configuration
def setup_logging():
    """Configure logging with file rotation and console output"""
    os.makedirs('logs', exist_ok=True)
    
    logger = logging.getLogger('jarvisqueue')
    logger.setLevel(logging.DEBUG)
    
    file_handler = RotatingFileHandler(
        'logs/jarvisqueue.log',
        maxBytes=10*1024*1024,
        backupCount=10,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] [%(levelname)-8s] %(message)s',
        datefmt='%H:%M:%S'
    ))
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.INFO)
    discord_logger.addHandler(file_handler)
    
    logger.info("=" * 70)
    logger.info("JARVISQUEUE - FULL FEATURE SET - STARTING")
    logger.info("=" * 70)
    
    return logger

logger = setup_logging()

# Bot Configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.reactions = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Database Configuration
DB_FILE = 'jarvisqueue_full.db'

# Music Configuration
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extract_flat': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# ============================================================================
# DATA CLASSES
# ============================================================================

class MusicQueue:
    """Manages music playback queue for a guild"""
    
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.loop = False
        self.volume = 0.5
    
    def add(self, song: Dict):
        self.queue.append(song)
    
    def next(self) -> Optional[Dict]:
        if self.loop and self.current:
            return self.current
        if self.queue:
            self.current = self.queue.popleft()
            return self.current
        self.current = None
        return None
    
    def clear(self):
        self.queue.clear()
        self.current = None
    
    def is_empty(self) -> bool:
        return len(self.queue) == 0

# ============================================================================
# GLOBAL STATE
# ============================================================================

# Queue System
guild_queues = {}  # {guild_id: {queue_name: [player_ids]}}
active_matches = {}  # {guild_id: {queue_name: match_data}}
captain_drafts = {}  # {guild_id: {queue_name: draft_data}}
active_match_channels = {}  # {guild_id: {queue_name: {'text': channel_id, 'voice1': channel_id, 'voice2': channel_id}}}
match_votes = {}  # {match_id: {'team1': set(), 'team2': set()}}

# Sticky Queue Messages - tracks queue messages that should stay at bottom
# {channel_id: {'message': message_object, 'view': QueueView_object, 'queue_name': str, 'guild_id': int}}
sticky_queue_messages = {}

# Music System
music_queues = {}  # {guild_id: MusicQueue}
now_playing = {}  # {guild_id: song_info}

# Blacklists
blacklisted_users = {}  # {guild_id: {queue_name: [user_ids]}}

# Scheduled tasks
scheduled_commands = {}  # {guild_id: [scheduled_task_data]}

# ============================================================================
# DATABASE MANAGEMENT
# ============================================================================

def init_db():
    """Initialize all database tables"""
    logger.info(f"Initializing database: {DB_FILE}")
    
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Players table
        c.execute('''CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            mmr INTEGER DEFAULT 1000,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            last_played TEXT,
            total_games INTEGER DEFAULT 0,
            win_streak INTEGER DEFAULT 0,
            highest_mmr INTEGER DEFAULT 1000,
            join_date TEXT,
            grace_period_until TEXT
        )''')
        
        # Matches table - expanded
        c.execute('''CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            queue_name TEXT,
            timestamp TEXT,
            team1 TEXT,
            team2 TEXT,
            winner INTEGER,
            cancelled INTEGER DEFAULT 0,
            mmr_change INTEGER,
            match_number INTEGER,
            team1_score INTEGER DEFAULT 0,
            team2_score INTEGER DEFAULT 0,
            map_played TEXT,
            lobby_details TEXT
        )''')
        
        # Queue settings table - expanded
        c.execute('''CREATE TABLE IF NOT EXISTS queue_settings (
            guild_id INTEGER,
            queue_name TEXT,
            team_size INTEGER DEFAULT 5,
            team_selection_mode TEXT DEFAULT 'balanced',
            captain_mode TEXT DEFAULT 'random',
            required_role INTEGER,
            locked INTEGER DEFAULT 0,
            results_channel INTEGER,
            auto_move INTEGER DEFAULT 0,
            create_channels INTEGER DEFAULT 0,
            channel_category INTEGER,
            map_voting INTEGER DEFAULT 0,
            ping_players INTEGER DEFAULT 1,
            sticky_message INTEGER DEFAULT 0,
            name_type TEXT DEFAULT 'discord',
            mmr_decay_enabled INTEGER DEFAULT 0,
            lobby_details_template TEXT,
            team1_name TEXT DEFAULT 'Team 1',
            team2_name TEXT DEFAULT 'Team 2',
            game_mode TEXT DEFAULT 'mix',
            PRIMARY KEY (guild_id, queue_name)
        )''')
        
        # Migrate queue_settings: add any missing columns from schema updates
        c.execute("PRAGMA table_info(queue_settings)")
        existing_columns = {row[1] for row in c.fetchall()}
        migration_columns = [
            ("create_channels", "INTEGER DEFAULT 0"),
            ("channel_category", "INTEGER"),
            ("map_voting", "INTEGER DEFAULT 0"),
            ("ping_players", "INTEGER DEFAULT 1"),
            ("sticky_message", "INTEGER DEFAULT 0"),
            ("name_type", "TEXT DEFAULT 'discord'"),
            ("mmr_decay_enabled", "INTEGER DEFAULT 0"),
            ("lobby_details_template", "TEXT"),
            ("team1_name", "TEXT DEFAULT 'Team 1'"),
            ("team2_name", "TEXT DEFAULT 'Team 2'"),
            ("game_mode", "TEXT DEFAULT 'mix'"),
        ]
        for col_name, col_type in migration_columns:
            if col_name not in existing_columns:
                c.execute(f"ALTER TABLE queue_settings ADD COLUMN {col_name} {col_type}")
        
        # Player stats per queue
        c.execute('''CREATE TABLE IF NOT EXISTS queue_stats (
            user_id INTEGER,
            guild_id INTEGER,
            queue_name TEXT,
            mmr INTEGER DEFAULT 1000,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            last_played TEXT,
            PRIMARY KEY (user_id, guild_id, queue_name)
        )''')
        
        # Staff roles
        c.execute('''CREATE TABLE IF NOT EXISTS staff_roles (
            guild_id INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, role_id)
        )''')
        
        # Blacklist
        c.execute('''CREATE TABLE IF NOT EXISTS blacklist (
            guild_id INTEGER,
            queue_name TEXT,
            user_id INTEGER,
            reason TEXT,
            blacklisted_at TEXT,
            blacklisted_by INTEGER,
            PRIMARY KEY (guild_id, queue_name, user_id)
        )''')
        
        # Maps
        c.execute('''CREATE TABLE IF NOT EXISTS maps (
            guild_id INTEGER,
            queue_name TEXT,
            map_name TEXT,
            game_mode TEXT DEFAULT 'all',
            PRIMARY KEY (guild_id, queue_name, map_name, game_mode)
        )''')
        
        # Migrate maps table: add game_mode if missing
        c.execute("PRAGMA table_info(maps)")
        map_columns = {row[1] for row in c.fetchall()}
        if 'game_mode' not in map_columns:
            c.execute("ALTER TABLE maps ADD COLUMN game_mode TEXT DEFAULT 'all'")
        
        # Teams/Clans
        c.execute('''CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            team_name TEXT,
            owner_id INTEGER,
            created_at TEXT,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            UNIQUE(guild_id, team_name)
        )''')
        
        # Team members
        c.execute('''CREATE TABLE IF NOT EXISTS team_members (
            team_id INTEGER,
            user_id INTEGER,
            joined_at TEXT,
            PRIMARY KEY (team_id, user_id),
            FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE
        )''')
        
        # Ranks/Auto-roles
        c.execute('''CREATE TABLE IF NOT EXISTS ranks (
            guild_id INTEGER,
            queue_name TEXT,
            rank_name TEXT,
            min_mmr INTEGER,
            max_mmr INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, queue_name, rank_name)
        )''')
        
        # Role limits
        c.execute('''CREATE TABLE IF NOT EXISTS role_limits (
            guild_id INTEGER,
            queue_name TEXT,
            role_id INTEGER,
            max_count INTEGER,
            PRIMARY KEY (guild_id, queue_name, role_id)
        )''')
        
        # Required roles (multiple allowed)
        c.execute('''CREATE TABLE IF NOT EXISTS required_roles (
            guild_id INTEGER,
            queue_name TEXT,
            role_id INTEGER,
            PRIMARY KEY (guild_id, queue_name, role_id)
        )''')
        
        # Scheduled commands
        c.execute('''CREATE TABLE IF NOT EXISTS scheduled_tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            command_name TEXT,
            command_args TEXT,
            schedule_times TEXT,
            created_by INTEGER,
            created_at TEXT
        )''')
        
        # Command logs
        c.execute('''CREATE TABLE IF NOT EXISTS command_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            command_name TEXT,
            timestamp TEXT,
            success INTEGER
        )''')
        
        # Activity logs
        c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            queue_name TEXT,
            user_id INTEGER,
            action TEXT,
            timestamp TEXT
        )''')
        
        # Predictions/Betting
        c.execute('''CREATE TABLE IF NOT EXISTS predictions (
            prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            match_id INTEGER,
            user_id INTEGER,
            predicted_winner INTEGER,
            bet_amount INTEGER,
            timestamp TEXT,
            FOREIGN KEY (match_id) REFERENCES matches(match_id)
        )''')
        
        # User currency for betting
        c.execute('''CREATE TABLE IF NOT EXISTS user_currency (
            guild_id INTEGER,
            user_id INTEGER,
            balance INTEGER DEFAULT 1000,
            PRIMARY KEY (guild_id, user_id)
        )''')
        
        # Reaction roles (Button-based panels - existing)
        c.execute('''CREATE TABLE IF NOT EXISTS reaction_role_panels (
            panel_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            message_id INTEGER UNIQUE,
            title TEXT,
            description TEXT,
            created_by INTEGER,
            created_at TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS reaction_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_id INTEGER,
            guild_id INTEGER,
            role_id INTEGER,
            emoji TEXT,
            label TEXT,
            FOREIGN KEY (panel_id) REFERENCES reaction_role_panels(panel_id) ON DELETE CASCADE,
            UNIQUE(panel_id, role_id)
        )''')
        
        # Emoji Reaction Roles (Carl-bot style - NEW)
        c.execute('''CREATE TABLE IF NOT EXISTS emoji_reaction_messages (
            message_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            title TEXT,
            description TEXT,
            mode TEXT DEFAULT 'normal',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS emoji_reaction_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            FOREIGN KEY (message_id) REFERENCES emoji_reaction_messages (message_id) ON DELETE CASCADE,
            UNIQUE(message_id, emoji)
        )''')
        
        # Welcome settings
        c.execute('''CREATE TABLE IF NOT EXISTS welcome_settings (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            message TEXT DEFAULT 'Welcome to the server, {member}!',
            enabled INTEGER DEFAULT 1,
            rules_channel INTEGER,
            verify_channel INTEGER,
            roles_channel INTEGER
        )''')
        
        conn.commit()
        
        # Log stats
        c.execute('SELECT COUNT(*) FROM players')
        player_count = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM matches')
        match_count = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM teams')
        team_count = c.fetchone()[0]
        
        logger.info(f"Database initialized successfully")
        logger.info(f"  - Players: {player_count}")
        logger.info(f"  - Matches: {match_count}")
        logger.info(f"  - Teams: {team_count}")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)

def log_command(guild_id: int, user_id: int, command_name: str, success: bool = True):
    """Log command usage"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO command_logs (guild_id, user_id, command_name, timestamp, success)
                     VALUES (?, ?, ?, ?, ?)''',
                  (guild_id, user_id, command_name, datetime.now().isoformat(), 1 if success else 0))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log command: {e}")

def log_activity(guild_id: int, queue_name: str, user_id: int, action: str):
    """Log queue activity"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO activity_logs (guild_id, queue_name, user_id, action, timestamp)
                     VALUES (?, ?, ?, ?, ?)''',
                  (guild_id, queue_name, user_id, action, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

# ============================================================================
# HELPER FUNCTIONS - QUEUE MANAGEMENT
# ============================================================================

def get_queue(guild_id: int, queue_name: str = "default") -> List:
    """Get or create a queue for a guild"""
    if guild_id not in guild_queues:
        guild_queues[guild_id] = {}
    if queue_name not in guild_queues[guild_id]:
        guild_queues[guild_id][queue_name] = []
    return guild_queues[guild_id][queue_name]

def get_queue_settings(guild_id: int, queue_name: str = "default") -> Dict:
    """Get queue settings from database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM queue_settings WHERE guild_id=? AND queue_name=?', 
              (guild_id, queue_name))
    result = c.fetchone()
    conn.close()
    
    if result:
        return {
            'guild_id': result[0],
            'queue_name': result[1],
            'team_size': result[2],
            'team_selection_mode': result[3],
            'captain_mode': result[4],
            'required_role': result[5],
            'locked': result[6],
            'results_channel': result[7],
            'auto_move': result[8],
            'create_channels': result[9],
            'channel_category': result[10],
            'map_voting': result[11],
            'ping_players': result[12],
            'sticky_message': result[13],
            'name_type': result[14],
            'mmr_decay_enabled': result[15],
            'lobby_details_template': result[16],
            'team1_name': result[17] if len(result) > 17 else 'Team 1',
            'team2_name': result[18] if len(result) > 18 else 'Team 2',
            'game_mode': result[19] if len(result) > 19 else 'mix'
        }
    
    # Default settings
    return {
        'guild_id': guild_id,
        'queue_name': queue_name,
        'team_size': 5,
        'team_selection_mode': 'balanced',
        'captain_mode': 'random',
        'required_role': None,
        'locked': 0,
        'results_channel': None,
        'auto_move': 0,
        'create_channels': 0,
        'channel_category': None,
        'map_voting': 0,
        'ping_players': 1,
        'sticky_message': 0,
        'name_type': 'discord',
        'mmr_decay_enabled': 0,
        'lobby_details_template': None,
        'team1_name': 'Team 1',
        'team2_name': 'Team 2',
        'game_mode': 'mix'
    }

def save_queue_settings(settings: Dict):
    """Save queue settings to database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO queue_settings 
                 (guild_id, queue_name, team_size, team_selection_mode, captain_mode,
                  required_role, locked, results_channel, auto_move, create_channels,
                  channel_category, map_voting, ping_players, sticky_message, name_type,
                  mmr_decay_enabled, lobby_details_template, team1_name, team2_name, game_mode)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (settings['guild_id'], settings['queue_name'], settings['team_size'],
               settings['team_selection_mode'], settings['captain_mode'],
               settings['required_role'], settings['locked'],
               settings['results_channel'], settings['auto_move'],
               settings['create_channels'], settings['channel_category'],
               settings['map_voting'], settings['ping_players'],
               settings['sticky_message'], settings['name_type'],
               settings['mmr_decay_enabled'], settings['lobby_details_template'],
               settings.get('team1_name', 'Team 1'), settings.get('team2_name', 'Team 2'),
               settings.get('game_mode', 'mix')))
    conn.commit()
    conn.close()

def is_user_staff(guild: discord.Guild, user: discord.Member) -> bool:
    """Check if user is staff (admin or has staff role)"""
    if user.guild_permissions.administrator:
        return True
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT role_id FROM staff_roles WHERE guild_id=?', (guild.id,))
    staff_roles = [row[0] for row in c.fetchall()]
    conn.close()
    
    return any(role.id in staff_roles for role in user.roles)

def is_user_blacklisted(guild_id: int, queue_name: str, user_id: int) -> bool:
    """Check if user is blacklisted from queue"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT user_id FROM blacklist WHERE guild_id=? AND queue_name=? AND user_id=?',
              (guild_id, queue_name, user_id))
    result = c.fetchone()
    conn.close()
    return result is not None

def check_required_roles(guild: discord.Guild, user: discord.Member, queue_name: str) -> bool:
    """Check if user has required roles for queue"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT role_id FROM required_roles WHERE guild_id=? AND queue_name=?',
              (guild.id, queue_name))
    required_roles = [row[0] for row in c.fetchall()]
    conn.close()
    
    if not required_roles:
        return True
    
    user_role_ids = [role.id for role in user.roles]
    return any(role_id in user_role_ids for role_id in required_roles)

def get_or_create_player(user_id: int, username: str) -> Dict:
    """Get player stats or create new player"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM players WHERE user_id=?', (user_id,))
    result = c.fetchone()
    
    if not result:
        join_date = datetime.now().isoformat()
        c.execute('''INSERT INTO players 
                     (user_id, username, mmr, wins, losses, total_games, win_streak, highest_mmr, join_date)
                     VALUES (?, ?, 1000, 0, 0, 0, 0, 1000, ?)''',
                  (user_id, username, join_date))
        conn.commit()
        c.execute('SELECT * FROM players WHERE user_id=?', (user_id,))
        result = c.fetchone()
    
    conn.close()
    
    return {
        'user_id': result[0],
        'username': result[1],
        'mmr': result[2],
        'wins': result[3],
        'losses': result[4],
        'last_played': result[5],
        'total_games': result[6],
        'win_streak': result[7],
        'highest_mmr': result[8],
        'join_date': result[9],
        'grace_period_until': result[10] if len(result) > 10 else None
    }

def get_queue_player_stats(user_id: int, guild_id: int, queue_name: str) -> Dict:
    """Get player stats for specific queue"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM queue_stats WHERE user_id=? AND guild_id=? AND queue_name=?',
              (user_id, guild_id, queue_name))
    result = c.fetchone()
    
    if not result:
        c.execute('''INSERT INTO queue_stats (user_id, guild_id, queue_name, mmr)
                     VALUES (?, ?, ?, 1000)''',
                  (user_id, guild_id, queue_name))
        conn.commit()
        c.execute('SELECT * FROM queue_stats WHERE user_id=? AND guild_id=? AND queue_name=?',
                  (user_id, guild_id, queue_name))
        result = c.fetchone()
    
    conn.close()
    
    return {
        'user_id': result[0],
        'guild_id': result[1],
        'queue_name': result[2],
        'mmr': result[3],
        'wins': result[4],
        'losses': result[5],
        'games_played': result[6],
        'last_played': result[7] if len(result) > 7 else None
    }

def update_player_stats(user_id: int, guild_id: int, queue_name: str, mmr_change: int, won: bool):
    """Update player stats after a match"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Update queue-specific stats
    c.execute('SELECT * FROM queue_stats WHERE user_id=? AND guild_id=? AND queue_name=?',
              (user_id, guild_id, queue_name))
    stats = c.fetchone()
    
    if stats:
        new_mmr = max(0, stats[3] + mmr_change)
        new_wins = stats[4] + (1 if won else 0)
        new_losses = stats[5] + (0 if won else 1)
        new_games = stats[6] + 1
        
        c.execute('''UPDATE queue_stats 
                     SET mmr=?, wins=?, losses=?, games_played=?, last_played=?
                     WHERE user_id=? AND guild_id=? AND queue_name=?''',
                  (new_mmr, new_wins, new_losses, new_games, datetime.now().isoformat(),
                   user_id, guild_id, queue_name))
    
    # Update global stats
    c.execute('SELECT * FROM players WHERE user_id=?', (user_id,))
    player = c.fetchone()
    
    if player:
        new_mmr = max(0, player[2] + mmr_change)
        new_wins = player[3] + (1 if won else 0)
        new_losses = player[4] + (0 if won else 1)
        new_total = player[6] + 1
        new_streak = (player[7] + 1) if won else 0
        new_highest = max(player[8], new_mmr)
        
        c.execute('''UPDATE players 
                     SET mmr=?, wins=?, losses=?, total_games=?, win_streak=?, 
                         highest_mmr=?, last_played=?
                     WHERE user_id=?''',
                  (new_mmr, new_wins, new_losses, new_total, new_streak, 
                   new_highest, datetime.now().isoformat(), user_id))
    
    conn.commit()
    conn.close()

def create_balanced_teams(queue: List, guild_id: int, queue_name: str, team_size: int) -> Tuple[List, List]:
    """Create balanced teams based on MMR"""
    players_with_mmr = []
    for player_id in queue:
        stats = get_queue_player_stats(player_id, guild_id, queue_name)
        players_with_mmr.append((player_id, stats['mmr']))
    
    # Sort by MMR descending
    players_with_mmr.sort(key=lambda x: x[1], reverse=True)
    
    team1, team2 = [], []
    team1_mmr, team2_mmr = 0, 0
    
    # Distribute players to balance MMR
    for player_id, mmr in players_with_mmr:
        if team1_mmr <= team2_mmr:
            team1.append(player_id)
            team1_mmr += mmr
        else:
            team2.append(player_id)
            team2_mmr += mmr
    
    return team1, team2

def create_random_teams(queue: List, team_size: int) -> Tuple[List, List]:
    """Create random teams"""
    shuffled = queue.copy()
    random.shuffle(shuffled)
    mid = len(shuffled) // 2
    return shuffled[:mid], shuffled[mid:]

def generate_password(length: int = 8, alphanumeric: bool = True) -> str:
    """Generate random password for lobby details"""
    if alphanumeric:
        chars = string.ascii_letters + string.digits
    else:
        chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(chars) for _ in range(length))

def format_lobby_details(template: str, queue: List, guild: discord.Guild, queue_name: str, match_number: int) -> str:
    """Format lobby details with variable substitutions"""
    if not template:
        return None
    
    # Pick random host
    host_member = guild.get_member(random.choice(queue))
    host_name = host_member.display_name if host_member else "Unknown"
    
    # Pick random team name
    team_names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]
    random_team = random.choice(team_names)
    
    # Generate password
    password = generate_password(8, True)
    
    # Replace variables
    result = template.replace("{HOST}", host_name)
    result = result.replace("{QUEUENUM}", str(match_number))
    result = result.replace("{RANDOMTEAM}", random_team)
    result = result.replace("{PASSWORD8A}", password)
    
    return result

def check_role_limits(guild: discord.Guild, queue: List, queue_name: str) -> Tuple[bool, str]:
    """Check if queue violates role limits"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT role_id, max_count FROM role_limits WHERE guild_id=? AND queue_name=?',
              (guild.id, queue_name))
    limits = c.fetchall()
    conn.close()
    
    for role_id, max_count in limits:
        role = guild.get_role(role_id)
        if not role:
            continue
        
        count = sum(1 for uid in queue if role in guild.get_member(uid).roles)
        if count > max_count:
            return False, f"Too many players with role {role.name} (max: {max_count})"
    
    return True, ""

def get_maps_for_queue(guild_id: int, queue_name: str) -> List[str]:
    """Get all maps for a queue"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT map_name FROM maps WHERE guild_id=? AND queue_name=?',
              (guild_id, queue_name))
    maps = [row[0] for row in c.fetchall()]
    conn.close()
    return maps


def get_match_game_mode(guild_id: int, queue_name: str, match_number: int) -> str:
    """Get the game mode for a specific match based on queue settings.
    For MIX mode, rotates through HP â†’ SND â†’ Overload based on match number.
    Returns the game mode string (e.g. 'HP', 'SND', 'Overload')."""
    settings = get_queue_settings(guild_id, queue_name)
    game_mode = settings.get('game_mode', 'mix')
    
    if game_mode == 'hp':
        return 'HP'
    elif game_mode == 'snd':
        return 'SND'
    else:  # mix - rotate HP â†’ SND â†’ Overload
        mode_order = ['HP', 'SND', 'Overload']
        return mode_order[(match_number - 1) % 3]


def get_game_mode_emoji(mode: str) -> str:
    """Get emoji for a game mode"""
    emojis = {'HP': 'ðŸ”¥', 'SND': 'ðŸ’£', 'Overload': 'âš¡'}
    return emojis.get(mode, 'ðŸŽ®')


def select_bo3_maps(guild_id: int, queue_name: str) -> List[Dict]:
    """Select 3 random maps for a Best of 3 series with game modes assigned.
    Returns list of dicts: [{'map': 'Scar', 'mode': 'HP', 'emoji': 'ðŸ”¥'}, ...]
    """
    settings = get_queue_settings(guild_id, queue_name)
    game_mode = settings.get('game_mode', 'mix')
    available_maps = get_maps_for_queue(guild_id, queue_name)
    
    if not available_maps:
        available_maps = ["TBD"]
    
    # Pick 3 random maps (allow repeats if fewer than 3 maps available)
    if len(available_maps) >= 3:
        chosen_maps = random.sample(available_maps, 3)
    else:
        chosen_maps = [random.choice(available_maps) for _ in range(3)]
    
    # Assign game modes
    bo3_maps = []
    for i, map_name in enumerate(chosen_maps):
        if game_mode == 'hp':
            mode = 'HP'
        elif game_mode == 'snd':
            mode = 'SND'
        elif game_mode == 'mix':
            # Game 1 = HP, Game 2 = SND, Game 3 = Overload
            mode_order = ['HP', 'SND', 'Overload']
            mode = mode_order[i]
        else:
            mode = 'HP'
        
        bo3_maps.append({
            'map': map_name,
            'mode': mode,
            'emoji': get_game_mode_emoji(mode)
        })
    
    return bo3_maps


def format_bo3_maps(bo3_maps: List[Dict], scores: List[int] = None) -> str:
    """Format BO3 maps into a display string.
    scores: [team1_wins, team2_wins] for showing progress"""
    lines = []
    game_labels = ["Game 1", "Game 2", "Game 3"]
    
    for i, game in enumerate(bo3_maps):
        status = ""
        if scores:
            # This game has been played or is current
            total_played = scores[0] + scores[1]  # not used for per-game but for context
        
        lines.append(f"**{game_labels[i]}:** {game['emoji']} {game['mode']} â€” **{game['map']}**")
    
    return "\n".join(lines)

def apply_mmr_ranks(guild: discord.Guild, user_id: int, queue_name: str, mmr: int):
    """Apply rank roles based on MMR"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT rank_name, min_mmr, max_mmr, role_id FROM ranks WHERE guild_id=? AND queue_name=?',
              (guild.id, queue_name))
    ranks = c.fetchall()
    conn.close()
    
    member = guild.get_member(user_id)
    if not member:
        return
    
    for rank_name, min_mmr, max_mmr, role_id in ranks:
        role = guild.get_role(role_id)
        if not role:
            continue
        
        if min_mmr <= mmr <= max_mmr:
            # User should have this rank
            if role not in member.roles:
                asyncio.create_task(member.add_roles(role))
        else:
            # User should not have this rank
            if role in member.roles:
                asyncio.create_task(member.remove_roles(role))

# ============================================================================
# MUSIC HELPER FUNCTIONS
# ============================================================================

def get_music_queue(guild_id: int) -> MusicQueue:
    """Get or create music queue for a guild"""
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicQueue()
    return music_queues[guild_id]

async def extract_song_info(query: str) -> Optional[Dict]:
    """Extract song information from YouTube"""
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            if not query.startswith('http'):
                query = f"ytsearch:{query}"
            
            info = await asyncio.to_thread(ydl.extract_info, query, download=False)
            
            if 'entries' in info:
                info = info['entries'][0]
            
            return {
                'title': info.get('title', 'Unknown'),
                'url': info.get('url'),
                'webpage_url': info.get('webpage_url', ''),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail')
            }
    except Exception as e:
        logger.error(f"Failed to extract song info: {e}")
        return None

async def play_next(guild: discord.Guild):
    """Play next song in queue"""
    if not guild.voice_client:
        return
    
    music_queue = get_music_queue(guild.id)
    song = music_queue.next()
    
    if not song:
        now_playing.pop(guild.id, None)
        return
    
    try:
        # Get fresh stream URL
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, song['webpage_url'], download=False)
            song['url'] = info['url']
        
        source = discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(source, volume=music_queue.volume)
        
        def after_playing(error):
            if error:
                logger.error(f"Playback error: {error}")
            asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)
        
        guild.voice_client.play(source, after=after_playing)
        now_playing[guild.id] = song
        logger.info(f"Now playing: {song['title']} in {guild.name}")
        
    except Exception as e:
        logger.error(f"Error playing song: {e}")
        asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)

# Continued in next section...

# ============================================================================
# UI COMPONENTS
# ============================================================================

class QueueView(discord.ui.View):
    """Interactive buttons for queue management"""
    
    def __init__(self, queue_name: str = "default"):
        super().__init__(timeout=None)
        self.queue_name = queue_name
        self.message = None  # Store message reference for sticky updates
        self._previous_queue = []  # Track previous queue state to detect who left
    
    @discord.ui.button(label="Join Queue", style=discord.ButtonStyle.primary, custom_id="join_queue")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_join(interaction)
    
    @discord.ui.button(label="Leave Queue", style=discord.ButtonStyle.danger, custom_id="leave_queue")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_leave(interaction)
    
    async def handle_join(self, interaction: discord.Interaction):
        """Handle player joining queue WITH AUTO-START"""
        try:
            queue = get_queue(interaction.guild.id, self.queue_name)
            settings = get_queue_settings(interaction.guild.id, self.queue_name)
            
            # Check if locked
            if settings['locked']:
                await interaction.response.send_message("âŒ Queue is locked!", ephemeral=True)
                return
            
            # Check blacklist
            if is_user_blacklisted(interaction.guild.id, self.queue_name, interaction.user.id):
                await interaction.response.send_message("âŒ You are blacklisted from this queue!", ephemeral=True)
                return
            
            # Check required roles
            if not check_required_roles(interaction.guild, interaction.user, self.queue_name):
                await interaction.response.send_message("âŒ You don't have the required role to join this queue!", ephemeral=True)
                return
            
            # Check already in queue
            if interaction.user.id in queue:
                await interaction.response.send_message("âŒ You're already in the queue!", ephemeral=True)
                return
            
            # Add to queue
            queue.append(interaction.user.id)
            get_or_create_player(interaction.user.id, interaction.user.name)
            get_queue_player_stats(interaction.user.id, interaction.guild.id, self.queue_name)
            
            # Log activity
            log_activity(interaction.guild.id, self.queue_name, interaction.user.id, "joined")
            
            # Defer with no visible response - this prevents the "message deleted" notification
            await interaction.response.defer(thinking=False)
            
            await self.update_queue_display(interaction)
            
            # ðŸ”¥ AUTO-START CHECK ðŸ”¥
            required_players = settings['team_size'] * 2
            if len(queue) >= required_players:
                # Queue is full! Auto-start the match
                await asyncio.sleep(2)  # Small delay for dramatic effect
                await self.auto_start_match(interaction)
            
        except Exception as e:
            logger.error(f"Error in join handler: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"âŒ Error: {str(e)}")
            except:
                pass
    
    async def handle_leave(self, interaction: discord.Interaction):
        """Handle player leaving queue"""
        try:
            queue = get_queue(interaction.guild.id, self.queue_name)
            
            if interaction.user.id not in queue:
                await interaction.response.send_message("âŒ You're not in the queue!", ephemeral=True)
                return
            
            queue.remove(interaction.user.id)
            settings = get_queue_settings(interaction.guild.id, self.queue_name)
            
            # Log activity
            log_activity(interaction.guild.id, self.queue_name, interaction.user.id, "left")
            
            # Defer with no visible response - this prevents the "message deleted" notification
            await interaction.response.defer(thinking=False)
            
            await self.update_queue_display(interaction)
            
        except Exception as e:
            logger.error(f"Error in leave handler: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"âŒ Error: {str(e)}")
            except:
                pass
    
    async def handle_start(self, interaction: discord.Interaction):
        """Handle starting a match"""
        try:
            await interaction.response.defer()
            
            queue = get_queue(interaction.guild.id, self.queue_name)
            settings = get_queue_settings(interaction.guild.id, self.queue_name)
            required_players = settings['team_size'] * 2
            
            if len(queue) < required_players:
                await interaction.followup.send(
                    f"âŒ Need {required_players} players! Currently: {len(queue)}"
                )
                return
            
            # Get next match number
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT MAX(match_number) FROM matches WHERE guild_id=? AND queue_name=?',
                      (interaction.guild.id, self.queue_name))
            result = c.fetchone()[0]
            match_number = (result + 1) if result else 1
            conn.close()
            
            players = queue[:required_players]
            
            # Create teams based on mode
            if settings['team_selection_mode'] == 'balanced':
                team1, team2 = create_balanced_teams(players, interaction.guild.id, self.queue_name, settings['team_size'])
            elif settings['team_selection_mode'] == 'random':
                team1, team2 = create_random_teams(players, settings['team_size'])
            elif settings['team_selection_mode'] == 'captains':
                # Start captain draft
                await self.start_captain_draft(interaction, players, settings)
                return
            else:
                team1, team2 = create_balanced_teams(players, interaction.guild.id, self.queue_name, settings['team_size'])
            
            # Remove players from queue
            for player_id in players:
                queue.remove(player_id)
            
            # Generate lobby details if configured
            lobby_details = None
            if settings['lobby_details_template']:
                lobby_details = format_lobby_details(
                    settings['lobby_details_template'],
                    players,
                    interaction.guild,
                    self.queue_name,
                    match_number
                )
            
            # Create match embed
            bo3_maps = select_bo3_maps(interaction.guild.id, self.queue_name)
            bo3_display = format_bo3_maps(bo3_maps)
            
            embed = discord.Embed(
                title=f"ðŸŽ® Match #{match_number} Started!",
                description=f"Queue: **{self.queue_name}**\n\n"
                            f"**ðŸ“‹ Best of 3 Series:**\n{bo3_display}",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            # Get player names
            name_type = settings['name_type']
            team1_names = []
            team2_names = []
            
            for uid in team1:
                member = interaction.guild.get_member(uid)
                if member:
                    name = member.display_name if name_type == 'nicknames' else member.name
                    if settings['ping_players']:
                        team1_names.append(member.mention)
                    else:
                        team1_names.append(name)
            
            for uid in team2:
                member = interaction.guild.get_member(uid)
                if member:
                    name = member.display_name if name_type == 'nicknames' else member.name
                    if settings['ping_players']:
                        team2_names.append(member.mention)
                    else:
                        team2_names.append(name)
            
            # Calculate average MMR
            team1_mmr = sum(get_queue_player_stats(uid, interaction.guild.id, self.queue_name)['mmr'] for uid in team1) // len(team1)
            team2_mmr = sum(get_queue_player_stats(uid, interaction.guild.id, self.queue_name)['mmr'] for uid in team2) // len(team2)
            
            embed.add_field(
                name=f"Team 1 (Avg MMR: {team1_mmr})",
                value="\n".join(team1_names),
                inline=True
            )
            embed.add_field(
                name=f"Team 2 (Avg MMR: {team2_mmr})",
                value="\n".join(team2_names),
                inline=True
            )
            
            if lobby_details:
                embed.add_field(name="ðŸ“‹ Lobby Details", value=lobby_details, inline=False)
            
            # Get custom team names
            team1_name = settings.get('team1_name', 'Team 1')
            team2_name = settings.get('team2_name', 'Team 2')
            
            embed.set_footer(text="Best of 3 â€” Vote for the winner of each game!")
            
            # Store match data
            match_data = {
                'match_id': None,  # Will be set after DB insert
                'team1': team1,
                'team2': team2,
                'timestamp': datetime.now().isoformat(),
                'lobby_details': lobby_details
            }
            
            # Save to database
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''INSERT INTO matches 
                         (guild_id, queue_name, timestamp, team1, team2, match_number, lobby_details)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (interaction.guild.id, self.queue_name, match_data['timestamp'],
                       json.dumps(team1), json.dumps(team2), match_number, lobby_details))
            match_id = c.lastrowid
            conn.commit()
            conn.close()
            
            match_data['match_id'] = match_id
            
            if interaction.guild.id not in active_matches:
                active_matches[interaction.guild.id] = {}
            active_matches[interaction.guild.id][self.queue_name] = match_data
            
            # Send to results channel if configured
            if settings['results_channel']:
                channel = interaction.guild.get_channel(settings['results_channel'])
                if channel:
                    await channel.send(embed=embed)
            
            # Auto-move players if enabled
            if settings['auto_move'] and settings['create_channels']:
                await self.auto_move_players(interaction.guild, team1, team2, settings, match_number)
            
            # Calculate required votes - minimum 5 or majority of players
            required_votes = max(5, (len(team1) + len(team2)) // 2 + 1)
            
            # Create voting view
            vote_view = MatchVoteView(
                match_id, team1, team2, self.queue_name,
                required_votes, team1_name, team2_name, bo3_maps
            )
            
            await interaction.followup.send(embed=embed, view=vote_view)
            await self.update_queue_display(interaction)
            
        except Exception as e:
            logger.error(f"Error starting match: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"âŒ Error starting match: {str(e)}")
            except:
                pass
    
    async def start_captain_draft(self, interaction: discord.Interaction, players: List, settings: Dict):
        """Start captain draft mode"""
        # This would implement captain selection and draft
        # For now, fall back to balanced
        team1, team2 = create_balanced_teams(players, interaction.guild.id, self.queue_name, settings['team_size'])
        await interaction.followup.send("âš ï¸ Captain mode not fully implemented yet, using balanced teams")
    
    async def auto_move_players(self, guild: discord.Guild, team1: List, team2: List, settings: Dict, match_number: int):
        """Auto-move players to team voice channels"""
        try:
            category_id = settings['channel_category']
            if not category_id:
                return
            
            category = guild.get_channel(category_id)
            if not category:
                return
            
            # Create team channels
            team1_channel = await guild.create_voice_channel(
                f"Match #{match_number} - Team 1",
                category=category
            )
            team2_channel = await guild.create_voice_channel(
                f"Match #{match_number} - Team 2",
                category=category
            )
            
            # Move players
            for user_id in team1:
                member = guild.get_member(user_id)
                if member and member.voice:
                    await member.move_to(team1_channel)
            
            for user_id in team2:
                member = guild.get_member(user_id)
                if member and member.voice:
                    await member.move_to(team2_channel)
            
        except Exception as e:
            logger.error(f"Error auto-moving players: {e}")
    
    async def update_queue_display(self, interaction: discord.Interaction):
        """Update the queue display message - NeatQueue style"""
        try:
            queue = get_queue(interaction.guild.id, self.queue_name)
            settings = get_queue_settings(interaction.guild.id, self.queue_name)
            guild = interaction.guild
            
            # Check if someone just left (compare current queue with previous state if available)
            left_player = None
            if hasattr(self, '_previous_queue'):
                for user_id in self._previous_queue:
                    if user_id not in queue:
                        member = guild.get_member(user_id)
                        if member:
                            left_player = member
                        break
            
            # Store current queue for next comparison
            self._previous_queue = queue.copy()
            
            # Create embed with dark theme and red left border (like NeatQueue)
            # Show the actual queue name exactly as it was entered
            queue_display_name = self.queue_name if self.queue_name != "default" else "Queue"
            
            embed = discord.Embed(
                title=queue_display_name,
                color=0xed4245  # Discord red color for left border
            )
            
            # Build description - shorter box with less padding
            description_parts = []
            
            # If someone just left, show that message at the top
            if left_player:
                description_parts.append(f"**Player Left Queue!**")
                description_parts.append(f"{left_player.mention}")
                description_parts.append("")  # Empty line for spacing
            
            # Add queue count
            description_parts.append(f"**Queue {len(queue)}/{settings['team_size']*2}**")
            description_parts.append("")  # Empty line for spacing
            
            # Show players in queue with mentions
            if queue:
                for user_id in queue:
                    member = guild.get_member(user_id)
                    if member:
                        description_parts.append(f"{member.mention}")
            else:
                description_parts.append("*No players in queue*")
            
            # Add moderate padding to keep box visible but shorter (3-5 lines instead of 10)
            padding_lines = max(0, 5 - len(queue))
            for _ in range(padding_lines):
                description_parts.append("")
            
            # Add timestamp at bottom - Discord format automatically adjusts to user's timezone
            timestamp = f"<t:{int(datetime.now().timestamp())}:t>"  # Shows time in user's local timezone
            description_parts.append(timestamp)
            
            embed.description = "\n".join(description_parts)
            
            # Sticky message: Delete and repost to keep at bottom
            if settings.get('sticky_message', 0):
                try:
                    # Get the message to delete - use self.message which is set when queue is started
                    message_to_delete = self.message
                    
                    if message_to_delete:
                        # Send new message at bottom first
                        new_message = await interaction.channel.send(embed=embed, view=self)
                        
                        # Then delete the old message
                        await message_to_delete.delete()
                        
                        # Update the view's message reference
                        self.message = new_message
                        
                        # Update sticky tracking
                        if interaction.channel.id in sticky_queue_messages:
                            sticky_queue_messages[interaction.channel.id]['message'] = new_message
                except Exception as e:
                    logger.error(f"Error with sticky message: {e}")
                    # Fall back to regular edit if sticky fails
                    if self.message:
                        await self.message.edit(embed=embed, view=self)
            else:
                # Regular update - edit the queue message directly
                if self.message:
                    await self.message.edit(embed=embed, view=self)
                    
        except Exception as e:
            logger.error(f"Error updating queue display: {e}")
    
    async def auto_start_match(self, interaction: discord.Interaction):
        """Automatically start a match with custom team names and sequential numbering"""
        try:
            queue = get_queue(interaction.guild.id, self.queue_name)
            settings = get_queue_settings(interaction.guild.id, self.queue_name)
            required_players = settings['team_size'] * 2
            
            if len(queue) < required_players:
                return
            
            # Get next match number (sequential)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT MAX(match_number) FROM matches WHERE guild_id=? AND queue_name=?',
                      (interaction.guild.id, self.queue_name))
            result = c.fetchone()[0]
            match_number = (result + 1) if result else 1
            conn.close()
            
            # Get custom team names
            team1_name = settings.get('team1_name', 'Team 1')
            team2_name = settings.get('team2_name', 'Team 2')
            
            players = queue[:required_players]
            
            # Create teams
            if settings['team_selection_mode'] == 'balanced':
                team1, team2 = create_balanced_teams(players, interaction.guild.id, self.queue_name, settings['team_size'])
            elif settings['team_selection_mode'] == 'random':
                team1, team2 = create_random_teams(players, settings['team_size'])
            else:
                team1, team2 = create_balanced_teams(players, interaction.guild.id, self.queue_name, settings['team_size'])
            
            # Remove players from queue
            for player_id in players:
                queue.remove(player_id)
            
            # Create match channels
            category_id = settings.get('channel_category')
            category = interaction.guild.get_channel(category_id) if category_id else None
            
            # Create text channel
            match_text_channel = await interaction.guild.create_text_channel(
                f"queue-{match_number}-{self.queue_name}",
                category=category,
                topic=f"Match #{match_number} | {team1_name} vs {team2_name}"
            )
            
            # Create voice channels with custom team names
            team1_voice = await interaction.guild.create_voice_channel(
                f"Queue {match_number} | {team1_name}",
                category=category
            )
            team2_voice = await interaction.guild.create_voice_channel(
                f"Queue {match_number} | {team2_name}",
                category=category
            )
            
            # Store channel IDs for cleanup
            if interaction.guild.id not in active_match_channels:
                active_match_channels[interaction.guild.id] = {}
            
            active_match_channels[interaction.guild.id][self.queue_name] = {
                'text': match_text_channel.id,
                'voice1': team1_voice.id,
                'voice2': team2_voice.id,
                'match_number': match_number
            }
            
            # Set permissions - only match players can see
            await match_text_channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await team1_voice.set_permissions(interaction.guild.default_role, view_channel=False)
            await team2_voice.set_permissions(interaction.guild.default_role, view_channel=False)
            
            # Team 1 permissions
            for user_id in team1:
                member = interaction.guild.get_member(user_id)
                if member:
                    await match_text_channel.set_permissions(member, view_channel=True, send_messages=True)
                    await team1_voice.set_permissions(member, view_channel=True, connect=True)
            
            # Team 2 permissions
            for user_id in team2:
                member = interaction.guild.get_member(user_id)
                if member:
                    await match_text_channel.set_permissions(member, view_channel=True, send_messages=True)
                    await team2_voice.set_permissions(member, view_channel=True, connect=True)
            
            # Auto-move players
            if settings.get('auto_move'):
                for user_id in team1:
                    member = interaction.guild.get_member(user_id)
                    if member and member.voice:
                        try:
                            await member.move_to(team1_voice)
                        except:
                            pass
                
                for user_id in team2:
                    member = interaction.guild.get_member(user_id)
                    if member and member.voice:
                        try:
                            await member.move_to(team2_voice)
                        except:
                            pass
            
            # Calculate MMR
            team1_mmr = sum(get_queue_player_stats(uid, interaction.guild.id, self.queue_name)['mmr'] for uid in team1) // len(team1)
            team2_mmr = sum(get_queue_player_stats(uid, interaction.guild.id, self.queue_name)['mmr'] for uid in team2) // len(team2)
            
            # Get player names
            name_type = settings['name_type']
            team1_names = []
            team2_names = []
            
            for uid in team1:
                member = interaction.guild.get_member(uid)
                if member:
                    name = member.display_name if name_type == 'nicknames' else member.name
                    team1_names.append(member.mention if settings['ping_players'] else name)
            
            for uid in team2:
                member = interaction.guild.get_member(uid)
                if member:
                    name = member.display_name if name_type == 'nicknames' else member.name
                    team2_names.append(member.mention if settings['ping_players'] else name)
            
            # Create announcement embed
            bo3_maps = select_bo3_maps(interaction.guild.id, self.queue_name)
            bo3_display = format_bo3_maps(bo3_maps)
            
            embed = discord.Embed(
                title=f"ðŸŽ® Queue #{match_number} Started! (AUTO-START)",
                description=f"**{self.queue_name}** - {team1_name} vs {team2_name}\n\n"
                            f"**ðŸ“‹ Best of 3 Series:**\n{bo3_display}\n\n"
                            f"Match channels have been created!\n"
                            f"Check {match_text_channel.mention} for details.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name=f"ðŸ”µ {team1_name} (Avg MMR: {team1_mmr})",
                value="\n".join(team1_names),
                inline=True
            )
            embed.add_field(
                name=f"ðŸ”´ {team2_name} (Avg MMR: {team2_mmr})",
                value="\n".join(team2_names),
                inline=True
            )
            
            embed.add_field(
                name="Voice Channels Created",
                value=f"ðŸ”µ {team1_voice.mention}\nðŸ”´ {team2_voice.mention}",
                inline=False
            )
            
            # Save match to database
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''INSERT INTO matches 
                         (guild_id, queue_name, timestamp, team1, team2, match_number)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (interaction.guild.id, self.queue_name, datetime.now().isoformat(),
                       json.dumps(team1), json.dumps(team2), match_number))
            match_id = c.lastrowid
            conn.commit()
            conn.close()
            
            # Send announcement in original channel
            await interaction.channel.send(embed=embed)
            
            # Create match info in text channel
            match_embed = discord.Embed(
                title=f"ðŸŽ® Queue #{match_number} - {self.queue_name}",
                description=f"**{team1_name} vs {team2_name}**\n\n"
                            f"**ðŸ“‹ Best of 3 â€” First to 2 wins!**\n{bo3_display}\n\n"
                            f"Vote for the winner of each game below.\n"
                            f"Series ends when a team wins 2 games.",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            match_embed.add_field(
                name=f"ðŸ”µ {team1_name} (Avg MMR: {team1_mmr})",
                value="\n".join(team1_names),
                inline=True
            )
            match_embed.add_field(
                name=f"ðŸ”´ {team2_name} (Avg MMR: {team2_mmr})",
                value="\n".join(team2_names),
                inline=True
            )
            
            match_embed.add_field(
                name="ðŸŽ™ï¸ Voice Channels",
                value=f"ðŸ”µ {team1_voice.mention} ({team1_name})\n"
                      f"ðŸ”´ {team2_voice.mention} ({team2_name})",
                inline=False
            )
            
            match_embed.set_footer(text=f"Queue #{match_number} | Vote after your match!")
            
            # Calculate required votes
            required_votes = max(5, (len(team1) + len(team2)) // 2 + 1)
            
            # Send voting message
            vote_view = MatchVoteView(
                match_id, team1, team2, self.queue_name, 
                required_votes, team1_name, team2_name, bo3_maps
            )
            await match_text_channel.send(embed=match_embed, view=vote_view)
            
            # Send to results channel
            if settings['results_channel']:
                channel = interaction.guild.get_channel(settings['results_channel'])
                if channel:
                    await channel.send(embed=embed)
            
            # Update queue display
            await self.update_queue_display(interaction)
            
            logger.info(f"Queue #{match_number} auto-started: {team1_name} vs {team2_name}")
            
        except Exception as e:
            logger.error(f"Error auto-starting match: {e}", exc_info=True)

class MatchVoteView(discord.ui.View):
    """Best of 3 voting - players vote per game, first team to 2 wins takes the series"""
    
    def __init__(self, match_id: int, team1: List, team2: List, queue_name: str, 
                 required_votes: int, team1_name: str = "Team 1", team2_name: str = "Team 2",
                 bo3_maps: List[Dict] = None):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.team1 = team1
        self.team2 = team2
        self.queue_name = queue_name
        self.required_votes = required_votes
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.bo3_maps = bo3_maps or []
        
        # BO3 series state
        self.current_game = 1  # 1, 2, or 3
        self.series_score = [0, 0]  # [team1_wins, team2_wins]
        self.game_results = []  # list of winning team per game
        
        # Update button labels
        self._update_button_labels()
        
        # Initialize votes
        if match_id not in match_votes:
            match_votes[match_id] = {
                'team1': set(),
                'team2': set(),
                'all_players': set(team1 + team2)
            }
    
    def _update_button_labels(self):
        """Update buttons to show current game info"""
        game_info = ""
        if self.bo3_maps and self.current_game <= len(self.bo3_maps):
            game = self.bo3_maps[self.current_game - 1]
            game_info = f" (Game {self.current_game}: {game['mode']} - {game['map']})"
        
        self.children[0].label = f"{self.team1_name} Won{game_info}"
        self.children[1].label = f"{self.team2_name} Won{game_info}"
    
    @discord.ui.button(label="Team 1 Won", style=discord.ButtonStyle.primary, custom_id="vote_team1")
    async def vote_team1_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, 1)
    
    @discord.ui.button(label="Team 2 Won", style=discord.ButtonStyle.danger, custom_id="vote_team2")
    async def vote_team2_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_vote(interaction, 2)
    
    async def handle_vote(self, interaction: discord.Interaction, team: int):
        """Handle a vote for a team"""
        try:
            user_id = interaction.user.id
            votes = match_votes[self.match_id]
            
            # Check if user is in the match
            if user_id not in votes['all_players']:
                await interaction.response.send_message(
                    "âŒ Only players from this match can vote!",
                    ephemeral=True
                )
                return
            
            # Remove from other team if they voted before
            if team == 1:
                votes['team2'].discard(user_id)
                votes['team1'].add(user_id)
                voted_for = self.team1_name
            else:
                votes['team1'].discard(user_id)
                votes['team2'].add(user_id)
                voted_for = self.team2_name
            
            team1_votes = len(votes['team1'])
            team2_votes = len(votes['team2'])
            
            game_info = ""
            if self.bo3_maps and self.current_game <= len(self.bo3_maps):
                game = self.bo3_maps[self.current_game - 1]
                game_info = f"\n**Current Game:** {game['emoji']} {game['mode']} on **{game['map']}**"
            
            await interaction.response.send_message(
                f"âœ… Vote recorded for **{voted_for}**!{game_info}\n"
                f"**Current Votes:** {self.team1_name}: {team1_votes} | {self.team2_name}: {team2_votes}\n"
                f"**Needed:** {self.required_votes} votes\n"
                f"**Series:** {self.team1_name} {self.series_score[0]} - {self.series_score[1]} {self.team2_name}",
                ephemeral=True
            )
            
            # Check if we have enough votes for this game
            if team1_votes >= self.required_votes:
                await self.finalize_game(interaction, 1)
            elif team2_votes >= self.required_votes:
                await self.finalize_game(interaction, 2)
            else:
                await self.update_vote_display(interaction)
                
        except Exception as e:
            logger.error(f"Error handling vote: {e}", exc_info=True)
            try:
                await interaction.response.send_message(f"âŒ Error: {str(e)}", ephemeral=True)
            except:
                pass
    
    async def update_vote_display(self, interaction: discord.Interaction):
        """Update the vote count display for current game"""
        try:
            votes = match_votes[self.match_id]
            team1_votes = len(votes['team1'])
            team2_votes = len(votes['team2'])
            
            # Build series status
            series_status = f"**Series: {self.team1_name} {self.series_score[0]} - {self.series_score[1]} {self.team2_name}**"
            
            # Build game results history
            results_lines = []
            for i, result in enumerate(self.game_results):
                game = self.bo3_maps[i] if i < len(self.bo3_maps) else {}
                winner_name = self.team1_name if result == 1 else self.team2_name
                results_lines.append(f"~~Game {i+1}: {game.get('emoji', 'ðŸŽ®')} {game.get('mode', '?')} â€” {game.get('map', '?')}~~ â†’ **{winner_name}** âœ…")
            
            # Current game info
            current_game_info = ""
            if self.bo3_maps and self.current_game <= len(self.bo3_maps):
                game = self.bo3_maps[self.current_game - 1]
                current_game_info = f"â–¶ï¸ **Game {self.current_game}: {game['emoji']} {game['mode']} â€” {game['map']}**"
            
            # Future games
            future_lines = []
            for i in range(self.current_game, min(3, len(self.bo3_maps))):
                game = self.bo3_maps[i]
                future_lines.append(f"Game {i+1}: {game['emoji']} {game['mode']} â€” {game['map']}")
            
            description_parts = [series_status, ""]
            if results_lines:
                description_parts.extend(results_lines)
            if current_game_info:
                description_parts.append(current_game_info)
            if future_lines:
                description_parts.extend(future_lines)
            
            description_parts.append(f"\nVote for who won Game {self.current_game}!")
            description_parts.append(f"**{self.required_votes} votes needed**")
            
            embed = discord.Embed(
                title=f"ðŸ—³ï¸ Best of 3 â€” Game {self.current_game} Voting",
                description="\n".join(description_parts),
                color=discord.Color.gold()
            )
            
            embed.add_field(
                name=f"ðŸ”µ {self.team1_name}",
                value=f"**{team1_votes}** votes",
                inline=True
            )
            embed.add_field(
                name=f"ðŸ”´ {self.team2_name}",
                value=f"**{team2_votes}** votes",
                inline=True
            )
            
            if interaction.message:
                await interaction.message.edit(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Error updating vote display: {e}")
    
    async def finalize_game(self, interaction: discord.Interaction, winning_team: int):
        """Finalize a single game in the BO3 series"""
        try:
            # Record game result
            self.series_score[winning_team - 1] += 1
            self.game_results.append(winning_team)
            
            winner_name = self.team1_name if winning_team == 1 else self.team2_name
            game = self.bo3_maps[self.current_game - 1] if self.current_game <= len(self.bo3_maps) else {}
            
            # Check if series is over (first to 2)
            if self.series_score[0] >= 2 or self.series_score[1] >= 2:
                await self.finalize_series(interaction)
                return
            
            # Series continues â€” move to next game
            self.current_game += 1
            
            # Reset votes for next game
            match_votes[self.match_id]['team1'] = set()
            match_votes[self.match_id]['team2'] = set()
            
            # Update button labels for next game
            self._update_button_labels()
            
            # Show game result and next game info
            next_game = self.bo3_maps[self.current_game - 1] if self.current_game <= len(self.bo3_maps) else {}
            
            # Build series status
            results_lines = []
            for i, result in enumerate(self.game_results):
                g = self.bo3_maps[i] if i < len(self.bo3_maps) else {}
                w = self.team1_name if result == 1 else self.team2_name
                results_lines.append(f"Game {i+1}: {g.get('emoji', 'ðŸŽ®')} {g.get('mode', '?')} â€” {g.get('map', '?')} â†’ **{w}** âœ…")
            
            embed = discord.Embed(
                title=f"ðŸ—³ï¸ Best of 3 â€” Game {self.current_game} Voting",
                description=(
                    f"**{winner_name}** won Game {self.current_game - 1}!\n\n"
                    f"**Series: {self.team1_name} {self.series_score[0]} - {self.series_score[1]} {self.team2_name}**\n\n"
                    + "\n".join(results_lines) + "\n"
                    f"â–¶ï¸ **Game {self.current_game}: {next_game.get('emoji', 'ðŸŽ®')} {next_game.get('mode', '?')} â€” {next_game.get('map', '?')}**\n\n"
                    f"Vote for who won Game {self.current_game}!\n"
                    f"**{self.required_votes} votes needed**"
                ),
                color=discord.Color.gold()
            )
            
            embed.add_field(name=f"ðŸ”µ {self.team1_name}", value="**0** votes", inline=True)
            embed.add_field(name=f"ðŸ”´ {self.team2_name}", value="**0** votes", inline=True)
            
            if interaction.message:
                await interaction.message.edit(embed=embed, view=self)
            
        except Exception as e:
            logger.error(f"Error finalizing game: {e}", exc_info=True)
    
    async def finalize_series(self, interaction: discord.Interaction):
        """Finalize the entire BO3 series"""
        try:
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            series_winner = 1 if self.series_score[0] >= 2 else 2
            winning_team_name = self.team1_name if series_winner == 1 else self.team2_name
            
            # Update match in database
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('UPDATE matches SET winner=?, team1_score=?, team2_score=? WHERE match_id=?',
                      (series_winner, self.series_score[0], self.series_score[1], self.match_id))
            conn.commit()
            conn.close()
            
            # Award MMR
            winners = self.team1 if series_winner == 1 else self.team2
            losers = self.team2 if series_winner == 1 else self.team1
            mmr_change = 25
            
            for user_id in winners:
                update_player_stats(user_id, interaction.guild.id, self.queue_name, mmr_change, won=True)
                stats = get_queue_player_stats(user_id, interaction.guild.id, self.queue_name)
                apply_mmr_ranks(interaction.guild, user_id, self.queue_name, stats['mmr'])
            
            for user_id in losers:
                update_player_stats(user_id, interaction.guild.id, self.queue_name, -mmr_change, won=False)
                stats = get_queue_player_stats(user_id, interaction.guild.id, self.queue_name)
                apply_mmr_ranks(interaction.guild, user_id, self.queue_name, stats['mmr'])
            
            # Build game-by-game results
            results_lines = []
            for i, result in enumerate(self.game_results):
                game = self.bo3_maps[i] if i < len(self.bo3_maps) else {}
                w = self.team1_name if result == 1 else self.team2_name
                results_lines.append(f"Game {i+1}: {game.get('emoji', 'ðŸŽ®')} {game.get('mode', '?')} â€” {game.get('map', '?')} â†’ **{w}** âœ…")
            
            embed = discord.Embed(
                title=f"ðŸ† {winning_team_name} Wins the Series!",
                description=(
                    f"**Final Score: {self.team1_name} {self.series_score[0]} - {self.series_score[1]} {self.team2_name}**\n\n"
                    + "\n".join(results_lines)
                ),
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="MMR Changes",
                value=f"âœ… **{winning_team_name}:** +{mmr_change} MMR\n"
                      f"âŒ **Losing Team:** -{mmr_change} MMR",
                inline=False
            )
            
            embed.set_footer(text="Channels will be deleted in 30 seconds...")
            
            # Update message
            if interaction.message:
                await interaction.message.edit(embed=embed, view=self)
            
            # Send to results channel
            settings = get_queue_settings(interaction.guild.id, self.queue_name)
            if settings['results_channel']:
                channel = interaction.guild.get_channel(settings['results_channel'])
                if channel:
                    await channel.send(embed=embed)
            
            # Delete channels after 30 seconds
            if interaction.guild.id in active_match_channels:
                if self.queue_name in active_match_channels[interaction.guild.id]:
                    await asyncio.sleep(30)
                    await self.cleanup_channels(interaction.guild)
            
            # Clean up votes
            if self.match_id in match_votes:
                del match_votes[self.match_id]
            
            # Clean up active match tracking
            if interaction.guild.id in active_matches:
                if self.queue_name in active_matches[interaction.guild.id]:
                    del active_matches[interaction.guild.id][self.queue_name]
                
        except Exception as e:
            logger.error(f"Error finalizing series: {e}", exc_info=True)
    
    async def cleanup_channels(self, guild: discord.Guild):
        """Delete match text and voice channels"""
        try:
            channels_data = active_match_channels[guild.id].get(self.queue_name, {})
            
            # Delete text channel
            if 'text' in channels_data:
                text_channel = guild.get_channel(channels_data['text'])
                if text_channel:
                    await text_channel.delete()
            
            # Delete voice channels
            if 'voice1' in channels_data:
                voice1 = guild.get_channel(channels_data['voice1'])
                if voice1:
                    await voice1.delete()
            
            if 'voice2' in channels_data:
                voice2 = guild.get_channel(channels_data['voice2'])
                if voice2:
                    await voice2.delete()
            
            # Clean up tracking
            del active_match_channels[guild.id][self.queue_name]
            
            logger.info(f"Cleaned up Queue #{channels_data.get('match_number', '?')} channels")
            
        except Exception as e:
            logger.error(f"Error cleaning up channels: {e}")

class MapVoteView(discord.ui.View):
    """Map voting buttons"""
    
    def __init__(self, maps: List[str], match_id: int):
        super().__init__(timeout=60)
        self.maps = maps
        self.match_id = match_id
        self.votes = {}
        
        # Add buttons for each map
        for map_name in maps[:5]:  # Limit to 5 maps
            button = discord.ui.Button(label=map_name, style=discord.ButtonStyle.primary)
            button.callback = self.make_vote_callback(map_name)
            self.add_item(button)
    
    def make_vote_callback(self, map_name: str):
        async def callback(interaction: discord.Interaction):
            self.votes[interaction.user.id] = map_name
            await interaction.response.send_message(f"âœ… Voted for **{map_name}**!", ephemeral=True)
        return callback
    
    def get_winning_map(self) -> str:
        """Get map with most votes"""
        if not self.votes:
            return random.choice(self.maps)
        
        vote_counts = {}
        for map_name in self.votes.values():
            vote_counts[map_name] = vote_counts.get(map_name, 0) + 1
        
        return max(vote_counts, key=vote_counts.get)


# ============================================================================
# BOT EVENTS
# ============================================================================

@bot.event
async def on_ready():
    """Bot startup event"""
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    logger.info(f'Connected to {len(bot.guilds)} guilds')
    
    init_db()
    
    # Register persistent reaction role views (button-based panels)
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT panel_id, message_id FROM reaction_role_panels')
        panels = c.fetchall()
        conn.close()
        
        for panel_id, message_id in panels:
            view = ReactionRoleView(panel_id)
            bot.add_view(view, message_id=message_id)
        
        if panels:
            logger.info(f'Registered {len(panels)} button reaction role panels')
    except Exception as e:
        logger.error(f'Failed to load button reaction role panels: {e}')
    
    # Reload emoji reaction roles (Carl-bot style)
    try:
        logger.info("Reloading emoji reaction role messages...")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('SELECT message_id, channel_id, guild_id FROM emoji_reaction_messages')
        messages = c.fetchall()
        
        reload_count = 0
        for msg_id, channel_id, guild_id in messages:
            try:
                guild = bot.get_guild(guild_id)
                if not guild:
                    continue
                
                channel = guild.get_channel(channel_id)
                if not channel:
                    continue
                
                message = await channel.fetch_message(msg_id)
                
                # Get all emojis for this message
                c.execute('SELECT emoji FROM emoji_reaction_pairs WHERE message_id = ?', (msg_id,))
                emojis = [row[0] for row in c.fetchall()]
                
                # Add reactions that are missing
                for emoji in emojis:
                    try:
                        await message.add_reaction(emoji)
                    except:
                        pass  # Reaction might already exist
                
                reload_count += 1
                logger.info(f"Reloaded reactions for emoji reaction message {msg_id}")
                
            except Exception as e:
                logger.error(f"Error reloading reactions for message {msg_id}: {e}")
        
        conn.close()
        if reload_count > 0:
            logger.info(f"Emoji reaction role reload complete! Reloaded {reload_count} messages")
    except Exception as e:
        logger.error(f'Failed to reload emoji reaction roles: {e}')
    
    # Start scheduled tasks
    check_scheduled_tasks.start()
    
    try:
        synced = await bot.tree.sync()
        logger.info(f'Synced {len(synced)} commands')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')
    
    logger.info('JarvisQueue is ready!')

@bot.event
async def on_message(message):
    """Handle sticky queue messages - repost queue to bottom when new messages arrive"""
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Check if this channel has a sticky queue
    if message.channel.id in sticky_queue_messages:
        try:
            sticky_data = sticky_queue_messages[message.channel.id]
            old_message = sticky_data['message']
            view = sticky_data['view']
            queue_name = sticky_data['queue_name']
            guild_id = sticky_data['guild_id']
            
            # Get current queue data
            queue = get_queue(guild_id, queue_name)
            settings = get_queue_settings(guild_id, queue_name)
            
            # Recreate the embed
            queue_display_name = queue_name if queue_name != "default" else "Queue"
            
            embed = discord.Embed(
                title=queue_display_name,
                color=0xed4245
            )
            
            description_parts = []
            description_parts.append(f"**Queue {len(queue)}/{settings['team_size']*2}**")
            description_parts.append("")
            
            # Show players in queue with mentions
            if queue:
                guild = message.guild
                for user_id in queue:
                    member = guild.get_member(user_id)
                    if member:
                        description_parts.append(f"{member.mention}")
            else:
                description_parts.append("*No players in queue*")
            
            # Add moderate padding to keep box visible but shorter (3-5 lines instead of 10)
            padding_lines = max(0, 5 - len(queue))
            for _ in range(padding_lines):
                description_parts.append("")
            
            timestamp = f"<t:{int(datetime.now().timestamp())}:t>"  # Shows time in user's local timezone
            description_parts.append(timestamp)
            
            embed.description = "\n".join(description_parts)
            
            # Send new message at bottom
            new_message = await message.channel.send(embed=embed, view=view)
            
            # Delete old message
            try:
                await old_message.delete()
            except:
                pass  # Message might already be deleted
            
            # Update references
            view.message = new_message
            sticky_queue_messages[message.channel.id]['message'] = new_message
            
        except Exception as e:
            logger.error(f"Error in sticky message handler: {e}")
    
    # Process commands
    await bot.process_commands(message)

# ============================================================================
# SCHEDULED TASKS
# ============================================================================

@tasks.loop(minutes=5)
async def check_scheduled_tasks():
    """Check and execute scheduled commands"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT * FROM scheduled_tasks')
        tasks = c.fetchall()
        conn.close()
        
        current_time = datetime.now()
        
        for task in tasks:
            task_id, guild_id, channel_id, command_name, command_args, schedule_times, created_by, created_at = task
            times = json.loads(schedule_times) if schedule_times else []
            
            for time_str in times:
                # Parse time
                try:
                    scheduled_time = datetime.fromisoformat(time_str)
                    if abs((current_time - scheduled_time).total_seconds()) < 300:  # Within 5 minutes
                        # Execute command
                        guild = bot.get_guild(guild_id)
                        if guild:
                            logger.info(f"Executing scheduled task: {command_name}")
                            # Would execute the command here
                except:
                    pass
    except Exception as e:
        logger.error(f"Error in scheduled tasks: {e}")

# ============================================================================
# INTERACTIVE SETUP VIEWS & MODALS
# ============================================================================

class QueueTypeView(discord.ui.View):
    """Interactive queue type selection - Step 1"""
    
    def __init__(self):
        super().__init__(timeout=300)
        self.queue_type = None
        
    @discord.ui.button(label="PUGs/Normal Individual Queue", style=discord.ButtonStyle.blurple, row=0)
    async def pug_normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.queue_type = "individual"
        await self.show_queue_name_step(interaction)
    
    @discord.ui.button(label="Matchmaking", style=discord.ButtonStyle.blurple, row=1)
    async def matchmaking(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.queue_type = "matchmaking"
        await self.show_queue_name_step(interaction)
    
    @discord.ui.button(label="Full Team vs Full Team", style=discord.ButtonStyle.blurple, row=2)
    async def full_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.queue_type = "team_vs_team"
        await self.show_queue_name_step(interaction)
    
    @discord.ui.button(label="Select Team On Join", style=discord.ButtonStyle.blurple, row=3)
    async def select_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.queue_type = "select_team"
        await self.show_queue_name_step(interaction)
    
    async def show_queue_name_step(self, interaction: discord.Interaction):
        modal = QueueNameModal(self.queue_type)
        await interaction.response.send_modal(modal)


class QueueNameModal(discord.ui.Modal, title="Queue Name"):
    """Queue name input - Step 2"""
    
    queue_name_input = discord.ui.TextInput(
        label="What would you like this queue to be called?",
        placeholder="Examples: Rocket League, Valorant, Overwatch, etc",
        style=discord.TextStyle.short,
        required=True,
        max_length=50
    )
    
    def __init__(self, queue_type: str):
        super().__init__()
        self.queue_type = queue_type
    
    async def on_submit(self, interaction: discord.Interaction):
        queue_name = self.queue_name_input.value.strip()
        
        if not queue_name:
            await interaction.response.send_message("âŒ Queue name cannot be empty!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Queue Setup - Team Size",
            description=(
                f"**Queue Name:** {queue_name}\n\n"
                "Change in the future with `/setteamsize`\n\n"
                "**How many players should be on each team?**\n"
                "Examples: 2, 3, 4, 5, 6, etc\n\n"
                "Note: All stats are tied to the queue name!\n\n"
                "Setup will timeout in 5 minutes!"
            ),
            color=discord.Color.blue()
        )
        
        view = TeamSizeView(queue_name, self.queue_type)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class TeamSizeView(discord.ui.View):
    """Team size button - Step 3"""
    
    def __init__(self, queue_name: str, queue_type: str):
        super().__init__(timeout=300)
        self.queue_name = queue_name
        self.queue_type = queue_type
    
    @discord.ui.button(label="Enter Team Size", style=discord.ButtonStyle.green)
    async def enter_team_size(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TeamSizeModal(self.queue_name, self.queue_type)
        await interaction.response.send_modal(modal)


class TeamSizeModal(discord.ui.Modal, title="Team Size"):
    """Team size input - Final step"""
    
    team_size_input = discord.ui.TextInput(
        label="Team Size (players per team)",
        placeholder="Enter a number (1-20)",
        style=discord.TextStyle.short,
        required=True,
        max_length=2
    )
    
    def __init__(self, queue_name: str, queue_type: str):
        super().__init__()
        self.queue_name = queue_name
        self.queue_type = queue_type
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            team_size = int(self.team_size_input.value.strip())
            
            if team_size < 1 or team_size > 20:
                await interaction.response.send_message("âŒ Team size must be between 1 and 20!", ephemeral=True)
                return
            
            # Map queue type to team selection mode
            mode_map = {
                "individual": "balanced",
                "matchmaking": "balanced",
                "team_vs_team": "captain",
                "select_team": "manual"
            }
            team_mode = mode_map.get(self.queue_type, "balanced")
            
            # Create queue settings
            settings = {
                'guild_id': interaction.guild.id,
                'queue_name': self.queue_name,
                'team_size': team_size,
                'team_selection_mode': team_mode,
                'captain_mode': 'random',
                'required_role': None,
                'locked': 0,
                'results_channel': None,
                'auto_move': 0,
                'create_channels': 0,
                'channel_category': None,
                'map_voting': 0,
                'ping_players': 1,
                'sticky_message': 0,
                'name_type': 'discord',
                'mmr_decay_enabled': 0,
                'lobby_details_template': None,
                'game_mode': 'mix'
            }
            
            save_queue_settings(settings)
            log_command(interaction.guild.id, interaction.user.id, "setup", True)
            
            logger.info(f"Queue '{self.queue_name}' created in guild {interaction.guild.id}")
            
            # Launch the interactive post-setup wizard
            wizard = PostSetupWizard(self.queue_name, team_size, self.queue_type, team_mode)
            embed = wizard.build_step_embed()
            await interaction.response.edit_message(embed=embed, view=wizard)
            
        except ValueError:
            await interaction.response.send_message("âŒ Please enter a valid number!", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating queue: {e}", exc_info=True)
            await interaction.response.send_message(f"âŒ Error creating queue: {str(e)}", ephemeral=True)


# ============================================================================
# POST-SETUP WIZARD - Interactive step-by-step configuration
# ============================================================================

SETUP_STEPS = [
    {
        "title": "Step 1: Start Your Queue",
        "emoji": "ðŸš€",
        "description": (
            "Your queue **{queue_name}** has been created!\n\n"
            "**Queue Info:**\n"
            "â€¢ Name: `{queue_name}`\n"
            "â€¢ Size: `{team_size}v{team_size}`\n"
            "â€¢ Type: `{queue_type}`\n"
            "â€¢ Team Mode: `{team_mode}`\n\n"
            "**Run this command in the channel where you want the queue displayed:**\n"
            "`/startqueue {queue_name}`\n\n"
            "Click **Next** when you're ready to continue configuring, or **Finish** to stop here."
        ),
    },
    {
        "title": "Step 2: Set a Results Channel",
        "emoji": "ðŸ“¢",
        "description": (
            "Set a channel where match results will be posted after each game.\n\n"
            "**Run this command:**\n"
            "`/resultschannel {queue_name} #your-results-channel`\n\n"
            "This keeps your queue channel clean and gives you a dedicated log of all match outcomes.\n\n"
            "Click **Next** to continue or **Skip** if you don't need this."
        ),
    },
    {
        "title": "Step 3: Set Up Staff Roles",
        "emoji": "ðŸ›¡ï¸",
        "description": (
            "Grant staff permissions to specific roles so they can manage queues without needing full admin.\n\n"
            "**Run this command:**\n"
            "`/staffroles add @your-staff-role`\n\n"
            "Staff can report wins, cancel matches, add/remove players, blacklist users, and more.\n\n"
            "You can add multiple staff roles by running the command again."
        ),
    },
    {
        "title": "Step 4: Configure Team Selection",
        "emoji": "âš™ï¸",
        "description": (
            "Choose how teams are formed when a match starts.\n\n"
            "**Change team selection mode:**\n"
            "`/setteammode {queue_name} <mode>`\n"
            "Modes: `balanced` (MMR-based), `random`, `captain`, `manual`\n\n"
            "**If using captains, set captain selection:**\n"
            "`/setcaptainmode {queue_name} <mode>`\n"
            "Modes: `random`, `highest_mmr`, `volunteer`\n\n"
            "**Set custom team names:**\n"
            "`/setteamnames {queue_name} <team1> <team2>`"
        ),
    },
    {
        "title": "Step 5: Maps & Game Mode",
        "emoji": "ðŸ—ºï¸",
        "description": (
            "Set up maps and choose your game mode.\n\n"
            "**Add all default maps at once:**\n"
            "`/addmap {queue_name} all`\n"
            "Adds: Blackheart, Scar, Den, Exposure, Colossus\n\n"
            "**Or add maps individually:**\n"
            "`/addmap {queue_name} <map_name>`\n\n"
            "**Set the game mode:**\n"
            "`/setgamemode {queue_name} <mode>`\n"
            "ðŸ”¥ `hp` â€” Hardpoint only\n"
            "ðŸ’£ `snd` â€” Search & Destroy only\n"
            "ðŸ”„ `mix` â€” HP â†’ SND â†’ Overload rotation\n\n"
            "**Enable map voting (players vote on map):**\n"
            "`/setmapvoting {queue_name} true`\n\n"
            "**Remove a map:**\n"
            "`/removemap {queue_name} <map_name>`"
        ),
    },
    {
        "title": "Step 6: Voice Channel Settings (Optional)",
        "emoji": "ðŸ”Š",
        "description": (
            "Automatically manage voice channels for matches.\n\n"
            "**Auto-move players to voice when match starts:**\n"
            "`/automove {queue_name}`\n\n"
            "**Auto-create team voice channels:**\n"
            "`/createchannels {queue_name}`\n\n"
            "**Set the category for auto-created channels:**\n"
            "`/channelcategory {queue_name} <category_id>`\n\n"
            "Players must be in a voice channel for auto-move to work."
        ),
    },
    {
        "title": "Step 7: Required Roles & Blacklist (Optional)",
        "emoji": "ðŸ”’",
        "description": (
            "Control who can join the queue.\n\n"
            "**Require a role to join:**\n"
            "`/requiredrole add {queue_name} @role`\n\n"
            "**Blacklist a user from this queue:**\n"
            "`/blacklist add {queue_name} @user`\n\n"
            "**Limit how many players with a specific role can be in a match:**\n"
            "`/rolelimit {queue_name} @role <max_count>`\n\n"
            "This is useful for restricting smurfs, rank-gating, or balancing by role."
        ),
    },
    {
        "title": "Step 8: MMR & Ranks (Optional)",
        "emoji": "ðŸ“Š",
        "description": (
            "Set up automatic rank roles based on MMR thresholds.\n\n"
            "**Add a rank:**\n"
            "`/rankadd {queue_name} @role <mmr_threshold>`\n"
            "Example: `/rankadd ranked @Gold 1200`\n\n"
            "**View all ranks:**\n"
            "`/ranks {queue_name}`\n\n"
            "**Enable MMR decay for inactive players:**\n"
            "`/mmrdecay {queue_name}`\n\n"
            "**Give a user a grace period from decay:**\n"
            "`/graceperiod {queue_name} @user <days>`"
        ),
    },
    {
        "title": "Step 9: Display Settings (Optional)",
        "emoji": "ðŸŽ¨",
        "description": (
            "Fine-tune how the queue looks and behaves.\n\n"
            "**Toggle player pings when match starts:**\n"
            "`/pingplayers {queue_name}`\n\n"
            "**Change name display (Discord name vs server nickname):**\n"
            "`/nametype {queue_name} <discord/nickname>`\n\n"
            "**Enable sticky queue message (always stays at bottom):**\n"
            "`/stickymessage {queue_name}`\n\n"
            "**Set a lobby details template (shown when match starts):**\n"
            "`/lobbydetailsset {queue_name} <template>`\n"
            "Use `{{team1}}`, `{{team2}}`, `{{map}}` as placeholders."
        ),
    },
    {
        "title": "Step 10: Verification & Role Panels (Optional)",
        "emoji": "âœ…",
        "description": (
            "These are server-wide features (not queue-specific).\n\n"
            "**Set up a verification button:**\n"
            "`/verify @verified-role`\n"
            "Creates a verify button in the channel. Users click it to get the role.\n\n"
            "**Create a role selection panel:**\n"
            "`/rolepanel @role1 @role2 @role3`\n"
            "Users can pick roles from a button menu.\n\n"
            "**Create emoji reaction roles (Carl-bot style):**\n"
            "`/reactionrole create`\n"
            "Then add emoji-role pairs with `/reactionrole add`"
        ),
    },
]


class PostSetupWizard(discord.ui.View):
    """Interactive post-setup wizard that guides through all configuration steps"""
    
    def __init__(self, queue_name: str, team_size: int, queue_type: str, team_mode: str):
        super().__init__(timeout=600)  # 10 minute timeout
        self.queue_name = queue_name
        self.team_size = team_size
        self.queue_type = queue_type.replace("_", " ").title()
        self.team_mode = team_mode.title()
        self.current_step = 0
        self.total_steps = len(SETUP_STEPS)
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current step"""
        self.back_button.disabled = (self.current_step == 0)
        # On the last step, change Next to say "Finish"
        if self.current_step == self.total_steps - 1:
            self.next_button.label = "âœ… Finish Setup"
            self.next_button.style = discord.ButtonStyle.green
        else:
            self.next_button.label = "Next âž¡ï¸"
            self.next_button.style = discord.ButtonStyle.primary
    
    def _format_description(self, template: str) -> str:
        """Fill in queue-specific values in step descriptions"""
        return template.format(
            queue_name=self.queue_name,
            team_size=self.team_size,
            queue_type=self.queue_type,
            team_mode=self.team_mode
        )
    
    def build_step_embed(self) -> discord.Embed:
        """Build the embed for the current step"""
        step = SETUP_STEPS[self.current_step]
        
        embed = discord.Embed(
            title=f"{step['emoji']} Queue Setup â€” {step['title']}",
            description=self._format_description(step["description"]),
            color=discord.Color.blue() if self.current_step > 0 else discord.Color.green()
        )
        
        # Progress bar
        filled = self.current_step + 1
        bar = "â–ˆ" * filled + "â–‘" * (self.total_steps - filled)
        embed.set_footer(text=f"Step {filled}/{self.total_steps}  {bar}  â€¢  Setup will timeout in 10 minutes")
        
        return embed
    
    @discord.ui.button(label="â¬…ï¸ Back", style=discord.ButtonStyle.secondary, row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_step > 0:
            self.current_step -= 1
        self._update_buttons()
        embed = self.build_step_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Next âž¡ï¸", style=discord.ButtonStyle.primary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_step < self.total_steps - 1:
            self.current_step += 1
            self._update_buttons()
            embed = self.build_step_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # Final step â€” show completion summary
            embed = discord.Embed(
                title="ðŸŽ‰ Setup Complete!",
                description=(
                    f"**{self.queue_name}** is fully configured and ready to go!\n\n"
                    f"**Don't forget to run** `/startqueue {self.queue_name}` **in your queue channel!**\n\n"
                    "You can change any setting at any time using the commands shown in the steps.\n"
                    "Use `/help` to see all available commands."
                ),
                color=discord.Color.green()
            )
            embed.add_field(name="Queue Name", value=self.queue_name, inline=True)
            embed.add_field(name="Team Size", value=f"{self.team_size}v{self.team_size}", inline=True)
            embed.add_field(name="Queue Type", value=self.queue_type, inline=True)
            embed.add_field(name="Team Mode", value=self.team_mode, inline=True)
            embed.set_footer(text="JarvisQueue â€” Use /help for the full command list!")
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()
    
    @discord.ui.button(label="Skip â­ï¸", style=discord.ButtonStyle.secondary, row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip ahead to the next step (same as next but semantically different for optional steps)"""
        if self.current_step < self.total_steps - 1:
            self.current_step += 1
            self._update_buttons()
            embed = self.build_step_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # Same finish behavior
            await self.next_button.callback(interaction)
    
    @discord.ui.button(label="ðŸ Finish Now", style=discord.ButtonStyle.danger, row=0)
    async def finish_now_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """End setup early"""
        embed = discord.Embed(
            title="âœ… Queue Created Successfully!",
            description=(
                f"**{self.queue_name}** is ready to use!\n\n"
                f"**Run** `/startqueue {self.queue_name}` **in your queue channel to display it.**\n\n"
                "You can configure more settings anytime using the commands below.\n"
                "Use `/help` to see the full command list!"
            ),
            color=discord.Color.green()
        )
        embed.add_field(name="Queue Name", value=self.queue_name, inline=True)
        embed.add_field(name="Team Size", value=f"{self.team_size}v{self.team_size}", inline=True)
        embed.add_field(name="Queue Type", value=self.queue_type, inline=True)
        embed.add_field(
            name="âš¡ Quick Reference",
            value=(
                "`/resultschannel` - Set results channel\n"
                "`/staffroles add` - Add staff roles\n"
                "`/setteammode` - Change team selection\n"
                "`/setmapvoting` - Enable map voting\n"
                "`/automove` - Auto-move to voice\n"
                "`/rankadd` - Add MMR ranks\n"
                "`/verify` - Verification button\n"
                "`/rolepanel` - Role selection panel"
            ),
            inline=False
        )
        embed.set_footer(text="JarvisQueue â€” Use /help for the full command list!")
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


# ============================================================================
# QUEUE SETUP & MANAGEMENT COMMANDS
# ============================================================================

@bot.tree.command(name="setup", description="Create a new queue (Interactive Setup)")
@app_commands.default_permissions(manage_guild=True)  # Only admins can see this command
async def setup(interaction: discord.Interaction):
    """Interactive queue setup with step-by-step guidance"""
    try:
        embed = discord.Embed(
            title="ðŸŽ® Queue Setup - Step 1: Queue Type",
            description=(
                "**PUGs/Normal Individual Queue:**\n"
                "The default queue setup, players join individually to get put into a match when the queue is filled.\n\n"
                "**Matchmaking:**\n"
                "Players join the queue, and once there are enough players within their MMR range, "
                "a match is created.\n\n"
                "**Full Team vs Full Team:**\n"
                "Captains join the queue and pull in the entire team. No team setup is required.\n\n"
                "**Select Team On Join:**\n"
                "The queue has join buttons for each team, no team setup is required.\n\n"
                "Setup will timeout in 5 minutes!"
            ),
            color=discord.Color.blue()
        )
        
        view = QueueTypeView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in setup command: {e}", exc_info=True)
        await interaction.response.send_message(f"âŒ Error starting setup: {str(e)}", ephemeral=True)

@bot.tree.command(name="startqueue", description="Display queue interface")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(queue_name="Name of the queue")
async def startqueue(interaction: discord.Interaction, queue_name: str = "default"):
    """Display interactive queue interface"""
    try:
        await interaction.response.defer()
        
        settings = get_queue_settings(interaction.guild.id, queue_name)
        queue = get_queue(interaction.guild.id, queue_name)
        
        # NeatQueue style embed
        # Show the actual queue name exactly as it was entered
        queue_display_name = queue_name if queue_name != "default" else "Queue"
        
        embed = discord.Embed(
            title=queue_display_name,
            color=0xed4245  # Discord red color for left border
        )
        
        # Build description - shorter box with less padding
        description_parts = []
        description_parts.append(f"**Queue {len(queue)}/{settings['team_size']*2}**")
        description_parts.append("")  # Empty line for spacing
        
        # Show players in queue with mentions
        if queue:
            for user_id in queue:
                member = interaction.guild.get_member(user_id)
                if member:
                    description_parts.append(f"{member.mention}")
        else:
            description_parts.append("*No players in queue*")
        
        # Add moderate padding to keep box visible but shorter (3-5 lines instead of 10)
        padding_lines = max(0, 5 - len(queue))
        for _ in range(padding_lines):
            description_parts.append("")
        
        # Add timestamp - Discord format automatically adjusts to user's timezone
        timestamp = f"<t:{int(datetime.now().timestamp())}:t>"  # Shows time in user's local timezone
        description_parts.append(timestamp)
        
        embed.description = "\n".join(description_parts)
        
        view = QueueView(queue_name)
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message  # Store message reference for sticky updates
        
        # If sticky message is enabled, track this message
        if settings.get('sticky_message', 0):
            sticky_queue_messages[interaction.channel.id] = {
                'message': message,
                'view': view,
                'queue_name': queue_name,
                'guild_id': interaction.guild.id
            }
            logger.info(f"Sticky queue registered for channel {interaction.channel.id}")
        
        log_command(interaction.guild.id, interaction.user.id, "startqueue", True)
        
    except Exception as e:
        logger.error(f"Error in startqueue command: {e}", exc_info=True)
        log_command(interaction.guild.id, interaction.user.id, "startqueue", False)
        await interaction.followup.send(f"âŒ Error: {str(e)}")

@bot.tree.command(name="clearqueue", description="Clear all players from queue")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(queue_name="Name of the queue")
async def clearqueue(interaction: discord.Interaction, queue_name: str = "default"):
    """Clear all players from queue"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    queue = get_queue(interaction.guild.id, queue_name)
    count = len(queue)
    queue.clear()
    
    await interaction.response.send_message(f"âœ… Cleared {count} player(s) from queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "clearqueue", True)

@bot.tree.command(name="lockqueue", description="Lock the queue")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(queue_name="Name of the queue")
async def lockqueue(interaction: discord.Interaction, queue_name: str = "default"):
    """Lock queue to prevent new joins"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['locked'] = 1
    save_queue_settings(settings)
    
    await interaction.response.send_message(f"ðŸ”’ Queue **{queue_name}** locked!")
    log_command(interaction.guild.id, interaction.user.id, "lockqueue", True)

@bot.tree.command(name="unlockqueue", description="Unlock the queue")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(queue_name="Name of the queue")
async def unlockqueue(interaction: discord.Interaction, queue_name: str = "default"):
    """Unlock queue to allow new joins"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['locked'] = 0
    save_queue_settings(settings)
    
    await interaction.response.send_message(f"ðŸ”“ Queue **{queue_name}** unlocked!")
    log_command(interaction.guild.id, interaction.user.id, "unlockqueue", True)

@bot.tree.command(name="purge", description="Delete all messages except queue message")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(limit="Number of messages to check (max 100)")
async def purge(interaction: discord.Interaction, limit: int = 50):
    """Purge channel messages except queue interface"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        deleted = 0
        async for message in interaction.channel.history(limit=min(limit, 100)):
            # Don't delete queue messages (messages with QueueView)
            if message.author == bot.user and message.components:
                continue
            try:
                await message.delete()
                deleted += 1
            except:
                pass
        
        await interaction.followup.send(f"âœ… Deleted {deleted} message(s)!")
        log_command(interaction.guild.id, interaction.user.id, "purge", True)
    except Exception as e:
        await interaction.followup.send(f"âŒ Error: {str(e)}")
        log_command(interaction.guild.id, interaction.user.id, "purge", False)

@bot.tree.command(name="removeuser", description="Remove a user from the queue")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="User to remove", queue_name="Queue name")
async def removeuser(interaction: discord.Interaction, user: discord.Member, queue_name: str = "default"):
    """Remove specific user from queue"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    queue = get_queue(interaction.guild.id, queue_name)
    
    if user.id not in queue:
        await interaction.response.send_message(f"âŒ {user.mention} is not in the queue!", ephemeral=True)
        return
    
    queue.remove(user.id)
    await interaction.response.send_message(f"âœ… Removed {user.mention} from queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "removeuser", True)

@bot.tree.command(name="adduser", description="Add a user to the queue")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="User to add", queue_name="Queue name")
async def adduser(interaction: discord.Interaction, user: discord.Member, queue_name: str = "default"):
    """Add specific user to queue"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    queue = get_queue(interaction.guild.id, queue_name)
    settings = get_queue_settings(interaction.guild.id, queue_name)
    
    if user.id in queue:
        await interaction.response.send_message(f"âŒ {user.mention} is already in the queue!", ephemeral=True)
        return
    
    if len(queue) >= settings['team_size'] * 2:
        await interaction.response.send_message(f"âŒ Queue is full!", ephemeral=True)
        return
    
    queue.append(user.id)
    get_or_create_player(user.id, user.name)
    
    await interaction.response.send_message(f"âœ… Added {user.mention} to queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "adduser", True)

# ============================================================================
# TEAM & MATCH CONFIGURATION COMMANDS
# ============================================================================

@bot.tree.command(name="setteamsize", description="Set team size")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(size="Players per team (1-20)", queue_name="Queue name")
async def setteamsize(interaction: discord.Interaction, size: int, queue_name: str = "default"):
    """Set number of players per team"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    if size < 1 or size > 20:
        await interaction.response.send_message("âŒ Team size must be between 1 and 20!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['team_size'] = size
    save_queue_settings(settings)
    
    await interaction.response.send_message(f"âœ… Set team size to {size} for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "setteamsize", True)

@bot.tree.command(name="setteammode", description="Set team selection mode")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    mode="Team selection method",
    queue_name="Queue name"
)
@app_commands.choices(mode=[
    app_commands.Choice(name="Balanced (by MMR)", value="balanced"),
    app_commands.Choice(name="Random", value="random"),
    app_commands.Choice(name="Captains", value="captains"),
    app_commands.Choice(name="Unfair (intentionally unbalanced)", value="unfair")
])
async def setteammode(interaction: discord.Interaction, mode: str, queue_name: str = "default"):
    """Set team selection mode"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['team_selection_mode'] = mode
    save_queue_settings(settings)
    
    await interaction.response.send_message(f"âœ… Set team mode to **{mode}** for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "setteammode", True)

@bot.tree.command(name="setcaptainmode", description="Set captain selection mode")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(mode="How to choose captains", queue_name="Queue name")
@app_commands.choices(mode=[
    app_commands.Choice(name="Random", value="random"),
    app_commands.Choice(name="Highest MMR", value="highest"),
    app_commands.Choice(name="Lowest MMR", value="lowest")
])
async def setcaptainmode(interaction: discord.Interaction, mode: str, queue_name: str = "default"):
    """Set how captains are chosen"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['captain_mode'] = mode
    save_queue_settings(settings)
    
    await interaction.response.send_message(f"âœ… Set captain mode to **{mode}** for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "setcaptainmode", True)

@bot.tree.command(name="setteamnames", description="Set custom names for Team 1 and Team 2")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    team1_name="Name for Team 1 (e.g., 'Red Team', 'Attackers', 'Alpha')",
    team2_name="Name for Team 2 (e.g., 'Blue Team', 'Defenders', 'Bravo')",
    queue_name="Queue name (default: default)"
)
async def setteamnames(
    interaction: discord.Interaction,
    team1_name: str,
    team2_name: str,
    queue_name: str = "default"
):
    """Set custom team names for a queue"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    try:
        settings = get_queue_settings(interaction.guild.id, queue_name)
        
        # Check if queue exists
        if settings['guild_id'] == 0:  # Default settings means queue doesn't exist
            await interaction.response.send_message(
                f"âŒ Queue '{queue_name}' doesn't exist! Create it first with `/setup`",
                ephemeral=True
            )
            return
        
        # Update team names
        settings['team1_name'] = team1_name
        settings['team2_name'] = team2_name
        save_queue_settings(settings)
        
        embed = discord.Embed(
            title="âœ… Team Names Updated!",
            description=f"Queue: **{queue_name}**",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Team 1 Name",
            value=f"ðŸ”µ **{team1_name}**",
            inline=True
        )
        
        embed.add_field(
            name="Team 2 Name",
            value=f"ðŸ”´ **{team2_name}**",
            inline=True
        )
        
        embed.set_footer(text="These names will be used in voice channels and match announcements!")
        
        await interaction.response.send_message(embed=embed)
        log_command(interaction.guild.id, interaction.user.id, "setteamnames", True)
        logger.info(f"Team names set for {queue_name}: {team1_name} vs {team2_name}")
        
    except Exception as e:
        logger.error(f"Error setting team names: {e}", exc_info=True)
        await interaction.response.send_message(f"âŒ Error: {str(e)}", ephemeral=True)

@bot.tree.command(name="setmapvoting", description="Enable/disable map voting")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(enabled="Enable or disable", queue_name="Queue name")
async def setmapvoting(interaction: discord.Interaction, enabled: bool, queue_name: str = "default"):
    """Toggle map voting"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['map_voting'] = 1 if enabled else 0
    save_queue_settings(settings)
    
    status = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"âœ… Map voting {status} for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "setmapvoting", True)

# Default map pool
DEFAULT_MAPS = ["Blackheart", "Scar", "Den", "Exposure", "Colossus"]

# Game mode map assignments for MIX rotation
GAME_MODE_ORDER = ["HP", "SND", "Overload"]

@bot.tree.command(name="addmap", description="Add a map to the map pool")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(map_name="Select a map or 'All Maps' to add all at once", queue_name="Queue name")
@app_commands.choices(map_name=[
    app_commands.Choice(name="âœ… All Maps (Blackheart, Scar, Den, Exposure, Colossus)", value="all"),
    app_commands.Choice(name="Blackheart", value="Blackheart"),
    app_commands.Choice(name="Scar", value="Scar"),
    app_commands.Choice(name="Den", value="Den"),
    app_commands.Choice(name="Exposure", value="Exposure"),
    app_commands.Choice(name="Colossus", value="Colossus"),
])
async def addmap(interaction: discord.Interaction, map_name: str, queue_name: str = "default"):
    """Add map to voting pool"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        if map_name == "all":
            added = []
            for m in DEFAULT_MAPS:
                c.execute('INSERT OR IGNORE INTO maps (guild_id, queue_name, map_name, game_mode) VALUES (?, ?, ?, ?)',
                          (interaction.guild.id, queue_name, m, 'all'))
                added.append(m)
            conn.commit()
            conn.close()
            
            map_list = ", ".join(f"**{m}**" for m in added)
            await interaction.response.send_message(
                f"âœ… Added all default maps to queue **{queue_name}**!\n"
                f"Maps: {map_list}"
            )
        else:
            c.execute('INSERT OR IGNORE INTO maps (guild_id, queue_name, map_name, game_mode) VALUES (?, ?, ?, ?)',
                      (interaction.guild.id, queue_name, map_name, 'all'))
            conn.commit()
            conn.close()
            
            await interaction.response.send_message(f"âœ… Added map **{map_name}** to queue **{queue_name}**!")
        
        log_command(interaction.guild.id, interaction.user.id, "addmap", True)
    except Exception as e:
        await interaction.response.send_message(f"âŒ Error: {str(e)}")
        log_command(interaction.guild.id, interaction.user.id, "addmap", False)

@bot.tree.command(name="removemap", description="Remove a map from the map pool")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(map_name="Name of the map", queue_name="Queue name")
async def removemap(interaction: discord.Interaction, map_name: str, queue_name: str = "default"):
    """Remove map from voting pool"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('DELETE FROM maps WHERE guild_id=? AND queue_name=? AND map_name=?',
                  (interaction.guild.id, queue_name, map_name))
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(f"âœ… Removed map **{map_name}** from queue **{queue_name}**!")
        log_command(interaction.guild.id, interaction.user.id, "removemap", True)
    except Exception as e:
        await interaction.response.send_message(f"âŒ Error: {str(e)}")
        log_command(interaction.guild.id, interaction.user.id, "removemap", False)


@bot.tree.command(name="setgamemode", description="Set game mode: HP only, SND only, or MIX (HPâ†’SNDâ†’Overload rotation)")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(mode="Game mode for the queue", queue_name="Queue name")
@app_commands.choices(mode=[
    app_commands.Choice(name="HP Only - Hardpoint maps only", value="hp"),
    app_commands.Choice(name="SND Only - Search & Destroy maps only", value="snd"),
    app_commands.Choice(name="MIX - HP, SND, Overload rotation", value="mix")
])
async def setgamemode(interaction: discord.Interaction, mode: str, queue_name: str = "default"):
    """Set the game mode for a queue"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['game_mode'] = mode
    save_queue_settings(settings)
    
    mode_descriptions = {
        'hp': 'ðŸ”¥ **HP Only** â€” All matches will be Hardpoint',
        'snd': 'ðŸ’£ **SND Only** â€” All matches will be Search & Destroy',
        'mix': 'ðŸ”„ **MIX** â€” Maps played in rotation: HP â†’ SND â†’ Overload â†’ HP...'
    }
    
    await interaction.response.send_message(
        f"âœ… Game mode set for queue **{queue_name}**!\n"
        f"{mode_descriptions[mode]}"
    )
    log_command(interaction.guild.id, interaction.user.id, "setgamemode", True)


# ============================================================================
# ROLE & PERMISSION COMMANDS
# ============================================================================

@bot.tree.command(name="requiredrole", description="Manage required roles for queue")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    action="Add or remove role",
    role="Discord role",
    queue_name="Queue name"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove")
])
async def requiredrole(interaction: discord.Interaction, action: str, role: discord.Role, queue_name: str = "default"):
    """Manage required roles"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if action == "add":
        c.execute('INSERT OR IGNORE INTO required_roles VALUES (?, ?, ?)',
                  (interaction.guild.id, queue_name, role.id))
        msg = f"âœ… Added required role {role.mention} to queue **{queue_name}**!"
    else:
        c.execute('DELETE FROM required_roles WHERE guild_id=? AND queue_name=? AND role_id=?',
                  (interaction.guild.id, queue_name, role.id))
        msg = f"âœ… Removed required role {role.mention} from queue **{queue_name}**!"
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(msg)
    log_command(interaction.guild.id, interaction.user.id, "requiredrole", True)

@bot.tree.command(name="blacklist", description="Manage user blacklist")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    action="Add or remove from blacklist",
    user="User to blacklist",
    queue_name="Queue name",
    reason="Reason for blacklist"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove")
])
async def blacklist(interaction: discord.Interaction, action: str, user: discord.Member, queue_name: str = "default", reason: str = "No reason provided"):
    """Blacklist/unblacklist users"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if action == "add":
        c.execute('INSERT OR REPLACE INTO blacklist VALUES (?, ?, ?, ?, ?, ?)',
                  (interaction.guild.id, queue_name, user.id, reason, 
                   datetime.now().isoformat(), interaction.user.id))
        msg = f"âœ… Blacklisted {user.mention} from queue **{queue_name}**!\nReason: {reason}"
        
        # Remove from queue if currently in it
        queue = get_queue(interaction.guild.id, queue_name)
        if user.id in queue:
            queue.remove(user.id)
    else:
        c.execute('DELETE FROM blacklist WHERE guild_id=? AND queue_name=? AND user_id=?',
                  (interaction.guild.id, queue_name, user.id))
        msg = f"âœ… Removed {user.mention} from blacklist for queue **{queue_name}**!"
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(msg)
    log_command(interaction.guild.id, interaction.user.id, "blacklist", True)

@bot.tree.command(name="staffroles", description="Manage staff roles")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(action="Add or remove", role="Discord role")
@app_commands.choices(action=[
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove")
])
async def staffroles(interaction: discord.Interaction, action: str, role: discord.Role):
    """Manage staff roles"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if action == "add":
        c.execute('INSERT OR IGNORE INTO staff_roles VALUES (?, ?)',
                  (interaction.guild.id, role.id))
        msg = f"âœ… Added {role.mention} as staff role!"
    else:
        c.execute('DELETE FROM staff_roles WHERE guild_id=? AND role_id=?',
                  (interaction.guild.id, role.id))
        msg = f"âœ… Removed {role.mention} from staff roles!"
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(msg)
    log_command(interaction.guild.id, interaction.user.id, "staffroles", True)

# ============================================================================
# CHANNEL & AUTOMATION COMMANDS
# ============================================================================

@bot.tree.command(name="resultschannel", description="Set results channel")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    action="Set or remove",
    channel="Channel for match results",
    queue_name="Queue name"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Set", value="set"),
    app_commands.Choice(name="Remove", value="remove")
])
async def resultschannel(interaction: discord.Interaction, action: str, channel: Optional[discord.TextChannel] = None, queue_name: str = "default"):
    """Set results announcement channel"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    
    if action == "set":
        if not channel:
            await interaction.response.send_message("âŒ Must specify a channel!", ephemeral=True)
            return
        settings['results_channel'] = channel.id
        msg = f"âœ… Set results channel to {channel.mention} for queue **{queue_name}**!"
    else:
        settings['results_channel'] = None
        msg = f"âœ… Removed results channel for queue **{queue_name}**!"
    
    save_queue_settings(settings)
    await interaction.response.send_message(msg)
    log_command(interaction.guild.id, interaction.user.id, "resultschannel", True)

@bot.tree.command(name="automove", description="Toggle auto-move players to voice channels")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(enabled="Enable or disable", queue_name="Queue name")
async def automove(interaction: discord.Interaction, enabled: bool, queue_name: str = "default"):
    """Auto-move players to team voice channels"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['auto_move'] = 1 if enabled else 0
    save_queue_settings(settings)
    
    status = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"âœ… Auto-move {status} for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "automove", True)

@bot.tree.command(name="createchannels", description="Auto-create team voice channels")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(enabled="Enable or disable", queue_name="Queue name")
async def createchannels(interaction: discord.Interaction, enabled: bool, queue_name: str = "default"):
    """Toggle auto-creation of team channels"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['create_channels'] = 1 if enabled else 0
    save_queue_settings(settings)
    
    status = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"âœ… Auto-create channels {status} for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "createchannels", True)

@bot.tree.command(name="channelcategory", description="Set category for team channels")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(category="Category for voice channels", queue_name="Queue name")
async def channelcategory(interaction: discord.Interaction, category: discord.CategoryChannel, queue_name: str = "default"):
    """Set category for auto-created channels"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['channel_category'] = category.id
    save_queue_settings(settings)
    
    await interaction.response.send_message(f"âœ… Team channels will be created in **{category.name}** for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "channelcategory", True)

@bot.tree.command(name="pingplayers", description="Toggle player mentions in match start")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(enabled="Enable or disable", queue_name="Queue name")
async def pingplayers(interaction: discord.Interaction, enabled: bool, queue_name: str = "default"):
    """Toggle pinging players when match starts"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['ping_players'] = 1 if enabled else 0
    save_queue_settings(settings)
    
    status = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"âœ… Player pings {status} for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "pingplayers", True)

@bot.tree.command(name="nametype", description="Set name display type")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(name_type="Use Discord names or server nicknames", queue_name="Queue name")
@app_commands.choices(name_type=[
    app_commands.Choice(name="Discord Names", value="discord"),
    app_commands.Choice(name="Server Nicknames", value="nicknames")
])
async def nametype(interaction: discord.Interaction, name_type: str, queue_name: str = "default"):
    """Set how names are displayed"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['name_type'] = name_type
    save_queue_settings(settings)
    
    display = "Discord names" if name_type == "discord" else "server nicknames"
    await interaction.response.send_message(f"âœ… Will use {display} for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "nametype", True)

@bot.tree.command(name="stickymessage", description="Toggle sticky queue message (stays at bottom)")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(enabled="Enable or disable", queue_name="Queue name")
async def stickymessage(interaction: discord.Interaction, enabled: bool, queue_name: str = "default"):
    """Toggle sticky message - queue stays at bottom of channel"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['sticky_message'] = 1 if enabled else 0
    save_queue_settings(settings)
    
    if enabled:
        # Try to find the existing queue message in this channel and register sticky tracking
        found = False
        async for msg in interaction.channel.history(limit=50):
            if msg.author.id == bot.user.id and msg.embeds:
                embed = msg.embeds[0]
                display_name = queue_name if queue_name != "default" else "Queue"
                if embed.title and embed.title == display_name:
                    # Found the queue message â€” register sticky tracking
                    view = QueueView(queue_name)
                    view.message = msg
                    sticky_queue_messages[interaction.channel.id] = {
                        'message': msg,
                        'view': view,
                        'queue_name': queue_name,
                        'guild_id': interaction.guild.id
                    }
                    found = True
                    break
        
        if found:
            await interaction.response.send_message(
                f"âœ… Sticky message enabled for queue **{queue_name}**!\n"
                f"The queue will now stay at the bottom of the channel."
            )
        else:
            await interaction.response.send_message(
                f"âœ… Sticky message enabled for queue **{queue_name}**!\n"
                f"Run `/startqueue {queue_name}` in this channel to activate it."
            )
    else:
        # Remove from sticky tracking
        if interaction.channel.id in sticky_queue_messages:
            del sticky_queue_messages[interaction.channel.id]
        
        await interaction.response.send_message(
            f"âœ… Sticky message disabled for queue **{queue_name}**!\n"
            f"The queue will no longer move to the bottom."
        )
    
    log_command(interaction.guild.id, interaction.user.id, "stickymessage", True)

# ============================================================================
# MATCH RESULT COMMANDS
# ============================================================================

@bot.tree.command(name="reportwin", description="Staff override: force report match winner (bypasses voting)")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(team="Winning team (1 or 2)", queue_name="Queue name")
@app_commands.choices(team=[
    app_commands.Choice(name="Team 1", value=1),
    app_commands.Choice(name="Team 2", value=2)
])
async def reportwin(interaction: discord.Interaction, team: int, queue_name: str = "default"):
    """Staff override to force-report match winner, bypassing the vote system"""
    try:
        await interaction.response.defer()
        
        # Check if there's an active match
        if interaction.guild.id not in active_matches or queue_name not in active_matches[interaction.guild.id]:
            await interaction.followup.send("âŒ No active match for this queue!")
            return
        
        match_data = active_matches[interaction.guild.id][queue_name]
        match_id = match_data['match_id']
        team1 = match_data['team1']
        team2 = match_data['team2']
        
        # Check permissions - must be staff or in the match
        is_staff = is_user_staff(interaction.guild, interaction.user)
        is_participant = interaction.user.id in team1 or interaction.user.id in team2
        
        if not (is_staff or is_participant):
            await interaction.followup.send("âŒ Only staff or match participants can report results!")
            return
        
        # Calculate MMR changes
        winner_team = team1 if team == 1 else team2
        loser_team = team2 if team == 1 else team1
        
        # Simple MMR: +25 for win, -25 for loss
        mmr_change = 25
        
        # Update player stats
        for user_id in winner_team:
            update_player_stats(user_id, interaction.guild.id, queue_name, mmr_change, True)
            # Apply rank roles
            stats = get_queue_player_stats(user_id, interaction.guild.id, queue_name)
            apply_mmr_ranks(interaction.guild, user_id, queue_name, stats['mmr'])
        
        for user_id in loser_team:
            update_player_stats(user_id, interaction.guild.id, queue_name, -mmr_change, False)
            # Apply rank roles
            stats = get_queue_player_stats(user_id, interaction.guild.id, queue_name)
            apply_mmr_ranks(interaction.guild, user_id, queue_name, stats['mmr'])
        
        # Update match in database
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('UPDATE matches SET winner=?, mmr_change=? WHERE match_id=?',
                  (team, mmr_change, match_id))
        conn.commit()
        conn.close()
        
        # Create result embed
        embed = discord.Embed(
            title="ðŸ† Match Result",
            description=f"Queue: **{queue_name}**",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        winner_names = [interaction.guild.get_member(uid).mention for uid in winner_team if interaction.guild.get_member(uid)]
        loser_names = [interaction.guild.get_member(uid).mention for uid in loser_team if interaction.guild.get_member(uid)]
        
        embed.add_field(
            name=f"ðŸ¥‡ Winners - Team {team}",
            value="\n".join(winner_names),
            inline=True
        )
        embed.add_field(
            name=f"Losers - Team {3-team}",
            value="\n".join(loser_names),
            inline=True
        )
        embed.add_field(
            name="MMR Change",
            value=f"+{mmr_change} / -{mmr_change}",
            inline=False
        )
        
        # Send to results channel
        settings = get_queue_settings(interaction.guild.id, queue_name)
        if settings['results_channel']:
            channel = interaction.guild.get_channel(settings['results_channel'])
            if channel:
                await channel.send(embed=embed)
        
        await interaction.followup.send(embed=embed)
        
        # Clear active match
        del active_matches[interaction.guild.id][queue_name]
        
        log_command(interaction.guild.id, interaction.user.id, "reportwin", True)
        
    except Exception as e:
        logger.error(f"Error reporting win: {e}", exc_info=True)
        await interaction.followup.send(f"âŒ Error: {str(e)}")
        log_command(interaction.guild.id, interaction.user.id, "reportwin", False)

@bot.tree.command(name="cancelmatch", description="Cancel current match (no MMR changes)")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(queue_name="Queue name")
async def cancelmatch(interaction: discord.Interaction, queue_name: str = "default"):
    """Cancel match without MMR changes"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    if interaction.guild.id not in active_matches or queue_name not in active_matches[interaction.guild.id]:
        await interaction.response.send_message("âŒ No active match for this queue!", ephemeral=True)
        return
    
    match_data = active_matches[interaction.guild.id][queue_name]
    match_id = match_data['match_id']
    
    # Mark as cancelled in database
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE matches SET cancelled=1 WHERE match_id=?', (match_id,))
    conn.commit()
    conn.close()
    
    # Clear active match
    del active_matches[interaction.guild.id][queue_name]
    
    await interaction.response.send_message(f"âœ… Match cancelled for queue **{queue_name}**! No MMR changes.")
    log_command(interaction.guild.id, interaction.user.id, "cancelmatch", True)

@bot.tree.command(name="matchhistory", description="View recent match history")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(limit="Number of matches to show", queue_name="Queue name")
async def matchhistory(interaction: discord.Interaction, limit: int = 10, queue_name: str = "default"):
    """View match history"""
    await interaction.response.defer()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT match_id, timestamp, team1, team2, winner, mmr_change, match_number 
                 FROM matches 
                 WHERE guild_id=? AND queue_name=? AND cancelled=0 
                 ORDER BY match_id DESC LIMIT ?''',
              (interaction.guild.id, queue_name, min(limit, 25)))
    matches = c.fetchall()
    conn.close()
    
    if not matches:
        await interaction.followup.send(f"âŒ No match history for queue **{queue_name}**!")
        return
    
    embed = discord.Embed(
        title=f"ðŸ“œ Match History - {queue_name}",
        color=discord.Color.blue()
    )
    
    for match in matches[:10]:  # Show max 10 in embed
        match_id, timestamp, team1, team2, winner, mmr_change, match_number = match
        result = f"Team {winner} won (+{mmr_change}/-{mmr_change} MMR)" if winner else "In Progress"
        time_str = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M")
        embed.add_field(
            name=f"Match #{match_number}",
            value=f"{time_str}\n{result}",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)
    log_command(interaction.guild.id, interaction.user.id, "matchhistory", True)


# ============================================================================
# STATS & LEADERBOARD COMMANDS
# ============================================================================

@bot.tree.command(name="stats", description="View player statistics")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="User to check", queue_name="Specific queue (optional)")
async def stats(interaction: discord.Interaction, user: Optional[discord.Member] = None, queue_name: Optional[str] = None):
    """Display player statistics"""
    target_user = user or interaction.user
    
    if queue_name:
        # Queue-specific stats
        stats = get_queue_player_stats(target_user.id, interaction.guild.id, queue_name)
        winrate = (stats['wins'] / stats['games_played'] * 100) if stats['games_played'] > 0 else 0
        
        embed = discord.Embed(
            title=f"ðŸ“Š Stats for {target_user.name}",
            description=f"Queue: **{queue_name}**",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="MMR", value=stats['mmr'], inline=True)
        embed.add_field(name="Wins", value=stats['wins'], inline=True)
        embed.add_field(name="Losses", value=stats['losses'], inline=True)
        embed.add_field(name="Games Played", value=stats['games_played'], inline=True)
        embed.add_field(name="Win Rate", value=f"{winrate:.1f}%", inline=True)
    else:
        # Global stats
        player = get_or_create_player(target_user.id, target_user.name)
        winrate = (player['wins'] / player['total_games'] * 100) if player['total_games'] > 0 else 0
        
        embed = discord.Embed(
            title=f"ðŸ“Š Global Stats for {target_user.name}",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="MMR", value=player['mmr'], inline=True)
        embed.add_field(name="Highest MMR", value=player['highest_mmr'], inline=True)
        embed.add_field(name="Win Streak", value=player['win_streak'], inline=True)
        embed.add_field(name="Wins", value=player['wins'], inline=True)
        embed.add_field(name="Losses", value=player['losses'], inline=True)
        embed.add_field(name="Total Games", value=player['total_games'], inline=True)
        embed.add_field(name="Win Rate", value=f"{winrate:.1f}%", inline=True)
        
        if player['join_date']:
            embed.set_footer(text=f"Player since {player['join_date'][:10]}")
    
    await interaction.response.send_message(embed=embed)
    log_command(interaction.guild.id, interaction.user.id, "stats", True)

@bot.tree.command(name="leaderboard", description="View the leaderboard")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(limit="Number of players", queue_name="Specific queue (optional)")
async def leaderboard(interaction: discord.Interaction, limit: int = 10, queue_name: Optional[str] = None):
    """Display leaderboard"""
    await interaction.response.defer()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if queue_name:
        # Queue-specific leaderboard
        c.execute('''SELECT user_id, mmr, wins, losses, games_played 
                     FROM queue_stats 
                     WHERE guild_id=? AND queue_name=? 
                     ORDER BY mmr DESC LIMIT ?''',
                  (interaction.guild.id, queue_name, min(limit, 25)))
        title = f"ðŸ† Leaderboard - {queue_name}"
    else:
        # Global leaderboard
        c.execute('SELECT user_id, username, mmr, wins, losses FROM players ORDER BY mmr DESC LIMIT ?',
                  (min(limit, 25),))
        title = "ðŸ† Global Leaderboard"
    
    results = c.fetchall()
    conn.close()
    
    if not results:
        await interaction.followup.send("âŒ No players found!")
        return
    
    embed = discord.Embed(title=title, color=discord.Color.gold())
    
    leaderboard_text = ""
    for i, result in enumerate(results, 1):
        if queue_name:
            user_id, mmr, wins, losses, games = result
            member = interaction.guild.get_member(user_id)
            name = member.name if member else f"User {user_id}"
            winrate = (wins / games * 100) if games > 0 else 0
        else:
            user_id, username, mmr, wins, losses = result
            name = username
            total = wins + losses
            winrate = (wins / total * 100) if total > 0 else 0
        
        medal = "ðŸ¥‡" if i == 1 else "ðŸ¥ˆ" if i == 2 else "ðŸ¥‰" if i == 3 else f"`{i}.`"
        leaderboard_text += f"{medal} **{name}** - {mmr} MMR ({wins}W/{losses}L - {winrate:.1f}%)\n"
    
    embed.description = leaderboard_text
    await interaction.followup.send(embed=embed)
    log_command(interaction.guild.id, interaction.user.id, "leaderboard", True)

@bot.tree.command(name="rank", description="View your rank position")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="User to check", queue_name="Specific queue (optional)")
async def rank(interaction: discord.Interaction, user: Optional[discord.Member] = None, queue_name: Optional[str] = None):
    """Show player's rank position"""
    target_user = user or interaction.user
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if queue_name:
        c.execute('''SELECT COUNT(*) + 1 FROM queue_stats 
                     WHERE guild_id=? AND queue_name=? AND mmr > (
                         SELECT mmr FROM queue_stats 
                         WHERE guild_id=? AND queue_name=? AND user_id=?
                     )''',
                  (interaction.guild.id, queue_name, interaction.guild.id, queue_name, target_user.id))
        rank_pos = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM queue_stats WHERE guild_id=? AND queue_name=?',
                  (interaction.guild.id, queue_name))
        total = c.fetchone()[0]
        
        stats = get_queue_player_stats(target_user.id, interaction.guild.id, queue_name)
        mmr = stats['mmr']
        title = f"Rank in {queue_name}"
    else:
        c.execute('''SELECT COUNT(*) + 1 FROM players WHERE mmr > (
                         SELECT mmr FROM players WHERE user_id=?
                     )''', (target_user.id,))
        rank_pos = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM players')
        total = c.fetchone()[0]
        
        player = get_or_create_player(target_user.id, target_user.name)
        mmr = player['mmr']
        title = "Global Rank"
    
    conn.close()
    
    percentile = (1 - (rank_pos / total)) * 100 if total > 0 else 0
    
    embed = discord.Embed(
        title=f"ðŸ“ˆ {title}",
        description=f"**{target_user.name}**",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Rank", value=f"#{rank_pos} / {total}", inline=True)
    embed.add_field(name="MMR", value=mmr, inline=True)
    embed.add_field(name="Percentile", value=f"Top {100-percentile:.1f}%", inline=True)
    
    await interaction.response.send_message(embed=embed)
    log_command(interaction.guild.id, interaction.user.id, "rank", True)

@bot.tree.command(name="compare", description="Compare two players")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user1="First player", user2="Second player", queue_name="Specific queue (optional)")
async def compare(interaction: discord.Interaction, user1: discord.Member, user2: discord.Member, queue_name: Optional[str] = None):
    """Compare stats between two players"""
    if queue_name:
        stats1 = get_queue_player_stats(user1.id, interaction.guild.id, queue_name)
        stats2 = get_queue_player_stats(user2.id, interaction.guild.id, queue_name)
        
        embed = discord.Embed(
            title=f"âš”ï¸ Player Comparison - {queue_name}",
            color=discord.Color.purple()
        )
        
        embed.add_field(name=user1.name, value=f"MMR: {stats1['mmr']}\nW/L: {stats1['wins']}/{stats1['losses']}", inline=True)
        embed.add_field(name="VS", value="âš”ï¸", inline=True)
        embed.add_field(name=user2.name, value=f"MMR: {stats2['mmr']}\nW/L: {stats2['wins']}/{stats2['losses']}", inline=True)
        
        mmr_diff = abs(stats1['mmr'] - stats2['mmr'])
        better = user1.name if stats1['mmr'] > stats2['mmr'] else user2.name
        embed.add_field(name="MMR Difference", value=f"{mmr_diff} ({better} higher)", inline=False)
    else:
        player1 = get_or_create_player(user1.id, user1.name)
        player2 = get_or_create_player(user2.id, user2.name)
        
        embed = discord.Embed(
            title="âš”ï¸ Global Player Comparison",
            color=discord.Color.purple()
        )
        
        wr1 = (player1['wins'] / player1['total_games'] * 100) if player1['total_games'] > 0 else 0
        wr2 = (player2['wins'] / player2['total_games'] * 100) if player2['total_games'] > 0 else 0
        
        embed.add_field(
            name=user1.name,
            value=f"MMR: {player1['mmr']}\nW/L: {player1['wins']}/{player1['losses']}\nWR: {wr1:.1f}%",
            inline=True
        )
        embed.add_field(name="VS", value="âš”ï¸", inline=True)
        embed.add_field(
            name=user2.name,
            value=f"MMR: {player2['mmr']}\nW/L: {player2['wins']}/{player2['losses']}\nWR: {wr2:.1f}%",
            inline=True
        )
    
    await interaction.response.send_message(embed=embed)
    log_command(interaction.guild.id, interaction.user.id, "compare", True)

# ============================================================================
# MMR MANAGEMENT COMMANDS
# ============================================================================

@bot.tree.command(name="setmmr", description="Set a player's MMR")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="Target player", mmr="New MMR value", queue_name="Specific queue (optional)")
async def setmmr(interaction: discord.Interaction, user: discord.Member, mmr: int, queue_name: Optional[str] = None):
    """Manually set player MMR"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    if mmr < 0:
        await interaction.response.send_message("âŒ MMR cannot be negative!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if queue_name:
        c.execute('UPDATE queue_stats SET mmr=? WHERE user_id=? AND guild_id=? AND queue_name=?',
                  (mmr, user.id, interaction.guild.id, queue_name))
        msg = f"âœ… Set {user.mention}'s MMR to {mmr} in queue **{queue_name}**!"
    else:
        c.execute('UPDATE players SET mmr=? WHERE user_id=?', (mmr, user.id))
        msg = f"âœ… Set {user.mention}'s global MMR to {mmr}!"
    
    conn.commit()
    conn.close()
    
    # Apply rank roles if queue specified
    if queue_name:
        apply_mmr_ranks(interaction.guild, user.id, queue_name, mmr)
    
    await interaction.response.send_message(msg)
    log_command(interaction.guild.id, interaction.user.id, "setmmr", True)

@bot.tree.command(name="adjustmmr", description="Adjust a player's MMR by amount")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="Target player", amount="Amount to add/subtract", queue_name="Specific queue (optional)")
async def adjustmmr(interaction: discord.Interaction, user: discord.Member, amount: int, queue_name: Optional[str] = None):
    """Add or subtract MMR"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if queue_name:
        stats = get_queue_player_stats(user.id, interaction.guild.id, queue_name)
        new_mmr = max(0, stats['mmr'] + amount)
        c.execute('UPDATE queue_stats SET mmr=? WHERE user_id=? AND guild_id=? AND queue_name=?',
                  (new_mmr, user.id, interaction.guild.id, queue_name))
        msg = f"âœ… Adjusted {user.mention}'s MMR by {amount:+d} to {new_mmr} in queue **{queue_name}**!"
        
        apply_mmr_ranks(interaction.guild, user.id, queue_name, new_mmr)
    else:
        player = get_or_create_player(user.id, user.name)
        new_mmr = max(0, player['mmr'] + amount)
        c.execute('UPDATE players SET mmr=? WHERE user_id=?', (new_mmr, user.id))
        msg = f"âœ… Adjusted {user.mention}'s global MMR by {amount:+d} to {new_mmr}!"
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(msg)
    log_command(interaction.guild.id, interaction.user.id, "adjustmmr", True)

@bot.tree.command(name="resetstats", description="Reset all stats for a queue")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(queue_name="Queue to reset")
async def resetstats(interaction: discord.Interaction, queue_name: str):
    """Reset all player stats for a queue"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this command!", ephemeral=True)
        return
    
    # Confirmation required
    await interaction.response.send_message(
        f"âš ï¸ This will reset ALL stats for queue **{queue_name}**!\n"
        f"Type `/confirmreset {queue_name}` to confirm.",
        ephemeral=True
    )

@bot.tree.command(name="confirmreset", description="Confirm stats reset")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(queue_name="Queue to reset")
async def confirmreset(interaction: discord.Interaction, queue_name: str):
    """Confirm stats reset"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM queue_stats WHERE guild_id=? AND queue_name=?',
              (interaction.guild.id, queue_name))
    c.execute('DELETE FROM matches WHERE guild_id=? AND queue_name=?',
              (interaction.guild.id, queue_name))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"âœ… Reset all stats for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "resetstats", True)

@bot.tree.command(name="resetuser", description="Reset a specific user's stats")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="User to reset", queue_name="Specific queue (optional)")
async def resetuser(interaction: discord.Interaction, user: discord.Member, queue_name: Optional[str] = None):
    """Reset user's stats"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if queue_name:
        c.execute('UPDATE queue_stats SET mmr=1000, wins=0, losses=0, games_played=0 WHERE user_id=? AND guild_id=? AND queue_name=?',
                  (user.id, interaction.guild.id, queue_name))
        msg = f"âœ… Reset {user.mention}'s stats for queue **{queue_name}**!"
    else:
        c.execute('UPDATE players SET mmr=1000, wins=0, losses=0, total_games=0, win_streak=0, highest_mmr=1000 WHERE user_id=?',
                  (user.id,))
        msg = f"âœ… Reset {user.mention}'s global stats!"
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(msg)
    log_command(interaction.guild.id, interaction.user.id, "resetuser", True)

# ============================================================================
# RANKS & AUTO-ROLES COMMANDS
# ============================================================================

@bot.tree.command(name="ranks", description="Manage MMR ranks")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    action="Add, remove, or list ranks",
    queue_name="Queue name"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove"),
    app_commands.Choice(name="List", value="list")
])
async def ranks(interaction: discord.Interaction, action: str, queue_name: str = "default"):
    """Manage auto-role ranks"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    if action == "list":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT rank_name, min_mmr, max_mmr, role_id FROM ranks WHERE guild_id=? AND queue_name=?',
                  (interaction.guild.id, queue_name))
        ranks = c.fetchall()
        conn.close()
        
        if not ranks:
            await interaction.response.send_message(f"No ranks configured for queue **{queue_name}**!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"ðŸ… Ranks - {queue_name}",
            color=discord.Color.gold()
        )
        
        for rank_name, min_mmr, max_mmr, role_id in ranks:
            role = interaction.guild.get_role(role_id)
            role_mention = role.mention if role else "Unknown Role"
            embed.add_field(
                name=rank_name,
                value=f"MMR: {min_mmr}-{max_mmr}\nRole: {role_mention}",
                inline=True
            )
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            f"Use `/rankadd` or `/rankremove` to manage ranks!",
            ephemeral=True
        )

@bot.tree.command(name="rankadd", description="Add an MMR rank")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    rank_name="Name of the rank",
    min_mmr="Minimum MMR",
    max_mmr="Maximum MMR",
    role="Discord role to assign",
    queue_name="Queue name"
)
async def rankadd(interaction: discord.Interaction, rank_name: str, min_mmr: int, max_mmr: int, role: discord.Role, queue_name: str = "default"):
    """Add MMR rank with auto-role"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO ranks VALUES (?, ?, ?, ?, ?, ?)',
              (interaction.guild.id, queue_name, rank_name, min_mmr, max_mmr, role.id))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(
        f"âœ… Added rank **{rank_name}** ({min_mmr}-{max_mmr} MMR) â†’ {role.mention} for queue **{queue_name}**!"
    )
    log_command(interaction.guild.id, interaction.user.id, "rankadd", True)

@bot.tree.command(name="rankremove", description="Remove an MMR rank")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(rank_name="Name of the rank", queue_name="Queue name")
async def rankremove(interaction: discord.Interaction, rank_name: str, queue_name: str = "default"):
    """Remove MMR rank"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM ranks WHERE guild_id=? AND queue_name=? AND rank_name=?',
              (interaction.guild.id, queue_name, rank_name))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"âœ… Removed rank **{rank_name}** from queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "rankremove", True)


# ============================================================================
# TEAMS/CLANS COMMANDS
# ============================================================================

@bot.tree.command(name="teamcreate", description="Create a team/clan")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(team_name="Name of your team")
async def teamcreate(interaction: discord.Interaction, team_name: str):
    """Create a new team"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if user already owns a team
    c.execute('SELECT team_id FROM teams WHERE guild_id=? AND owner_id=?',
              (interaction.guild.id, interaction.user.id))
    if c.fetchone():
        conn.close()
        await interaction.response.send_message("âŒ You already own a team! Disband it first to create a new one.", ephemeral=True)
        return
    
    # Create team
    try:
        c.execute('INSERT INTO teams (guild_id, team_name, owner_id, created_at) VALUES (?, ?, ?, ?)',
                  (interaction.guild.id, team_name, interaction.user.id, datetime.now().isoformat()))
        team_id = c.lastrowid
        
        # Add owner as member
        c.execute('INSERT INTO team_members VALUES (?, ?, ?)',
                  (team_id, interaction.user.id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(f"âœ… Created team **{team_name}**! You are the owner.")
        log_command(interaction.guild.id, interaction.user.id, "teamcreate", True)
    except sqlite3.IntegrityError:
        conn.close()
        await interaction.response.send_message("âŒ A team with that name already exists!", ephemeral=True)

@bot.tree.command(name="teaminvite", description="Invite a player to your team")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="User to invite")
async def teaminvite(interaction: discord.Interaction, user: discord.Member):
    """Invite user to team"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if user owns a team
    c.execute('SELECT team_id, team_name FROM teams WHERE guild_id=? AND owner_id=?',
              (interaction.guild.id, interaction.user.id))
    team = c.fetchone()
    
    if not team:
        conn.close()
        await interaction.response.send_message("âŒ You don't own a team!", ephemeral=True)
        return
    
    team_id, team_name = team
    
    # Check if user already in a team
    c.execute('SELECT team_id FROM team_members WHERE user_id=?', (user.id,))
    if c.fetchone():
        conn.close()
        await interaction.response.send_message(f"âŒ {user.mention} is already in a team!", ephemeral=True)
        return
    
    conn.close()
    
    await interaction.response.send_message(
        f"ðŸ“¨ {user.mention}, you've been invited to join team **{team_name}**!\n"
        f"Use `/teamjoin {team_name}` to accept."
    )

@bot.tree.command(name="teamjoin", description="Join a team")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(team_name="Name of the team")
async def teamjoin(interaction: discord.Interaction, team_name: str):
    """Join a team"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if user already in a team
    c.execute('SELECT team_id FROM team_members WHERE user_id=?', (interaction.user.id,))
    if c.fetchone():
        conn.close()
        await interaction.response.send_message("âŒ You're already in a team! Leave it first.", ephemeral=True)
        return
    
    # Find team
    c.execute('SELECT team_id FROM teams WHERE guild_id=? AND team_name=?',
              (interaction.guild.id, team_name))
    result = c.fetchone()
    
    if not result:
        conn.close()
        await interaction.response.send_message(f"âŒ Team **{team_name}** doesn't exist!", ephemeral=True)
        return
    
    team_id = result[0]
    
    # Add to team
    c.execute('INSERT INTO team_members VALUES (?, ?, ?)',
              (team_id, interaction.user.id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"âœ… Joined team **{team_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "teamjoin", True)

@bot.tree.command(name="teamleave", description="Leave your current team")
@app_commands.default_permissions(manage_guild=True)
async def teamleave(interaction: discord.Interaction):
    """Leave team"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if owner
    c.execute('SELECT team_id FROM teams WHERE owner_id=?', (interaction.user.id,))
    if c.fetchone():
        conn.close()
        await interaction.response.send_message("âŒ You're the team owner! Use `/teamdisband` instead.", ephemeral=True)
        return
    
    # Remove from team
    c.execute('DELETE FROM team_members WHERE user_id=?', (interaction.user.id,))
    rows = c.rowcount
    conn.commit()
    conn.close()
    
    if rows > 0:
        await interaction.response.send_message("âœ… Left your team!")
    else:
        await interaction.response.send_message("âŒ You're not in a team!", ephemeral=True)

@bot.tree.command(name="teamdisband", description="Disband your team")
@app_commands.default_permissions(manage_guild=True)
async def teamdisband(interaction: discord.Interaction):
    """Disband team"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if owner
    c.execute('SELECT team_id, team_name FROM teams WHERE owner_id=?', (interaction.user.id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        await interaction.response.send_message("âŒ You don't own a team!", ephemeral=True)
        return
    
    team_id, team_name = result
    
    # Delete team (cascade deletes members)
    c.execute('DELETE FROM teams WHERE team_id=?', (team_id,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"âœ… Disbanded team **{team_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "teamdisband", True)

@bot.tree.command(name="teamstats", description="View team statistics")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(team_name="Name of the team (optional)")
async def teamstats(interaction: discord.Interaction, team_name: Optional[str] = None):
    """View team stats"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if team_name:
        c.execute('SELECT * FROM teams WHERE guild_id=? AND team_name=?',
                  (interaction.guild.id, team_name))
    else:
        # Find user's team
        c.execute('''SELECT teams.* FROM teams 
                     JOIN team_members ON teams.team_id = team_members.team_id 
                     WHERE team_members.user_id=?''', (interaction.user.id,))
    
    result = c.fetchone()
    
    if not result:
        conn.close()
        await interaction.response.send_message("âŒ Team not found!", ephemeral=True)
        return
    
    team_id, guild_id, team_name, owner_id, created_at, wins, losses = result
    
    # Get members
    c.execute('SELECT user_id FROM team_members WHERE team_id=?', (team_id,))
    member_ids = [row[0] for row in c.fetchall()]
    conn.close()
    
    members = [interaction.guild.get_member(uid) for uid in member_ids]
    member_names = [m.mention for m in members if m]
    
    winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    
    embed = discord.Embed(
        title=f"ðŸ›¡ï¸ {team_name}",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Owner", value=f"<@{owner_id}>", inline=True)
    embed.add_field(name="W/L", value=f"{wins}/{losses}", inline=True)
    embed.add_field(name="Win Rate", value=f"{winrate:.1f}%", inline=True)
    embed.add_field(name="Members", value="\n".join(member_names), inline=False)
    
    await interaction.response.send_message(embed=embed)

# ============================================================================
# LOBBY DETAILS COMMANDS
# ============================================================================

@bot.tree.command(name="lobbydetails", description="Manage lobby details template")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    action="Set, remove, or preview",
    queue_name="Queue name"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Set", value="set"),
    app_commands.Choice(name="Remove", value="remove"),
    app_commands.Choice(name="Preview", value="preview")
])
async def lobbydetails(interaction: discord.Interaction, action: str, queue_name: str = "default"):
    """Manage lobby details"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    
    if action == "remove":
        settings['lobby_details_template'] = None
        save_queue_settings(settings)
        await interaction.response.send_message(f"âœ… Removed lobby details for queue **{queue_name}**!")
    elif action == "preview":
        if not settings['lobby_details_template']:
            await interaction.response.send_message("âŒ No lobby details set!", ephemeral=True)
            return
        
        # Generate preview
        preview = format_lobby_details(
            settings['lobby_details_template'],
            [interaction.user.id],
            interaction.guild,
            queue_name,
            1
        )
        
        await interaction.response.send_message(f"**Preview:**\n{preview}", ephemeral=True)
    else:
        await interaction.response.send_message(
            "Use `/lobbydetailsset <template>` to set the template!\n\n"
            "**Available variables:**\n"
            "`{HOST}` - Random player name\n"
            "`{QUEUENUM}` - Match number\n"
            "`{RANDOMTEAM}` - Random team name\n"
            "`{PASSWORD8A}` - Random 8-char password",
            ephemeral=True
        )

@bot.tree.command(name="lobbydetailsset", description="Set lobby details template")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(template="Template with variables", queue_name="Queue name")
async def lobbydetailsset(interaction: discord.Interaction, template: str, queue_name: str = "default"):
    """Set lobby details template"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    settings = get_queue_settings(interaction.guild.id, queue_name)
    settings['lobby_details_template'] = template
    save_queue_settings(settings)
    
    await interaction.response.send_message(f"âœ… Set lobby details template for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "lobbydetailsset", True)

# ============================================================================
# LOGS & MONITORING COMMANDS
# ============================================================================

@bot.tree.command(name="commandlog", description="View recent command usage")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(limit="Number of commands to show")
async def commandlog(interaction: discord.Interaction, limit: int = 10):
    """View command logs"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT user_id, command_name, timestamp, success 
                 FROM command_logs 
                 WHERE guild_id=? 
                 ORDER BY log_id DESC LIMIT ?''',
              (interaction.guild.id, min(limit, 25)))
    logs = c.fetchall()
    conn.close()
    
    if not logs:
        await interaction.response.send_message("âŒ No command logs found!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="ðŸ“‹ Command Log",
        color=discord.Color.blue()
    )
    
    for user_id, command_name, timestamp, success in logs[:10]:
        member = interaction.guild.get_member(user_id)
        name = member.name if member else f"User {user_id}"
        time_str = datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
        status = "âœ…" if success else "âŒ"
        embed.add_field(
            name=f"{status} /{command_name}",
            value=f"{name} at {time_str}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="activitylog", description="View queue activity")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(limit="Number of activities to show", queue_name="Queue name")
async def activitylog(interaction: discord.Interaction, limit: int = 10, queue_name: str = "default"):
    """View activity logs"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT user_id, action, timestamp 
                 FROM activity_logs 
                 WHERE guild_id=? AND queue_name=? 
                 ORDER BY log_id DESC LIMIT ?''',
              (interaction.guild.id, queue_name, min(limit, 25)))
    logs = c.fetchall()
    conn.close()
    
    if not logs:
        await interaction.response.send_message("âŒ No activity logs found!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"ðŸ“Š Activity Log - {queue_name}",
        color=discord.Color.blue()
    )
    
    for user_id, action, timestamp in logs[:10]:
        member = interaction.guild.get_member(user_id)
        name = member.name if member else f"User {user_id}"
        time_str = datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
        embed.add_field(
            name=name,
            value=f"{action} at {time_str}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================================
# ADDITIONAL MATCH & STATS COMMANDS
# ============================================================================

@bot.tree.command(name="viewmatch", description="View details of a specific match")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(match_id="Match ID to view")
async def viewmatch(interaction: discord.Interaction, match_id: int):
    """View detailed match information"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT match_id, queue_name, timestamp, team1, team2, winner, mmr_change, 
                        team1_score, team2_score, map_played, lobby_details
                 FROM matches WHERE match_id=? AND guild_id=?''',
              (match_id, interaction.guild.id))
    match = c.fetchone()
    conn.close()
    
    if not match:
        await interaction.response.send_message(f"âŒ Match #{match_id} not found!", ephemeral=True)
        return
    
    match_id, queue_name, timestamp, team1_json, team2_json, winner, mmr_change, score1, score2, map_played, lobby = match
    team1 = json.loads(team1_json)
    team2 = json.loads(team2_json)
    
    embed = discord.Embed(
        title=f"ðŸ† Match #{match_id} - {queue_name}",
        description=f"Played: {datetime.fromisoformat(timestamp).strftime('%Y-%m-%d %H:%M')}",
        color=discord.Color.green() if winner else discord.Color.red()
    )
    
    # Team 1
    team1_players = []
    for player_id in team1:
        member = interaction.guild.get_member(player_id)
        name = member.name if member else f"User {player_id}"
        team1_players.append(name)
    
    embed.add_field(
        name=f"ðŸ”µ Team 1 {'âœ…' if winner == 1 else ''}",
        value="\n".join(team1_players) or "No players",
        inline=True
    )
    
    # Team 2
    team2_players = []
    for player_id in team2:
        member = interaction.guild.get_member(player_id)
        name = member.name if member else f"User {player_id}"
        team2_players.append(name)
    
    embed.add_field(
        name=f"ðŸ”´ Team 2 {'âœ…' if winner == 2 else ''}",
        value="\n".join(team2_players) or "No players",
        inline=True
    )
    
    # Match details
    if map_played:
        embed.add_field(name="ðŸ—ºï¸ Map", value=map_played, inline=False)
    if score1 or score2:
        embed.add_field(name="ðŸ“Š Score", value=f"{score1} - {score2}", inline=False)
    if mmr_change:
        embed.add_field(name="ðŸ“ˆ MMR Change", value=f"Â±{mmr_change}", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="recentmatches", description="View recent matches for a player")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="Player to view (default: you)", limit="Number of matches", queue_name="Specific queue")
async def recentmatches(interaction: discord.Interaction, user: Optional[discord.Member] = None, limit: int = 5, queue_name: Optional[str] = None):
    """View recent matches for a specific player"""
    target = user or interaction.user
    limit = min(limit, 10)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if queue_name:
        c.execute('''SELECT match_id, timestamp, team1, team2, winner, queue_name 
                     FROM matches 
                     WHERE guild_id=? AND queue_name=? AND (team1 LIKE ? OR team2 LIKE ?)
                     ORDER BY match_id DESC LIMIT ?''',
                  (interaction.guild.id, queue_name, f'%{target.id}%', f'%{target.id}%', limit))
    else:
        c.execute('''SELECT match_id, timestamp, team1, team2, winner, queue_name 
                     FROM matches 
                     WHERE guild_id=? AND (team1 LIKE ? OR team2 LIKE ?)
                     ORDER BY match_id DESC LIMIT ?''',
                  (interaction.guild.id, f'%{target.id}%', f'%{target.id}%', limit))
    
    matches = c.fetchall()
    conn.close()
    
    if not matches:
        await interaction.response.send_message(f"âŒ No recent matches found for {target.mention}!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"ðŸ“‹ Recent Matches - {target.name}",
        color=discord.Color.blue()
    )
    
    for match_id, timestamp, team1_json, team2_json, winner, q_name in matches:
        team1 = json.loads(team1_json)
        team2 = json.loads(team2_json)
        
        # Determine if player won
        player_team = 1 if target.id in team1 else 2
        result = "âœ… Win" if winner == player_team else "âŒ Loss" if winner else "âšª No result"
        
        time_str = datetime.fromisoformat(timestamp).strftime("%m/%d %H:%M")
        embed.add_field(
            name=f"Match #{match_id} - {q_name}",
            value=f"{result} â€¢ {time_str}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="winstreak", description="View win streak for a player")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="Player to view (default: you)", queue_name="Specific queue")
async def winstreak(interaction: discord.Interaction, user: Optional[discord.Member] = None, queue_name: Optional[str] = None):
    """View current and longest win streak"""
    target = user or interaction.user
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Get matches
    if queue_name:
        c.execute('''SELECT match_id, team1, team2, winner 
                     FROM matches 
                     WHERE guild_id=? AND queue_name=? AND (team1 LIKE ? OR team2 LIKE ?) AND winner IS NOT NULL
                     ORDER BY match_id DESC LIMIT 50''',
                  (interaction.guild.id, queue_name, f'%{target.id}%', f'%{target.id}%'))
        stats = get_queue_player_stats(target.id, interaction.guild.id, queue_name)
    else:
        c.execute('''SELECT match_id, team1, team2, winner 
                     FROM matches 
                     WHERE guild_id=? AND (team1 LIKE ? OR team2 LIKE ?) AND winner IS NOT NULL
                     ORDER BY match_id DESC LIMIT 50''',
                  (interaction.guild.id, f'%{target.id}%', f'%{target.id}%'))
        stats = get_or_create_player(target.id, target.name)
    
    matches = c.fetchall()
    conn.close()
    
    # Calculate current streak
    current_streak = 0
    longest_streak = 0
    temp_streak = 0
    
    for match_id, team1_json, team2_json, winner in matches:
        team1 = json.loads(team1_json)
        team2 = json.loads(team2_json)
        player_team = 1 if target.id in team1 else 2
        
        if winner == player_team:
            temp_streak += 1
            longest_streak = max(longest_streak, temp_streak)
            if current_streak == 0:  # First match
                current_streak = temp_streak
        else:
            temp_streak = 0
            if current_streak == 0:
                current_streak = temp_streak
    
    embed = discord.Embed(
        title=f"ðŸ”¥ Win Streaks - {target.name}",
        color=discord.Color.orange()
    )
    
    embed.add_field(name="Current Streak", value=f"{current_streak} {'win' if current_streak == 1 else 'wins'}", inline=True)
    embed.add_field(name="Longest Streak", value=f"{longest_streak} {'win' if longest_streak == 1 else 'wins'}", inline=True)
    
    if queue_name:
        embed.set_footer(text=f"Queue: {queue_name}")
    else:
        embed.set_footer(text="All queues")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="modifyresult", description="Change the result of a previous match")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(match_id="Match ID", winning_team="New winning team (1 or 2, or 0 for draw)")
async def modifyresult(interaction: discord.Interaction, match_id: int, winning_team: int):
    """Modify match result (Admin only)"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this command!", ephemeral=True)
        return
    
    if winning_team not in [0, 1, 2]:
        await interaction.response.send_message("âŒ Winning team must be 0 (draw), 1, or 2!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Get match
    c.execute('SELECT team1, team2, winner, queue_name FROM matches WHERE match_id=? AND guild_id=?',
              (match_id, interaction.guild.id))
    match = c.fetchone()
    
    if not match:
        await interaction.response.send_message(f"âŒ Match #{match_id} not found!", ephemeral=True)
        conn.close()
        return
    
    team1_json, team2_json, old_winner, queue_name = match
    team1 = json.loads(team1_json)
    team2 = json.loads(team2_json)
    
    # Reverse old MMR changes
    if old_winner:
        for player_id in (team1 if old_winner == 1 else team2):
            c.execute('UPDATE queue_stats SET mmr = mmr - 25, wins = wins - 1 WHERE user_id=? AND guild_id=? AND queue_name=?',
                      (player_id, interaction.guild.id, queue_name))
        for player_id in (team2 if old_winner == 1 else team1):
            c.execute('UPDATE queue_stats SET mmr = mmr + 25, losses = losses - 1 WHERE user_id=? AND guild_id=? AND queue_name=?',
                      (player_id, interaction.guild.id, queue_name))
    
    # Apply new MMR changes
    if winning_team:
        for player_id in (team1 if winning_team == 1 else team2):
            c.execute('UPDATE queue_stats SET mmr = mmr + 25, wins = wins + 1 WHERE user_id=? AND guild_id=? AND queue_name=?',
                      (player_id, interaction.guild.id, queue_name))
        for player_id in (team2 if winning_team == 1 else team1):
            c.execute('UPDATE queue_stats SET mmr = mmr - 25, losses = losses + 1 WHERE user_id=? AND guild_id=? AND queue_name=?',
                      (player_id, interaction.guild.id, queue_name))
    
    # Update match
    c.execute('UPDATE matches SET winner=? WHERE match_id=?', (winning_team if winning_team else None, match_id))
    
    conn.commit()
    conn.close()
    
    result_text = "draw" if winning_team == 0 else f"Team {winning_team} win"
    await interaction.response.send_message(f"âœ… Modified match #{match_id} result to: **{result_text}**")
    log_command(interaction.guild.id, interaction.user.id, "modifyresult", True)

@bot.tree.command(name="rolelimit", description="Limit how many players with a role can be in a match")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    action="Add or remove role limit",
    role="Discord role",
    limit="Max players with this role per match",
    queue_name="Queue name"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove")
])
async def rolelimit(interaction: discord.Interaction, action: str, role: discord.Role, limit: Optional[int] = None, queue_name: str = "default"):
    """Manage role limits for matches"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if action == "add":
        if limit is None or limit < 1:
            await interaction.response.send_message("âŒ Please specify a valid limit!", ephemeral=True)
            conn.close()
            return
        
        c.execute('INSERT OR REPLACE INTO role_limits VALUES (?, ?, ?, ?)',
                  (interaction.guild.id, queue_name, role.id, limit))
        conn.commit()
        await interaction.response.send_message(
            f"âœ… Set role limit: Max {limit} {role.mention} per match in queue **{queue_name}**"
        )
    
    elif action == "remove":
        c.execute('DELETE FROM role_limits WHERE guild_id=? AND queue_name=? AND role_id=?',
                  (interaction.guild.id, queue_name, role.id))
        conn.commit()
        await interaction.response.send_message(
            f"âœ… Removed role limit for {role.mention} in queue **{queue_name}**"
        )
    
    conn.close()
    log_command(interaction.guild.id, interaction.user.id, "rolelimit", True)

@bot.tree.command(name="mmrdecay", description="Enable/disable MMR decay for inactive players")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(enabled="Enable or disable", queue_name="Queue name")
async def mmrdecay(interaction: discord.Interaction, enabled: bool, queue_name: str = "default"):
    """Toggle MMR decay"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE queue_settings SET mmr_decay_enabled=? WHERE guild_id=? AND queue_name=?',
              (1 if enabled else 0, interaction.guild.id, queue_name))
    conn.commit()
    conn.close()
    
    status = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"âœ… MMR decay **{status}** for queue **{queue_name}**!")
    log_command(interaction.guild.id, interaction.user.id, "mmrdecay", True)

@bot.tree.command(name="graceperiod", description="Give a user grace period from MMR decay")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(user="User to grant grace period", days="Number of days")
async def graceperiod(interaction: discord.Interaction, user: discord.Member, days: int):
    """Grant MMR decay grace period"""
    if not is_user_staff(interaction.guild, interaction.user):
        await interaction.response.send_message("âŒ Only staff can use this command!", ephemeral=True)
        return
    
    if days < 0 or days > 365:
        await interaction.response.send_message("âŒ Days must be between 0 and 365!", ephemeral=True)
        return
    
    grace_until = (datetime.now() + timedelta(days=days)).isoformat()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE players SET grace_period_until=? WHERE user_id=?', (grace_until, user.id))
    
    if c.rowcount == 0:
        # Create player if doesn't exist
        c.execute('INSERT INTO players (user_id, username, grace_period_until) VALUES (?, ?, ?)',
                  (user.id, user.name, grace_until))
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(
        f"âœ… Granted {user.mention} a {days}-day grace period from MMR decay!"
    )
    log_command(interaction.guild.id, interaction.user.id, "graceperiod", True)


# ============================================================================
# MUSIC COMMANDS
# ============================================================================

@bot.tree.command(name="join", description="Join your voice channel")
async def join(interaction: discord.Interaction):
    """Join user's voice channel"""
    if not interaction.user.voice:
        await interaction.response.send_message("âŒ You're not in a voice channel!", ephemeral=True)
        return
    
    channel = interaction.user.voice.channel
    
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.move_to(channel)
    else:
        await channel.connect()
    
    await interaction.response.send_message(f"âœ… Joined {channel.name}!")
    log_command(interaction.guild.id, interaction.user.id, "join", True)

@bot.tree.command(name="leave", description="Leave voice channel")
async def leave(interaction: discord.Interaction):
    """Leave voice channel and clear queue"""
    if interaction.guild.voice_client:
        music_queue = get_music_queue(interaction.guild.id)
        music_queue.clear()
        now_playing.pop(interaction.guild.id, None)
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("âœ… Left voice channel!")
    else:
        await interaction.response.send_message("âŒ I'm not in a voice channel!", ephemeral=True)

@bot.tree.command(name="play", description="Play a song")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(query="Song name or YouTube URL")
async def play(interaction: discord.Interaction, query: str):
    """Play a song from YouTube"""
    await interaction.response.defer()
    
    try:
        if not interaction.guild.voice_client:
            if not interaction.user.voice:
                await interaction.followup.send("âŒ You need to be in a voice channel!")
                return
            await interaction.user.voice.channel.connect()
        
        song = await extract_song_info(query)
        if not song:
            await interaction.followup.send("âŒ Couldn't find that song!")
            return
        
        music_queue = get_music_queue(interaction.guild.id)
        
        if not interaction.guild.voice_client.is_playing():
            music_queue.add(song)
            await play_next(interaction.guild)
            
            embed = discord.Embed(
                title="ðŸŽµ Now Playing",
                description=f"[{song['title']}]({song['webpage_url']})",
                color=discord.Color.green()
            )
            if song['thumbnail']:
                embed.set_thumbnail(url=song['thumbnail'])
            embed.add_field(name="Duration", value=f"{song['duration'] // 60}:{song['duration'] % 60:02d}")
            
            await interaction.followup.send(embed=embed)
        else:
            music_queue.add(song)
            await interaction.followup.send(
                f"âœ… Added to queue: **{song['title']}** (Position: {len(music_queue.queue)})"
            )
        
        log_command(interaction.guild.id, interaction.user.id, "play", True)
    
    except Exception as e:
        logger.error(f"Play command error: {e}", exc_info=True)
        await interaction.followup.send(f"âŒ An error occurred: {str(e)}")
        log_command(interaction.guild.id, interaction.user.id, "play", False)

@bot.tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    """Skip current song"""
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("â­ï¸ Skipped!")
    else:
        await interaction.response.send_message("âŒ Nothing is playing!", ephemeral=True)

@bot.tree.command(name="pause", description="Pause playback")
async def pause(interaction: discord.Interaction):
    """Pause current song"""
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("â¸ï¸ Paused!")
    else:
        await interaction.response.send_message("âŒ Nothing is playing!", ephemeral=True)

@bot.tree.command(name="resume", description="Resume playback")
async def resume(interaction: discord.Interaction):
    """Resume paused song"""
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("â–¶ï¸ Resumed!")
    else:
        await interaction.response.send_message("âŒ Nothing is paused!", ephemeral=True)

@bot.tree.command(name="stop", description="Stop playback and clear queue")
async def stop(interaction: discord.Interaction):
    """Stop playback and clear music queue"""
    if interaction.guild.voice_client:
        music_queue = get_music_queue(interaction.guild.id)
        music_queue.clear()
        now_playing.pop(interaction.guild.id, None)
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("â¹ï¸ Stopped and cleared queue!")
    else:
        await interaction.response.send_message("âŒ Nothing is playing!", ephemeral=True)

@bot.tree.command(name="nowplaying", description="Show current song")
async def nowplaying(interaction: discord.Interaction):
    """Display currently playing song"""
    if interaction.guild.id in now_playing:
        song = now_playing[interaction.guild.id]
        embed = discord.Embed(
            title="ðŸŽµ Now Playing",
            description=f"[{song['title']}]({song['webpage_url']})",
            color=discord.Color.blue()
        )
        if song['thumbnail']:
            embed.set_thumbnail(url=song['thumbnail'])
        embed.add_field(name="Duration", value=f"{song['duration'] // 60}:{song['duration'] % 60:02d}")
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("âŒ Nothing is playing!", ephemeral=True)

@bot.tree.command(name="musicqueue", description="View music queue")
async def musicqueue(interaction: discord.Interaction):
    """Display current music queue"""
    music_queue = get_music_queue(interaction.guild.id)
    
    if music_queue.is_empty() and interaction.guild.id not in now_playing:
        await interaction.response.send_message("âŒ The queue is empty!", ephemeral=True)
        return
    
    embed = discord.Embed(title="ðŸŽµ Music Queue", color=discord.Color.blue())
    
    if interaction.guild.id in now_playing:
        current = now_playing[interaction.guild.id]
        embed.add_field(
            name="Now Playing",
            value=f"[{current['title']}]({current['webpage_url']})",
            inline=False
        )
    
    if not music_queue.is_empty():
        queue_text = ""
        for i, song in enumerate(list(music_queue.queue)[:10], 1):
            queue_text += f"`{i}.` [{song['title']}]({song['webpage_url']})\n"
        
        if len(music_queue.queue) > 10:
            queue_text += f"\n*...and {len(music_queue.queue) - 10} more*"
        
        embed.add_field(name="Up Next", value=queue_text, inline=False)
    
    embed.set_footer(text=f"Total songs in queue: {len(music_queue.queue)}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="volume", description="Set volume (0-100)")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(volume="Volume level")
async def volume(interaction: discord.Interaction, volume: int):
    """Set playback volume"""
    if not 0 <= volume <= 100:
        await interaction.response.send_message("âŒ Volume must be between 0 and 100!", ephemeral=True)
        return
    
    if interaction.guild.voice_client:
        music_queue = get_music_queue(interaction.guild.id)
        music_queue.volume = volume / 100
        
        if interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = music_queue.volume
        
        await interaction.response.send_message(f"ðŸ”Š Volume set to {volume}%")
    else:
        await interaction.response.send_message("âŒ I'm not in a voice channel!", ephemeral=True)

@bot.tree.command(name="loop", description="Toggle loop mode")
async def loop(interaction: discord.Interaction):
    """Toggle loop for current song"""
    music_queue = get_music_queue(interaction.guild.id)
    music_queue.loop = not music_queue.loop
    
    status = "enabled" if music_queue.loop else "disabled"
    await interaction.response.send_message(f"ðŸ” Loop {status}!")

# ============================================================================
# REACTION ROLES (Simplified - Carl-bot style)
# ============================================================================

class ReactionRoleView(discord.ui.View):
    """Persistent button view for reaction roles - survives bot restarts"""
    
    def __init__(self, panel_id: int):
        super().__init__(timeout=None)
        self.panel_id = panel_id
        self._load_buttons()
    
    def _load_buttons(self):
        """Load buttons from database"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, role_id, emoji, label FROM reaction_roles WHERE panel_id=?', 
                      (self.panel_id,))
            roles = c.fetchall()
            conn.close()
            
            for role_id_db, role_id, emoji, label in roles:
                button = ReactionRoleButton(
                    role_id=role_id,
                    emoji=emoji,
                    label=label,
                    custom_id=f"rr:{self.panel_id}:{role_id}"
                )
                self.add_item(button)
        except Exception as e:
            logger.error(f"Failed to load reaction role buttons: {e}")


class ReactionRoleButton(discord.ui.Button):
    """A single reaction role button - toggles a role on/off"""
    
    def __init__(self, role_id: int, emoji: str, label: str, custom_id: str):
        super().__init__(
            style=discord.ButtonStyle.green,
            emoji=emoji if emoji else None,
            label=label,
            custom_id=custom_id
        )
        self.role_id = role_id
    
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("âŒ This role no longer exists!", ephemeral=True)
            return
        
        member = interaction.user
        if role in member.roles:
            try:
                await member.remove_roles(role)
                await interaction.response.send_message(
                    f"âœ… Removed **{role.name}** role!", ephemeral=True
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    "âŒ I don't have permission to remove that role! Make sure my role is above this role in Server Settings â†’ Roles.", ephemeral=True
                )
        else:
            try:
                await member.add_roles(role)
                await interaction.response.send_message(
                    f"âœ… You now have the **{role.name}** role!", ephemeral=True
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    "âŒ I don't have permission to assign that role! Make sure my role is above this role in Server Settings â†’ Roles.", ephemeral=True
                )


def _save_panel_and_send(guild_id, channel_id, title, description, created_by):
    """Helper to create a panel in the database and return its ID"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO reaction_role_panels 
                 (guild_id, channel_id, message_id, title, description, created_by, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (guild_id, channel_id, 0, title, description, created_by, datetime.now().isoformat()))
    panel_id = c.lastrowid
    conn.commit()
    conn.close()
    return panel_id


def _add_role_to_panel(panel_id, guild_id, role_id, emoji, label):
    """Helper to add a role to a panel"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO reaction_roles (panel_id, guild_id, role_id, emoji, label)
                 VALUES (?, ?, ?, ?, ?)''', (panel_id, guild_id, role_id, emoji, label))
    conn.commit()
    conn.close()


def _build_panel_embed(panel_id, title, description):
    """Build the embed for a reaction role panel"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT role_id, emoji, label FROM reaction_roles WHERE panel_id=?', (panel_id,))
    roles = c.fetchall()
    conn.close()
    
    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
    
    if roles:
        role_list = ""
        for role_id, emoji, label in roles:
            emoji_str = f"{emoji} " if emoji else "ðŸ”¹ "
            role_list += f"{emoji_str}**{label}** â†’ <@&{role_id}>\n"
        embed.add_field(name="Available Roles", value=role_list, inline=False)
    
    embed.set_footer(text="Click a button to get or remove a role!")
    return embed


async def _update_panel_message(guild, panel_id):
    """Update an existing panel message after changes"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT channel_id, message_id, title, description FROM reaction_role_panels WHERE panel_id=?', (panel_id,))
    panel = c.fetchone()
    conn.close()
    
    if not panel:
        return
    
    channel_id, message_id, title, description = panel
    try:
        channel = guild.get_channel(channel_id)
        if channel:
            msg = await channel.fetch_message(message_id)
            new_view = ReactionRoleView(panel_id)
            new_embed = _build_panel_embed(panel_id, title, description)
            await msg.edit(embed=new_embed, view=new_view)
            bot.add_view(new_view, message_id=message_id)
    except Exception as e:
        logger.error(f"Failed to update panel message: {e}")


# ==========================================
# /verify - ONE COMMAND VERIFICATION SETUP
# ==========================================

@bot.tree.command(name="verify", description="Set up a verification button in this channel (Admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(role="The role to give when someone clicks Verify")
async def verify_setup(interaction: discord.Interaction, role: discord.Role):
    """
    One-command verification setup!
    Just type: /verify @Verified
    Creates a verification panel with a button. Users click it to get the role.
    """
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this!", ephemeral=True)
        return
    
    # Create panel
    panel_id = _save_panel_and_send(
        interaction.guild.id, interaction.channel.id,
        "âœ… Server Verification",
        "Click the button below to verify yourself and unlock the server!",
        interaction.user.id
    )
    
    # Add the role
    _add_role_to_panel(panel_id, interaction.guild.id, role.id, "âœ…", "Click to Verify")
    
    # Build and send
    embed = _build_panel_embed(panel_id, "âœ… Server Verification",
                                "Click the button below to verify yourself and unlock the server!")
    view = ReactionRoleView(panel_id)
    
    await interaction.response.send_message(embed=embed, view=view)
    msg = await interaction.original_response()
    
    # Save message ID
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE reaction_role_panels SET message_id=? WHERE panel_id=?', (msg.id, panel_id))
    conn.commit()
    conn.close()
    bot.add_view(view, message_id=msg.id)
    
    log_command(interaction.guild.id, interaction.user.id, 'verify_setup')
    logger.info(f"Verification panel created in guild {interaction.guild.id}")


# ==========================================
# /rolepanel - SIMPLE ROLE PANEL COMMANDS
# ==========================================

@bot.tree.command(name="rolepanel", description="Create a role selection panel in this channel (Admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    role1="First role (required)",
    role2="Second role (optional)",
    role3="Third role (optional)",
    role4="Fourth role (optional)",
    role5="Fifth role (optional)",
    title="Panel title (optional)"
)
async def rolepanel(
    interaction: discord.Interaction,
    role1: discord.Role,
    role2: Optional[discord.Role] = None,
    role3: Optional[discord.Role] = None,
    role4: Optional[discord.Role] = None,
    role5: Optional[discord.Role] = None,
    title: Optional[str] = None
):
    """
    Create a role panel with up to 5 roles in ONE command!
    Example: /rolepanel @Valorant @CS2 @League
    Users click buttons to get/remove roles.
    """
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this!", ephemeral=True)
        return
    
    roles = [r for r in [role1, role2, role3, role4, role5] if r is not None]
    panel_title = title or "ðŸŽ­ Role Selection"
    
    # Create panel
    panel_id = _save_panel_and_send(
        interaction.guild.id, interaction.channel.id,
        panel_title,
        "Click a button below to get or remove a role!",
        interaction.user.id
    )
    
    # Add all roles
    for role in roles:
        _add_role_to_panel(panel_id, interaction.guild.id, role.id, None, role.name)
    
    # Build and send
    embed = _build_panel_embed(panel_id, panel_title,
                                "Click a button below to get or remove a role!")
    view = ReactionRoleView(panel_id)
    
    await interaction.response.send_message(embed=embed, view=view)
    msg = await interaction.original_response()
    
    # Save message ID
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE reaction_role_panels SET message_id=? WHERE panel_id=?', (msg.id, panel_id))
    conn.commit()
    conn.close()
    bot.add_view(view, message_id=msg.id)
    
    role_names = ", ".join([f"**{r.name}**" for r in roles])
    log_command(interaction.guild.id, interaction.user.id, 'rolepanel')
    logger.info(f"Role panel created with {len(roles)} roles in guild {interaction.guild.id}")


@bot.tree.command(name="rolepaneladd", description="Add a role to an existing panel (Admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    role="The role to add",
    panel_id="Panel ID number (use /rolepanellist to find it)",
    emoji="Button emoji (optional)",
    label="Button text (optional, defaults to role name)"
)
async def rolepaneladd(
    interaction: discord.Interaction,
    role: discord.Role,
    panel_id: int,
    emoji: Optional[str] = None,
    label: Optional[str] = None
):
    """Add a role to an existing panel"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this!", ephemeral=True)
        return
    
    # Check panel exists
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT panel_id FROM reaction_role_panels WHERE panel_id=? AND guild_id=?',
              (panel_id, interaction.guild.id))
    if not c.fetchone():
        conn.close()
        await interaction.response.send_message("âŒ Panel not found! Use `/rolepanellist` to see your panels.", ephemeral=True)
        return
    
    # Check not already added
    c.execute('SELECT id FROM reaction_roles WHERE panel_id=? AND role_id=?', (panel_id, role.id))
    if c.fetchone():
        conn.close()
        await interaction.response.send_message(f"âŒ **{role.name}** is already on that panel!", ephemeral=True)
        return
    
    # Check max 25
    c.execute('SELECT COUNT(*) FROM reaction_roles WHERE panel_id=?', (panel_id,))
    if c.fetchone()[0] >= 25:
        conn.close()
        await interaction.response.send_message("âŒ Max 25 roles per panel!", ephemeral=True)
        return
    conn.close()
    
    _add_role_to_panel(panel_id, interaction.guild.id, role.id, emoji, label or role.name)
    await _update_panel_message(interaction.guild, panel_id)
    
    await interaction.response.send_message(f"âœ… Added **{role.name}** to panel #{panel_id}!", ephemeral=True)
    log_command(interaction.guild.id, interaction.user.id, 'rolepaneladd')


@bot.tree.command(name="rolepanelremove", description="Remove a role from a panel (Admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    role="The role to remove",
    panel_id="Panel ID number (use /rolepanellist to find it)"
)
async def rolepanelremove(
    interaction: discord.Interaction,
    role: discord.Role,
    panel_id: int
):
    """Remove a role from a panel"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT panel_id FROM reaction_role_panels WHERE panel_id=? AND guild_id=?',
              (panel_id, interaction.guild.id))
    if not c.fetchone():
        conn.close()
        await interaction.response.send_message("âŒ Panel not found!", ephemeral=True)
        return
    
    c.execute('DELETE FROM reaction_roles WHERE panel_id=? AND role_id=?', (panel_id, role.id))
    if c.rowcount == 0:
        conn.close()
        await interaction.response.send_message(f"âŒ **{role.name}** is not on that panel!", ephemeral=True)
        return
    conn.commit()
    conn.close()
    
    await _update_panel_message(interaction.guild, panel_id)
    await interaction.response.send_message(f"âœ… Removed **{role.name}** from panel #{panel_id}!", ephemeral=True)
    log_command(interaction.guild.id, interaction.user.id, 'rolepanelremove')


@bot.tree.command(name="rolepaneldelete", description="Delete an entire role panel (Admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(panel_id="Panel ID number (use /rolepanellist to find it)")
async def rolepaneldelete(interaction: discord.Interaction, panel_id: int):
    """Delete a panel and its message"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this!", ephemeral=True)
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT channel_id, message_id FROM reaction_role_panels WHERE panel_id=? AND guild_id=?',
              (panel_id, interaction.guild.id))
    panel = c.fetchone()
    
    if not panel:
        conn.close()
        await interaction.response.send_message("âŒ Panel not found!", ephemeral=True)
        return
    
    channel_id, message_id = panel
    c.execute('DELETE FROM reaction_roles WHERE panel_id=?', (panel_id,))
    c.execute('DELETE FROM reaction_role_panels WHERE panel_id=?', (panel_id,))
    conn.commit()
    conn.close()
    
    try:
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            msg = await channel.fetch_message(message_id)
            await msg.delete()
    except Exception:
        pass
    
    await interaction.response.send_message(f"âœ… Deleted panel #{panel_id}!", ephemeral=True)
    log_command(interaction.guild.id, interaction.user.id, 'rolepaneldelete')


@bot.tree.command(name="rolepanellist", description="List all role panels in this server")
@app_commands.default_permissions(administrator=True)
async def rolepanellist(interaction: discord.Interaction):
    """List all panels"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT panel_id, channel_id, title FROM reaction_role_panels WHERE guild_id=?',
              (interaction.guild.id,))
    panels = c.fetchall()
    
    if not panels:
        conn.close()
        await interaction.response.send_message(
            "ðŸ“­ No role panels yet!\n\n"
            "**Quick setup:**\n"
            "â€¢ `/verify @role` â€” Verification button\n"
            "â€¢ `/rolepanel @role1 @role2` â€” Role selection panel",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(title="ðŸŽ­ Your Role Panels", color=discord.Color.blurple())
    
    for pid, ch_id, p_title in panels:
        c.execute('SELECT role_id, label FROM reaction_roles WHERE panel_id=?', (pid,))
        roles = c.fetchall()
        
        role_text = ""
        for role_id, lab in roles:
            role_text += f"â€¢ {lab} â†’ <@&{role_id}>\n"
        if not role_text:
            role_text = "*No roles yet*"
        
        channel = interaction.guild.get_channel(ch_id)
        ch_name = channel.mention if channel else "Unknown"
        
        embed.add_field(
            name=f"Panel #{pid} â€” {p_title} (in {ch_name})",
            value=role_text,
            inline=False
        )
    
    conn.close()
    embed.set_footer(text="Use /rolepaneladd, /rolepanelremove, or /rolepaneldelete to manage panels")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================================================
# EMOJI REACTION ROLES (Carl-bot Style)
# ============================================================================

@bot.tree.command(name="reactionrole", description="Manage emoji reaction roles (Carl-bot style)")
@app_commands.describe(
    action="What to do (create/add/remove/list/delete/edit/mode)",
    channel="Channel to create message in (for 'create')",
    description="Message description (for 'create' and 'edit')",
    title="Message title (for 'create' and 'edit')",
    message_id="ID of the reaction role message",
    emoji="Emoji to use",
    role="Role to assign",
    mode="Mode to set (normal/unique/temporary/reversed)"
)
async def reactionrole(
    interaction: discord.Interaction,
    action: str,
    channel: discord.TextChannel = None,
    description: str = None,
    title: str = None,
    message_id: str = None,
    emoji: str = None,
    role: discord.Role = None,
    mode: str = None
):
    """Emoji reaction role management system (like Carl-bot)"""
    
    # Permission check
    if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("âŒ You need Manage Roles or Manage Server permission!", ephemeral=True)
        return
    
    action = action.lower()
    
    # CREATE NEW REACTION ROLE MESSAGE
    if action == "create":
        if not channel or not description:
            await interaction.response.send_message(
                "âŒ Usage: `/reactionrole create [channel] [description] [title]`\n"
                "Example: `/reactionrole create #roles \"React to get roles!\" Role Selection`",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=title or "Reaction Roles",
            description=description,
            color=discord.Color.blue()
        )
        embed.set_footer(text="Click reactions below to get roles!")
        
        try:
            msg = await channel.send(embed=embed)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO emoji_reaction_messages (message_id, channel_id, guild_id, title, description)
                VALUES (?, ?, ?, ?, ?)
            ''', (msg.id, channel.id, interaction.guild.id, title, description))
            conn.commit()
            conn.close()
            
            await interaction.response.send_message(
                f"âœ… Reaction role message created!\n"
                f"**Message ID:** `{msg.id}`\n"
                f"**Channel:** {channel.mention}\n\n"
                f"**Next step:** Add roles using:\n"
                f"`/reactionrole add {msg.id} [emoji] @Role`",
                ephemeral=True
            )
            log_command(interaction.guild.id, interaction.user.id, 'reactionrole_create')
            logger.info(f"Created emoji reaction role message {msg.id} in {channel.name}")
            
        except Exception as e:
            await interaction.response.send_message(f"âŒ Error creating message: {e}", ephemeral=True)
            logger.error(f"Error creating emoji reaction role message: {e}")
    
    # ADD ROLE-REACTION PAIR
    elif action == "add":
        if not message_id or not emoji or not role:
            await interaction.response.send_message(
                "âŒ Usage: `/reactionrole add [message_id] [emoji] @Role`\n"
                "Example: `/reactionrole add 123456789 ðŸŽ® @Gamer`",
                ephemeral=True
            )
            return
        
        try:
            msg_id = int(message_id)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT channel_id FROM emoji_reaction_messages WHERE message_id = ?', (msg_id,))
            result = c.fetchone()
            
            if not result:
                await interaction.response.send_message(
                    f"âŒ Message ID `{msg_id}` is not a registered reaction role message!\n"
                    f"Create one first with `/reactionrole create`",
                    ephemeral=True
                )
                conn.close()
                return
            
            channel_id = result[0]
            
            try:
                c.execute('''
                    INSERT INTO emoji_reaction_pairs (message_id, emoji, role_id)
                    VALUES (?, ?, ?)
                ''', (msg_id, emoji, role.id))
                conn.commit()
            except sqlite3.IntegrityError:
                await interaction.response.send_message(
                    f"âŒ Emoji {emoji} is already used on this message!\n"
                    f"Remove it first with `/reactionrole remove {msg_id} {emoji}`",
                    ephemeral=True
                )
                conn.close()
                return
            
            channel = interaction.guild.get_channel(channel_id)
            message = await channel.fetch_message(msg_id)
            await message.add_reaction(emoji)
            
            c.execute('''
                SELECT emoji, role_id FROM emoji_reaction_pairs
                WHERE message_id = ?
            ''', (msg_id,))
            pairs = c.fetchall()
            conn.close()
            
            role_list = []
            for emoji_str, role_id in pairs:
                role_obj = interaction.guild.get_role(role_id)
                if role_obj:
                    role_list.append(f"{emoji_str} - {role_obj.mention}")
            
            embed = message.embeds[0] if message.embeds else discord.Embed()
            embed.clear_fields()
            if role_list:
                embed.add_field(name="Available Roles", value="\n".join(role_list), inline=False)
            await message.edit(embed=embed)
            
            await interaction.response.send_message(
                f"âœ… Added {emoji} â†’ {role.mention} to message `{msg_id}`!",
                ephemeral=True
            )
            log_command(interaction.guild.id, interaction.user.id, 'reactionrole_add')
            logger.info(f"Added emoji reaction role pair: {emoji} -> {role.name} on message {msg_id}")
            
        except ValueError:
            await interaction.response.send_message("âŒ Invalid message ID! Must be a number.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message(f"âŒ Could not find message with ID `{message_id}`", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"âŒ Error: {e}", ephemeral=True)
            logger.error(f"Error adding emoji reaction role: {e}")
    
    # REMOVE ROLE-REACTION PAIR
    elif action == "remove":
        if not message_id or not emoji:
            await interaction.response.send_message(
                "âŒ Usage: `/reactionrole remove [message_id] [emoji]`\n"
                "Example: `/reactionrole remove 123456789 ðŸŽ®`",
                ephemeral=True
            )
            return
        
        try:
            msg_id = int(message_id)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute('DELETE FROM emoji_reaction_pairs WHERE message_id = ? AND emoji = ?', (msg_id, emoji))
            
            if c.rowcount == 0:
                await interaction.response.send_message(
                    f"âŒ No role found for emoji {emoji} on message `{msg_id}`",
                    ephemeral=True
                )
                conn.close()
                return
            
            conn.commit()
            
            c.execute('SELECT channel_id FROM emoji_reaction_messages WHERE message_id = ?', (msg_id,))
            result = c.fetchone()
            conn.close()
            
            if result:
                channel = interaction.guild.get_channel(result[0])
                message = await channel.fetch_message(msg_id)
                await message.clear_reaction(emoji)
            
            await interaction.response.send_message(
                f"âœ… Removed {emoji} from message `{msg_id}`",
                ephemeral=True
            )
            log_command(interaction.guild.id, interaction.user.id, 'reactionrole_remove')
            logger.info(f"Removed emoji reaction role: {emoji} from message {msg_id}")
            
        except Exception as e:
            await interaction.response.send_message(f"âŒ Error: {e}", ephemeral=True)
            logger.error(f"Error removing emoji reaction role: {e}")
    
    # LIST ALL REACTION ROLE MESSAGES
    elif action == "list":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            SELECT message_id, channel_id, title, description, mode
            FROM emoji_reaction_messages
            WHERE guild_id = ?
        ''', (interaction.guild.id,))
        messages = c.fetchall()
        conn.close()
        
        if not messages:
            await interaction.response.send_message("âœ¨ No emoji reaction role messages found!", ephemeral=True)
            return
        
        embed = discord.Embed(title="ðŸŽ­ Emoji Reaction Role Messages", color=discord.Color.blue())
        
        for msg_id, channel_id, title_text, desc, mode_text in messages:
            channel = interaction.guild.get_channel(channel_id)
            channel_mention = channel.mention if channel else f"<#{channel_id}>"
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM emoji_reaction_pairs WHERE message_id = ?', (msg_id,))
            role_count = c.fetchone()[0]
            conn.close()
            
            embed.add_field(
                name=f"{title_text or 'Untitled'}",
                value=f"**ID:** `{msg_id}`\n"
                      f"**Channel:** {channel_mention}\n"
                      f"**Mode:** {mode_text}\n"
                      f"**Roles:** {role_count}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        log_command(interaction.guild.id, interaction.user.id, 'reactionrole_list')
    
    # DELETE REACTION ROLE MESSAGE
    elif action == "delete":
        if not message_id:
            await interaction.response.send_message(
                "âŒ Usage: `/reactionrole delete [message_id]`",
                ephemeral=True
            )
            return
        
        try:
            msg_id = int(message_id)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute('SELECT channel_id FROM emoji_reaction_messages WHERE message_id = ?', (msg_id,))
            result = c.fetchone()
            
            if not result:
                await interaction.response.send_message(
                    f"âŒ Message `{msg_id}` not found in database!",
                    ephemeral=True
                )
                conn.close()
                return
            
            c.execute('DELETE FROM emoji_reaction_messages WHERE message_id = ?', (msg_id,))
            conn.commit()
            conn.close()
            
            try:
                channel = interaction.guild.get_channel(result[0])
                message = await channel.fetch_message(msg_id)
                await message.delete()
            except:
                pass
            
            await interaction.response.send_message(
                f"âœ… Deleted reaction role message `{msg_id}`",
                ephemeral=True
            )
            log_command(interaction.guild.id, interaction.user.id, 'reactionrole_delete')
            logger.info(f"Deleted emoji reaction role message {msg_id}")
            
        except Exception as e:
            await interaction.response.send_message(f"âŒ Error: {e}", ephemeral=True)
    
    # EDIT REACTION ROLE MESSAGE
    elif action == "edit":
        if not message_id or not description:
            await interaction.response.send_message(
                "âŒ Usage: `/reactionrole edit [message_id] [description] [title]`",
                ephemeral=True
            )
            return
        
        try:
            msg_id = int(message_id)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute('''
                UPDATE emoji_reaction_messages
                SET description = ?, title = ?
                WHERE message_id = ?
            ''', (description, title, msg_id))
            
            if c.rowcount == 0:
                await interaction.response.send_message(
                    f"âŒ Message `{msg_id}` not found!",
                    ephemeral=True
                )
                conn.close()
                return
            
            conn.commit()
            
            c.execute('SELECT channel_id FROM emoji_reaction_messages WHERE message_id = ?', (msg_id,))
            channel_id = c.fetchone()[0]
            conn.close()
            
            channel = interaction.guild.get_channel(channel_id)
            message = await channel.fetch_message(msg_id)
            
            embed = discord.Embed(
                title=title or "Reaction Roles",
                description=description,
                color=discord.Color.blue()
            )
            embed.set_footer(text="Click reactions below to get roles!")
            
            await message.edit(embed=embed)
            
            await interaction.response.send_message(
                f"âœ… Updated message `{msg_id}`!",
                ephemeral=True
            )
            log_command(interaction.guild.id, interaction.user.id, 'reactionrole_edit')
            
        except Exception as e:
            await interaction.response.send_message(f"âŒ Error: {e}", ephemeral=True)
    
    # SET MODE
    elif action == "mode":
        if not message_id or not mode:
            await interaction.response.send_message(
                "âŒ Usage: `/reactionrole mode [message_id] [mode]`\n"
                "**Modes:** normal, unique, temporary, reversed",
                ephemeral=True
            )
            return
        
        valid_modes = ['normal', 'unique', 'temporary', 'reversed']
        if mode not in valid_modes:
            await interaction.response.send_message(
                f"âŒ Invalid mode! Use: {', '.join(valid_modes)}",
                ephemeral=True
            )
            return
        
        try:
            msg_id = int(message_id)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            c.execute('UPDATE emoji_reaction_messages SET mode = ? WHERE message_id = ?', (mode, msg_id))
            
            if c.rowcount == 0:
                await interaction.response.send_message(
                    f"âŒ Message `{msg_id}` not found!",
                    ephemeral=True
                )
                conn.close()
                return
            
            conn.commit()
            conn.close()
            
            mode_descriptions = {
                'normal': 'Users can have multiple roles',
                'unique': 'Users can only have ONE role (removes others)',
                'temporary': 'Roles removed when unreacted',
                'reversed': 'Toggle roles on/off'
            }
            
            await interaction.response.send_message(
                f"âœ… Set mode to **{mode}** for message `{msg_id}`\n"
                f"_{mode_descriptions[mode]}_",
                ephemeral=True
            )
            log_command(interaction.guild.id, interaction.user.id, 'reactionrole_mode')
            
        except Exception as e:
            await interaction.response.send_message(f"âŒ Error: {e}", ephemeral=True)
    
    else:
        await interaction.response.send_message(
            "âŒ Invalid action! Use: create, add, remove, list, delete, edit, or mode",
            ephemeral=True
        )

# ============================================================================
# WELCOMER SYSTEM
# ============================================================================

async def create_welcome_image(member: discord.Member, member_count: int) -> discord.File:
    """Generate a welcome card image with the member's avatar"""

    # Card dimensions
    W, H = 934, 282
    img = Image.new('RGBA', (W, H), (30, 31, 34, 255))  # Discord dark bg
    draw = ImageDraw.Draw(img)

    # ── Background gradient accent bar at top ──
    for y in range(4):
        draw.rectangle([0, y, W, y], fill=(88, 101, 242, 255))  # Blurple accent line

    # ── Try to load a nicer font, fall back to default ──
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except OSError:
        font_big = ImageFont.load_default()
        font_med = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # ── Download and paste avatar ──
    avatar_size = 128
    avatar_x, avatar_y = 60, (H - avatar_size) // 2

    try:
        async with aiohttp.ClientSession() as session:
            avatar_url = member.display_avatar.with_size(256).url
            async with session.get(str(avatar_url)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    avatar_img = Image.open(BytesIO(data)).convert('RGBA')
                    avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.LANCZOS)

                    # Make circular mask
                    mask = Image.new('L', (avatar_size, avatar_size), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse([0, 0, avatar_size, avatar_size], fill=255)

                    # Draw circle border (blurple ring)
                    ring_padding = 4
                    draw.ellipse(
                        [avatar_x - ring_padding, avatar_y - ring_padding,
                         avatar_x + avatar_size + ring_padding, avatar_y + avatar_size + ring_padding],
                        fill=(88, 101, 242, 255)
                    )

                    img.paste(avatar_img, (avatar_x, avatar_y), mask)
    except Exception as e:
        # If avatar fails, draw a placeholder circle
        draw.ellipse(
            [avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size],
            fill=(88, 101, 242, 255)
        )
        logger.error(f"Failed to load avatar for welcome card: {e}")

    # ── Text content ──
    text_x = avatar_x + avatar_size + 40
    text_y = 50

    # "WELCOME" header
    draw.text((text_x, text_y), "WELCOME", fill=(88, 101, 242, 255), font=font_big)

    # Username
    username = member.display_name
    if len(username) > 25:
        username = username[:22] + "..."
    draw.text((text_x, text_y + 45), username, fill=(255, 255, 255, 255), font=font_med)

    # Member count
    draw.text(
        (text_x, text_y + 80),
        f"You are member #{member_count}",
        fill=(148, 155, 164, 255),
        font=font_small
    )

    # Server name
    draw.text(
        (text_x, text_y + 110),
        member.guild.name,
        fill=(148, 155, 164, 255),
        font=font_small
    )

    # ── Decorative dots ──
    for i in range(3):
        dot_x = W - 60 + (i * 16)
        dot_y = H - 30
        draw.ellipse([dot_x, dot_y, dot_x + 8, dot_y + 8],
                     fill=(88, 101, 242, 80))

    # ── Save to buffer ──
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return discord.File(buffer, filename='welcome.png')


@bot.event
async def on_member_join(member: discord.Member):
    """Send welcome embed + image card when a new member joins"""
    if member.bot:
        return

    # Check if welcomer is enabled for this guild
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT channel_id, message, enabled, rules_channel, verify_channel, roles_channel FROM welcome_settings WHERE guild_id=?',
              (member.guild.id,))
    result = c.fetchone()
    conn.close()

    if not result or not result[2]:
        return

    channel_id, custom_message, _, rules_id, verify_id, roles_id = result
    channel = member.guild.get_channel(channel_id)
    if not channel:
        return

    member_count = member.guild.member_count

    # Format custom message
    welcome_text = custom_message.replace('{member}', member.mention) \
                                  .replace('{server}', member.guild.name) \
                                  .replace('{count}', str(member_count))

    # Channel mentions
    rules_mention = f"<#{rules_id}>" if rules_id else "#rules"
    verify_mention = f"<#{verify_id}>" if verify_id else "#verify-here"
    roles_mention = f"<#{roles_id}>" if roles_id else "#role-select"

    # ── Build embed ──
    embed = discord.Embed(
        title="\ud83d\udc4b Welcome to the server!",
        description=(
            f"{welcome_text}\n\n"
            f"You are member **#{member_count}**\n\n"
            f"\ud83d\udcdc Check out the rules in {rules_mention}\n"
            f"\u2705 Head to {verify_mention} to verify and unlock all channels\n"
            f"\ud83c\udfae Pick your game roles in {roles_mention}"
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{member.guild.name} \u2022 Enjoy your stay!")
    embed.timestamp = datetime.now()

    # ── Generate welcome image ──
    try:
        welcome_image = await create_welcome_image(member, member_count)
        embed.set_image(url="attachment://welcome.png")
        await channel.send(file=welcome_image, embed=embed)
    except Exception as e:
        logger.error(f"Welcome image failed, sending embed only: {e}")
        await channel.send(embed=embed)

    logger.info(f"Welcomed {member.name} to {member.guild.name} (member #{member_count})")


@bot.tree.command(name="setwelcome", description="Set up the welcome message for this channel (Admin)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    message="Custom welcome message. Use {member} for mention, {server} for server name, {count} for member #",
    rules_channel="Your #rules channel",
    verify_channel="Your #verify-here channel",
    roles_channel="Your #role-select channel"
)
async def setwelcome(
    interaction: discord.Interaction,
    rules_channel: discord.TextChannel,
    verify_channel: discord.TextChannel,
    roles_channel: discord.TextChannel,
    message: str = "Welcome to the server, {member}! \ud83c\udf89"
):
    """Set up welcomer in the current channel"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("\u274c Only admins can use this!", ephemeral=True)
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO welcome_settings 
                 (guild_id, channel_id, message, enabled, rules_channel, verify_channel, roles_channel)
                 VALUES (?, ?, ?, 1, ?, ?, ?)''',
              (interaction.guild.id, interaction.channel.id, message,
               rules_channel.id, verify_channel.id, roles_channel.id))
    conn.commit()
    conn.close()

    embed = discord.Embed(
        title="\u2705 Welcomer Enabled!",
        description=(
            f"**Channel:** {interaction.channel.mention}\n"
            f"**Message:** {message}\n\n"
            f"**Links in embed:**\n"
            f"\ud83d\udcdc Rules \u2192 {rules_channel.mention}\n"
            f"\u2705 Verify \u2192 {verify_channel.mention}\n"
            f"\ud83c\udfae Roles \u2192 {roles_channel.mention}\n\n"
            f"New members will see a welcome embed + image card here!"
        ),
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)
    log_command(interaction.guild.id, interaction.user.id, 'setwelcome')


@bot.tree.command(name="testwelcome", description="Preview the welcome message (Admin)")
@app_commands.default_permissions(administrator=True)
async def testwelcome(interaction: discord.Interaction):
    """Test the welcome message on yourself"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("\u274c Only admins can use this!", ephemeral=True)
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT channel_id, message, rules_channel, verify_channel, roles_channel FROM welcome_settings WHERE guild_id=?',
              (interaction.guild.id,))
    result = c.fetchone()
    conn.close()

    if not result:
        await interaction.response.send_message("\u274c Welcomer not set up! Use `/setwelcome` first.", ephemeral=True)
        return

    channel_id, custom_message, rules_id, verify_id, roles_id = result
    member = interaction.user
    member_count = interaction.guild.member_count

    welcome_text = custom_message.replace('{member}', member.mention) \
                                  .replace('{server}', member.guild.name) \
                                  .replace('{count}', str(member_count))

    rules_mention = f"<#{rules_id}>" if rules_id else "#rules"
    verify_mention = f"<#{verify_id}>" if verify_id else "#verify-here"
    roles_mention = f"<#{roles_id}>" if roles_id else "#role-select"

    embed = discord.Embed(
        title="\ud83d\udc4b Welcome to the server!",
        description=(
            f"{welcome_text}\n\n"
            f"You are member **#{member_count}**\n\n"
            f"\ud83d\udcdc Check out the rules in {rules_mention}\n"
            f"\u2705 Head to {verify_mention} to verify and unlock all channels\n"
            f"\ud83c\udfae Pick your game roles in {roles_mention}"
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{member.guild.name} \u2022 Enjoy your stay!")
    embed.timestamp = datetime.now()

    await interaction.response.defer()

    try:
        welcome_image = await create_welcome_image(member, member_count)
        embed.set_image(url="attachment://welcome.png")
        await interaction.followup.send(content="**\ud83d\udccb Welcome Preview:**", file=welcome_image, embed=embed)
    except Exception as e:
        logger.error(f"Welcome image test failed: {e}")
        await interaction.followup.send(content="**\ud83d\udccb Welcome Preview (image failed):**", embed=embed)


@bot.tree.command(name="disablewelcome", description="Disable the welcomer (Admin)")
@app_commands.default_permissions(administrator=True)
async def disablewelcome(interaction: discord.Interaction):
    """Disable welcomer"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("\u274c Only admins can use this!", ephemeral=True)
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE welcome_settings SET enabled=0 WHERE guild_id=?', (interaction.guild.id,))
    conn.commit()
    conn.close()

    await interaction.response.send_message("\u2705 Welcomer disabled!", ephemeral=True)
    log_command(interaction.guild.id, interaction.user.id, 'disablewelcome')


# ============================================================================
# EMOJI REACTION ROLE EVENT HANDLERS
# ============================================================================

@bot.event
async def on_raw_reaction_add(payload):
    """Handle emoji reaction additions"""
    if payload.user_id == bot.user.id:
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''
        SELECT mode FROM emoji_reaction_messages
        WHERE message_id = ? AND guild_id = ?
    ''', (payload.message_id, payload.guild_id))
    
    result = c.fetchone()
    if not result:
        conn.close()
        return
    
    mode = result[0]
    
    emoji_str = str(payload.emoji)
    c.execute('''
        SELECT role_id FROM emoji_reaction_pairs
        WHERE message_id = ? AND emoji = ?
    ''', (payload.message_id, emoji_str))
    
    role_result = c.fetchone()
    if not role_result:
        conn.close()
        return
    
    role_id = role_result[0]
    
    if mode == 'unique':
        c.execute('''
            SELECT role_id FROM emoji_reaction_pairs
            WHERE message_id = ?
        ''', (payload.message_id,))
        all_role_ids = [r[0] for r in c.fetchall()]
    
    conn.close()
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    
    member = guild.get_member(payload.user_id)
    if not member:
        return
    
    role = guild.get_role(role_id)
    if not role:
        return
    
    try:
        if mode == 'unique':
            for other_role_id in all_role_ids:
                if other_role_id != role_id:
                    other_role = guild.get_role(other_role_id)
                    if other_role and other_role in member.roles:
                        await member.remove_roles(other_role)
        
        if role not in member.roles:
            await member.add_roles(role)
            logger.info(f"Gave {role.name} to {member.name} via emoji reaction role")
        
    except Exception as e:
        logger.error(f"Error in emoji reaction role add: {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    """Handle emoji reaction removals"""
    if payload.user_id == bot.user.id:
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''
        SELECT mode FROM emoji_reaction_messages
        WHERE message_id = ? AND guild_id = ?
    ''', (payload.message_id, payload.guild_id))
    
    result = c.fetchone()
    if not result:
        conn.close()
        return
    
    mode = result[0]
    
    emoji_str = str(payload.emoji)
    c.execute('''
        SELECT role_id FROM emoji_reaction_pairs
        WHERE message_id = ? AND emoji = ?
    ''', (payload.message_id, emoji_str))
    
    role_result = c.fetchone()
    conn.close()
    
    if not role_result:
        return
    
    role_id = role_result[0]
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    
    member = guild.get_member(payload.user_id)
    if not member:
        return
    
    role = guild.get_role(role_id)
    if not role:
        return
    
    if mode in ['normal', 'temporary', 'reversed']:
        try:
            if role in member.roles:
                await member.remove_roles(role)
                logger.info(f"Removed {role.name} from {member.name} via emoji reaction role removal")
        except Exception as e:
            logger.error(f"Error in emoji reaction role remove: {e}")

# ============================================================================
# UTILITY COMMANDS
# ============================================================================

@bot.tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    """Display help information"""
    embed = discord.Embed(
        title="ðŸ¤– JarvisQueue - Full Feature Set",
        description="Complete command list",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="ðŸŽ® Queue Setup",
        value=(
            "`/setup` - Create queue\n"
            "`/startqueue` - Show queue interface\n"
            "`/clearqueue` - Clear queue\n"
            "`/lockqueue` `/unlockqueue` - Lock/unlock\n"
            "`/purge` - Clear channel messages"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ðŸ‘¥ User Management",
        value=(
            "`/adduser` `/removeuser` - Add/remove players\n"
            "`/blacklist` - Manage blacklist\n"
            "`/requiredrole` - Required roles\n"
            "`/staffroles` - Manage staff"
        ),
        inline=False
    )
    
    embed.add_field(
        name="âš™ï¸ Configuration",
        value=(
            "`/setteamsize` `/setteammode` - Team settings\n"
            "`/setcaptainmode` - Captain selection\n"
            "`/setmapvoting` `/addmap` `/removemap` - Maps\n"
            "`/addmap <queue> all` - Add all default maps\n"
            "`/setgamemode` - Set HP/SND/MIX mode\n"
            "`/resultschannel` - Results channel\n"
            "`/automove` `/createchannels` - Auto channels\n"
            "`/pingplayers` `/nametype` - Display settings\n"
            "`/rolelimit` - Role limits per match"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ðŸ† Matches & Results",
        value=(
            "`/reportwin` - Report winner\n"
            "`/cancelmatch` - Cancel match\n"
            "`/matchhistory` - View history\n"
            "`/viewmatch` - View match details\n"
            "`/modifyresult` - Change match result"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ðŸ“Š Stats & Rankings",
        value=(
            "`/stats` `/leaderboard` `/rank` - View stats\n"
            "`/compare` - Compare players\n"
            "`/recentmatches` - Player match history\n"
            "`/winstreak` - View win streaks\n"
            "`/setmmr` `/adjustmmr` - Adjust MMR\n"
            "`/resetstats` `/resetuser` - Reset stats\n"
            "`/ranks` `/rankadd` `/rankremove` - Auto-roles\n"
            "`/mmrdecay` `/graceperiod` - MMR decay"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ðŸ›¡ï¸ Teams/Clans",
        value=(
            "`/teamcreate` - Create team\n"
            "`/teaminvite` `/teamjoin` - Join team\n"
            "`/teamleave` `/teamdisband` - Leave/disband\n"
            "`/teamstats` - View team stats"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ðŸŽµ Music Player",
        value=(
            "`/join` `/leave` - Voice control\n"
            "`/play` `/skip` `/pause` `/resume` `/stop`\n"
            "`/nowplaying` `/musicqueue` - Queue info\n"
            "`/volume` `/loop` - Playback settings"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ðŸ“‹ Admin Tools",
        value=(
            "`/lobbydetails` - Lobby info template\n"
            "`/commandlog` `/activitylog` - View logs\n"
            "`/sync` - Sync commands"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ðŸŽ­ Button Reaction Roles",
        value=(
            "`/verify @role` - One-click verification setup\n"
            "`/rolepanel @role1 @role2...` - Role selection panel\n"
            "`/rolepaneladd` - Add role to a panel\n"
            "`/rolepanelremove` - Remove role from panel\n"
            "`/rolepaneldelete` - Delete a panel\n"
            "`/rolepanellist` - List all panels"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ðŸ˜€ Emoji Reaction Roles (Carl-bot Style)",
        value=(
            "`/reactionrole create` - Create reaction role message\n"
            "`/reactionrole add` - Add emoji-role pair\n"
            "`/reactionrole remove` - Remove emoji-role pair\n"
            "`/reactionrole list` - List all messages\n"
            "`/reactionrole delete` - Delete a message\n"
            "`/reactionrole edit` - Edit message text\n"
            "`/reactionrole mode` - Set mode (normal/unique/temporary/reversed)"
        ),
        inline=False
    )
    
    embed.set_footer(text="JarvisQueue - Complete Feature Set | Use buttons in queue messages!")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ping", description="Check bot responsiveness")
async def ping(interaction: discord.Interaction):
    """Test bot responsiveness"""
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"ðŸ“ Pong! Latency: {latency}ms", ephemeral=True)

@bot.tree.command(name="sync", description="Sync commands (Admin only)")
async def sync(interaction: discord.Interaction):
    """Manually sync slash commands"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("âŒ Only admins can use this command!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    try:
        synced = await bot.tree.sync()
        await interaction.followup.send(f'âœ… Synced {len(synced)} commands!')
    except Exception as e:
        await interaction.followup.send(f'âŒ Error: {e}')

# ============================================================================
# RUN BOT
# ============================================================================

if __name__ == "__main__":
    # ================================================
    # PASTE YOUR BOT TOKEN BETWEEN THE QUOTES BELOW
    # ================================================
    TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"
    # ================================================
    
    if TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE" or not TOKEN:
        # Fallback: try environment variable
        TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    if not TOKEN or TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        logger.error("DISCORD_BOT_TOKEN not set!")
        print("=" * 70)
        print("ERROR: Bot token not set!")
        print("=" * 70)
        print("Open jarvisqueue_full.py and paste your token at the bottom")
        print("on the line that says: TOKEN = \"PASTE_YOUR_BOT_TOKEN_HERE\"")
        print("=" * 70)
    else:
        logger.info("Starting JarvisQueue - Full Feature Set")
        logger.info(f"Python version: {os.sys.version}")
        logger.info(f"Discord.py version: {discord.__version__}")
        logger.info("=" * 70)
        try:
            bot.run(TOKEN)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.critical(f"Bot crashed: {e}", exc_info=True)
            raise

