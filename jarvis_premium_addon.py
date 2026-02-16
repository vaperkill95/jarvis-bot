# ============================================================================
# JARVIS BOT - PREMIUM SYSTEM ADDON
# Add this code to your jarvis.py file
# ============================================================================

# Add this section after the database initialization (in init_db function):
"""
        # Premium users (Durable SKU purchases)
        c.execute('''CREATE TABLE IF NOT EXISTS premium_users (
            user_id INTEGER PRIMARY KEY,
            sku_id TEXT,
            purchased_at TEXT,
            entitlement_id TEXT,
            profile_color TEXT DEFAULT '#FFD700',
            profile_badge TEXT DEFAULT '👑',
            custom_title TEXT
        )''')
"""

# Add these helper functions after the database helper functions:

async def check_premium(user_id: int) -> bool:
    """Check if user has premium (Durable SKU)"""
    try:
        conn = sqlite3.connect('jarvisqueue_full.db')
        c = conn.cursor()
        c.execute('SELECT user_id FROM premium_users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        print(f"Error checking premium: {e}")
        return False

async def grant_premium(user_id: int, sku_id: str, entitlement_id: str):
    """Grant premium to a user"""
    try:
        conn = sqlite3.connect('jarvisqueue_full.db')
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO premium_users 
                     (user_id, sku_id, purchased_at, entitlement_id, profile_color, profile_badge)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (user_id, sku_id, datetime.utcnow().isoformat(), entitlement_id, '#FFD700', '👑'))
        conn.commit()
        conn.close()
        print(f"✅ Granted premium to user {user_id}")
    except Exception as e:
        print(f"Error granting premium: {e}")

