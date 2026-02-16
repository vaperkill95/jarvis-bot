# 🌟 Jarvis Bot - Premium System Setup Guide

## Overview

This guide will help you set up the premium (Durable SKU) system for your Jarvis Discord bot. Premium gives users a **one-time purchase** option for exclusive features like custom profile cards.

---

## 📋 Prerequisites

- Discord Bot is set up and running
- Access to Discord Developer Portal
- Admin access to your bot's application

---

## Step 1: Create Durable SKU in Discord Developer Portal

### 1.1 Go to Discord Developer Portal

1. Visit: https://discord.com/developers/applications
2. Select your Jarvis bot application
3. Click on **"Monetization"** in the left sidebar

### 1.2 Create SKU

1. Click **"Create SKU"**
2. Fill in the details:

```
SKU Type: Durable
SKU Name: jarvis_premium_profile
Display Name: 🌟 Premium Profile Card
Price: $4.99 USD

Description:
Unlock a premium profile card with custom styling and advanced stats! One-time purchase, yours forever.

Benefits:
✨ Custom premium profile card design
👑 Exclusive premium badge
📊 Extended match history (50 matches)
🎨 Personalized color themes
⚡ Priority support
♾️ One-time purchase - yours forever!
```

3. Click **"Create"**
4. **IMPORTANT:** Note down your SKU ID - you'll need this!

---

## Step 2: Add Premium Code to Your Bot

### 2.1 Update Database

Add this to your `init_db()` function (after the other table creations):

```python
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
```

### 2.2 Add Premium Functions

Copy all the functions from `jarvis_premium_addon.py` into your `jarvis.py` file:

- `check_premium()`
- `grant_premium()`
- `revoke_premium()`
- `get_premium_settings()`
- `create_premium_profile_embed()`

### 2.3 Add Premium Commands

Add these slash commands:

- `/premium` - View premium info and purchase link
- `/premium_customize` - Customize premium profile (color, badge, title)
- `/premium_admin` - Admin command to grant/revoke premium

---

## Step 3: Update the /stats Command

### Replace the current /stats command with the premium-aware version:

```python
@bot.tree.command(name="stats", description="📊 STATS — View player statistics")
@app_commands.describe(user="User to check", queue_name="Specific queue (optional)")
async def stats(interaction: discord.Interaction, user: discord.Member = None, queue_name: str = None):
    target_user = user or interaction.user
    
    # Check if user has premium
    is_premium = await check_premium(target_user.id)
    premium_settings = get_premium_settings(target_user.id) if is_premium else None
    
    # Get stats and create premium embed
    if queue_name:
        stats_data = get_queue_player_stats(target_user.id, interaction.guild.id, queue_name)
        stats_dict = {
            'mmr': stats_data['mmr'],
            'wins': stats_data['wins'],
            'losses': stats_data['losses'],
            'games': stats_data['games_played'],
            'streak': 0,
            'best_streak': 0
        }
    else:
        player = get_or_create_player(target_user.id, target_user.name)
        stats_dict = {
            'mmr': player['mmr'],
            'wins': player['wins'],
            'losses': player['losses'],
            'games': player['total_games'],
            'streak': player['win_streak'],
            'best_streak': player['win_streak']
        }
    
    embed = create_premium_profile_embed(target_user, stats_dict, is_premium, premium_settings)
    await interaction.response.send_message(embed=embed)
```

---

## Step 4: Handle Premium Purchases (Discord Entitlements)

Discord will automatically handle payments, but you need to listen for entitlement events:

### Add this event handler to your bot:

```python
@bot.event
async def on_entitlement_create(entitlement):
    """Handle new premium purchases"""
    if entitlement.sku_id == "YOUR_SKU_ID_HERE":  # Replace with your actual SKU ID
        await grant_premium(entitlement.user_id, entitlement.sku_id, str(entitlement.id))
        
        # Notify user
        try:
            user = await bot.fetch_user(entitlement.user_id)
            embed = discord.Embed(
                title="🎉 Premium Activated!",
                description="Thank you for purchasing Jarvis Premium!",
                color=0xFFD700
            )
            embed.add_field(
                name="✨ You now have access to:",
                value=(
                    "• Custom premium profile card\n"
                    "• Exclusive premium badge\n"
                    "• Extended statistics\n"
                    "• Custom colors and themes\n"
                    "• Priority support"
                )
            )
            embed.add_field(
                name="🎨 Get Started",
                value="Use `/premium_customize` to personalize your profile!\nUse `/stats` to see your new premium card!",
                inline=False
            )
            await user.send(embed=embed)
        except:
            pass

@bot.event
async def on_entitlement_delete(entitlement):
    """Handle refunded purchases"""
    if entitlement.sku_id == "YOUR_SKU_ID_HERE":
        await revoke_premium(entitlement.user_id)
```

