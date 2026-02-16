# 🌟 Quick Reference: Discord Durable SKU Setup

## Fill Out Your SKU Form:

### Basic Information:
```
SKU Type: ✅ Durable (one-time purchase)

SKU Name (internal): jarvis_premium_profile

Display Name (users see): 🌟 Premium Profile Card

Price: $4.99 USD
```

### Description (what users see):
```
Unlock a premium profile card with custom styling and advanced stats! 
One-time purchase, yours forever.
```

### Benefits (detailed list):
```
✨ Custom premium profile card design
👑 Exclusive premium badge  
📊 Extended match history (50 matches)
🎨 Personalized color themes
⚡ Priority support
♾️ One-time purchase - yours forever!
```

### Additional Settings:
```
Tax Category: Digital Goods
Age Restriction: None (or 13+ if your bot requires)
Refund Policy: Follow Discord's standard refund policy
```

---

## After Creating SKU:

1. ✅ **Copy your SKU ID** - you'll need this for the code
2. ✅ **Enable Test Mode** - test purchases before going live
3. ✅ **Add the premium code** to your bot (see jarvis_premium_addon.py)
4. ✅ **Update `/stats` command** to use premium profiles
5. ✅ **Test with `/premium_admin grant`** command first
6. ✅ **Add purchase link** to your website and `/premium` command

---

## Your Purchase Link:

```
https://discord.com/application-directory/1465488984254714010
```

Users can click this to purchase premium directly from Discord!

---

## New Commands Added:

| Command | Description |
|---------|-------------|
| `/premium` | View premium info and purchase link |
| `/premium_customize` | Customize colors, badge, title (premium only) |
| `/premium_admin` | Grant/revoke premium manually (admin only) |

---

## Premium Features At A Glance:

**Visual:**
- Custom profile card colors (any hex code)
- Custom emoji badge (any emoji)
- Custom profile title (up to 50 chars)
- Premium footer badge

**Functional:**
- Extended match history (50 vs 10 matches)
- Premium stats section
- Priority support badge

**Lifetime:**
- One-time $4.99 payment
- Keep forever (Durable SKU)
- No subscriptions

---

## Testing Steps:

1. Use `/premium_admin grant @yourself`
2. Check `/stats` - should show premium styling
3. Use `/premium_customize color:#FFD700 badge:👑 title:Bot Owner`
4. Check `/stats` again - should show your custom settings
5. Use `/premium` - should show "You Have Premium!" message

---

## Going Live Checklist:

- [ ] SKU created in Discord Developer Portal
- [ ] SKU ID added to code
- [ ] Premium code added to jarvis.py
- [ ] Database table created (premium_users)
- [ ] Tested with admin command
- [ ] Entitlement events working
- [ ] Purchase link added to `/premium` command
- [ ] Announcement ready for Discord server
- [ ] Documentation updated

---

## Revenue Info:

- **Discord's Cut:** 10-15%
- **Your Share:** 85-90%
- **Example:** $4.99 SKU = ~$4.25 to you per sale
- **Payout:** Via Discord's payment system (monthly)

---

## Support Resources:

- **Discord Monetization Docs:** https://discord.com/developers/docs/monetization/overview
- **SKU Types Explained:** https://discord.com/developers/docs/monetization/skus
- **Entitlements API:** https://discord.com/developers/docs/monetization/entitlements

---

**Ready to launch? Follow the PREMIUM_SETUP_GUIDE.md for detailed instructions!** 🚀