async def revoke_premium(user_id: int):
    """Revoke premium from a user (if refunded)"""
    try:
        conn = sqlite3.connect('jarvisqueue_full.db')
        c = conn.cursor()
        c.execute('DELETE FROM premium_users WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        print(f"❌ Revoked premium from user {user_id}")
    except Exception as e:
        print(f"Error revoking premium: {e}")

def get_premium_settings(user_id: int) -> dict:
    """Get user's premium customization settings"""
    try:
        conn = sqlite3.connect('jarvisqueue_full.db')
        c = conn.cursor()
        c.execute('SELECT profile_color, profile_badge, custom_title FROM premium_users WHERE user_id = ?', 
                  (user_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            return {
                'color': result[0] or '#FFD700',
                'badge': result[1] or '👑',
                'title': result[2] or None
            }
        return None
    except Exception as e:
        print(f"Error getting premium settings: {e}")
        return None

def create_premium_profile_embed(user, stats: dict, is_premium: bool, premium_settings: dict = None):
    """Create a premium profile card with enhanced styling"""
    
    if is_premium and premium_settings:
        # Premium profile
        color = int(premium_settings['color'].replace('#', ''), 16)
        badge = premium_settings['badge']
        title = premium_settings['title'] or f"{badge} Premium Player"
        
        embed = discord.Embed(
            title=f"{title}",
            description=f"**{user.display_name}** • {user.mention}",
            color=color
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Premium badge in footer
        embed.set_footer(text=f"✨ Premium Member {badge}", 
                        icon_url="https://em-content.zobj.net/thumbs/120/twitter/351/crown_1f451.png")
    else:
        # Basic profile
        embed = discord.Embed(
            title=f"📊 Player Profile",
            description=f"**{user.display_name}** • {user.mention}",
            color=0x5865F2
        )
        embed.set_thumbnail(url=user.display_avatar.url)
    
    # Stats section
    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    games = wins + losses
    win_rate = (wins / games * 100) if games > 0 else 0
    mmr = stats.get('mmr', 1500)
    
    embed.add_field(
        name="📈 Statistics",
        value=(
            f"**MMR:** {mmr}\n"
            f"**Wins:** {wins}\n"
            f"**Losses:** {losses}\n"
            f"**Win Rate:** {win_rate:.1f}%"
        ),
        inline=True
    )
    
    embed.add_field(
        name="🎮 Performance",
        value=(
            f"**Games Played:** {games}\n"
            f"**Current Streak:** {stats.get('streak', 0)}\n"
            f"**Best Streak:** {stats.get('best_streak', 0)}"
        ),
        inline=True
    )
    
    if is_premium:
        # Show extended stats for premium users
        embed.add_field(
            name="⭐ Premium Stats",
            value=(
                f"**Avg MMR Gain:** +{stats.get('avg_gain', 25)}\n"
                f"**MVP Count:** {stats.get('mvp_count', 0)}\n"
                f"**Total Matches:** {games}"
            ),
            inline=False
        )
    else:
        # Add premium upgrade prompt if not premium
        embed.add_field(
            name="✨ Upgrade to Premium",
            value="Unlock premium profile card with custom colors, badges, and extended stats!\nUse `/premium` to learn more.",
            inline=False
        )
    
    return embed


# ============================================================================
# PREMIUM COMMANDS - Add these to your bot
# ============================================================================

@bot.tree.command(name="premium", description="✨ PREMIUM — View premium features and purchase")
async def premium_info(interaction: discord.Interaction):
    """Show premium features information"""
    is_premium = await check_premium(interaction.user.id)
    
    if is_premium:
        # User already has premium
        premium_settings = get_premium_settings(interaction.user.id)
        embed = discord.Embed(
            title="👑 You Have Premium!",
            description="Thank you for supporting Jarvis! You have access to all premium features.",
            color=0xFFD700
        )
        embed.add_field(
            name="✨ Your Premium Benefits",
            value=(
                "✅ Custom premium profile card\n"
                "✅ Exclusive premium badge 👑\n"
                "✅ Extended match history (50 matches)\n"
                "✅ Personalized color themes\n"
                "✅ Priority support\n"
                "✅ Permanent access"
            ),
            inline=False
        )
        embed.add_field(
            name="🎨 Your Settings",
            value=(
                f"**Badge:** {premium_settings['badge']}\n"
                f"**Color:** {premium_settings['color']}\n"
                f"**Custom Title:** {premium_settings['title'] or 'None set'}"
            ),
            inline=False
        )
        embed.add_field(
            name="⚙️ Customize Your Profile",
            value="Use `/premium_customize` to change your profile settings!",
            inline=False
        )
        embed.set_footer(text="✨ Premium Member")
    else:
        # User doesn't have premium - show purchase info
        embed = discord.Embed(
            title="✨ Upgrade to Premium!",
            description="Unlock exclusive features with a **one-time purchase** - yours forever!",
            color=0x5865F2
        )
        embed.add_field(
            name="🌟 Premium Features",
            value=(
                "👑 **Premium Profile Card**\n"
                "   Custom colors, badges, and styling\n\n"
                "📊 **Extended Statistics**\n"
                "   View last 50 matches instead of 10\n\n"
                "🎨 **Personalization**\n"
                "   Custom colors, badges, and titles\n\n"
                "⚡ **Priority Support**\n"
                "   Get help faster from our team\n\n"
                "♾️ **One-Time Purchase**\n"
                "   Pay once, keep forever!"
            ),
            inline=False
        )
        embed.add_field(
            name="💰 Pricing",
            value="**$4.99 USD** - One-time payment, lifetime access!",
            inline=False
        )
        embed.add_field(
            name="🔗 Purchase Link",
            value="[Click here to purchase premium](https://discord.com/application-directory/1465488984254714010)",
            inline=False
        )
        embed.set_footer(text="Questions? Join our support server!")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="premium_customize", description="🎨 PREMIUM — Customize your premium profile")
@app_commands.describe(
    color="Hex color code (e.g., #FFD700)",
    badge="Emoji for your profile badge",
    title="Custom title for your profile"
)
async def premium_customize(
    interaction: discord.Interaction,
    color: str = None,
    badge: str = None,
    title: str = None
):
    """Customize premium profile settings"""
    is_premium = await check_premium(interaction.user.id)
    
    if not is_premium:
        embed = discord.Embed(
            title="❌ Premium Required",
            description="This command is only available for premium members!\nUse `/premium` to learn more.",
            color=0xFF0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Validate and update settings
    updates = []
    
    if color:
        # Validate hex color
        if not color.startswith('#') or len(color) != 7:
            await interaction.response.send_message("❌ Invalid color! Use format: #FFD700", ephemeral=True)
            return
        try:
            int(color[1:], 16)  # Test if valid hex
            updates.append(('profile_color', color))
        except ValueError:
            await interaction.response.send_message("❌ Invalid hex color code!", ephemeral=True)
            return
    
    if badge:
        # Limit to 2 characters (emoji)
        if len(badge) > 2:
            await interaction.response.send_message("❌ Badge must be a single emoji!", ephemeral=True)
            return
        updates.append(('profile_badge', badge))
    
    if title:
        # Limit title length
        if len(title) > 50:
            await interaction.response.send_message("❌ Title too long! Max 50 characters.", ephemeral=True)
            return
        updates.append(('custom_title', title))
    
    if not updates:
        await interaction.response.send_message("❌ Please provide at least one setting to update!", ephemeral=True)
        return
    
    # Update database
    try:
        conn = sqlite3.connect('jarvisqueue_full.db')
        c = conn.cursor()
        
        for column, value in updates:
            c.execute(f'UPDATE premium_users SET {column} = ? WHERE user_id = ?', (value, interaction.user.id))
        
        conn.commit()
        conn.close()
        
        # Show updated profile
        settings = get_premium_settings(interaction.user.id)
        embed = discord.Embed(
            title="✅ Premium Profile Updated!",
            description="Your settings have been saved.",
            color=int(settings['color'].replace('#', ''), 16)
        )
        embed.add_field(
            name="Current Settings",
            value=(
                f"**Badge:** {settings['badge']}\n"
                f"**Color:** {settings['color']}\n"
                f"**Title:** {settings['title'] or 'None'}"
            )
        )
        embed.set_footer(text="Use /stats to see your new profile!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Error updating premium settings: {e}")
        await interaction.response.send_message("❌ Failed to update settings. Please try again.", ephemeral=True)


@bot.tree.command(name="premium_admin", description="👑 ADMIN — Manually grant/revoke premium")
@app_commands.describe(
    action="Grant or revoke premium",
    user="User to modify"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Grant Premium", value="grant"),
    app_commands.Choice(name="Revoke Premium", value="revoke"),
    app_commands.Choice(name="Check Status", value="check")
])
async def premium_admin(interaction: discord.Interaction, action: str, user: discord.User):
    """Admin command to manage premium status"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only admins can use this command!", ephemeral=True)
        return
    
    if action == "grant":
        await grant_premium(user.id, "manual_grant", "admin_override")
        await interaction.response.send_message(f"✅ Granted premium to {user.mention}!", ephemeral=True)
    elif action == "revoke":
        await revoke_premium(user.id)
        await interaction.response.send_message(f"❌ Revoked premium from {user.mention}!", ephemeral=True)
    elif action == "check":
        is_premium = await check_premium(user.id)
        status = "✅ Has Premium" if is_premium else "❌ No Premium"
        await interaction.response.send_message(f"{user.mention}: {status}", ephemeral=True)