---

## Step 5: Test Your Premium System

### 5.1 Test with Admin Command

1. Use `/premium_admin grant @YourTestUser`
2. Check `/stats @YourTestUser` - should show premium profile
3. Use `/premium_customize color:#FF0000 badge:⭐`
4. Check `/stats` again - should show new colors

### 5.2 Test Purchase Flow (Discord Test Mode)

1. Discord Developer Portal → Monetization → Test Mode
2. Add test users
3. Test users can "purchase" for free
4. Verify entitlement events trigger correctly

---

## Step 6: Go Live!

### 6.1 Submit for Approval (if required)

1. Discord may require app review for monetization
2. Submit your bot for review
3. Wait for approval

### 6.2 Announce Premium

Create an announcement in your support server:

```
🌟 **Premium is Here!**

Jarvis now offers premium features! Support the bot and unlock:

👑 Custom Premium Profile Card
📊 Extended Statistics  
🎨 Personalized Themes
⚡ Priority Support
♾️ One-Time Purchase - Yours Forever!

**$4.99 USD** - Purchase in the app directory!

Use `/premium` to learn more!
```

---

## Commands Reference

| Command | Description | Who Can Use |
|---------|-------------|-------------|
| `/premium` | View premium info and purchase | Everyone |
| `/premium_customize` | Customize profile colors/badge/title | Premium users only |
| `/premium_admin` | Grant/revoke premium manually | Admins only |
| `/stats` | View stats (shows premium profile if owned) | Everyone |

---

## Premium Features

### For Users:
- ✅ Custom profile card with personalized colors
- ✅ Exclusive premium badge (customizable emoji)
- ✅ Custom profile title
- ✅ Extended match history (50 vs 10 matches)
- ✅ Premium badge on leaderboards
- ✅ Priority support

### For You (Bot Owner):
- 💰 **Revenue share**: Discord takes 10-15%, you keep 85-90%
- 📊 **Analytics**: Track purchases in Discord Dev Portal
- 🎯 **No recurring billing**: Users pay once, keep forever
- 🤝 **Discord handles payments**: No payment processing needed

---

## Pricing Strategy

**Recommended: $4.99 USD**

Why this price?
- Not too high to scare away users
- Not too low to devalue the features
- Sweet spot for impulse purchases
- Competitive with other bot premiums

**Alternative Pricing:**
- **$2.99** - Budget tier (more volume, less per sale)
- **$7.99** - Premium tier (fewer sales, more per sale)

---

## Marketing Tips

1. **Show, Don't Tell**: Post screenshots of premium profiles
2. **Free Trial**: Use `/premium_admin` to grant 1-day trials
3. **Leaderboard Badge**: Premium users get special badge
4. **Social Proof**: "Join 50+ premium members!"
5. **Limited Features**: Keep some features premium-only to create value

---

## Troubleshooting

### Premium not activating after purchase?
- Check entitlement event fired: Look in bot logs
- Verify SKU ID matches in code
- Test with `/premium_admin grant` first

### Profile not showing premium styling?
- Check `/premium` - verify user has premium
- Clear Discord cache (Ctrl+Shift+R)
- Restart bot to reload database

### Can't customize profile?
- Verify premium status with `/premium_admin check`
- Check color format is `#RRGGBB` (hex)
- Badge must be single emoji (2 chars max)

---

## Support

Need help? Join our support server: [Your Discord Server Link]

Questions about Discord monetization? Check Discord's docs:
https://discord.com/developers/docs/monetization/overview

---

## Legal Notes

- **Tax Compliance**: You're responsible for taxes on earnings
- **Refund Policy**: Discord handles refunds (results in entitlement_delete event)
- **Terms of Service**: Create clear terms for premium features
- **Privacy**: Store minimal user data (user_id, settings only)

---

**🎉 Congratulations! Your premium system is ready to launch!**

Remember to:
1. Test thoroughly before going live
2. Create clear documentation for users
3. Monitor entitlement events in logs
4. Engage with your premium community

Good luck with your bot monetization! 🚀
