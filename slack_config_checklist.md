# Slack App Configuration Checklist for Message Events

## ✅ **Step 1: Event Subscriptions**
Go to [api.slack.com/apps](https://api.slack.com/apps) → Your App → **Event Subscriptions**

- [ ] **Enable Events** is turned **ON**
- [ ] **Request URL** is set to: `https://your-app-name-xxxxx.ondigitalocean.app/slack/events`
- [ ] Request URL shows **"Verified ✓"** (green checkmark)

## ✅ **Step 2: Subscribe to Bot Events**
In the **"Subscribe to bot events"** section, you should have:

- [ ] `message.channels` - Messages in public channels
- [ ] `message.groups` - Messages in private channels  
- [ ] `message.im` - Direct messages
- [ ] `message.mpim` - Group direct messages

## ✅ **Step 3: OAuth & Permissions**
Go to **OAuth & Permissions** and verify these scopes:

**Bot Token Scopes:**
- [ ] `channels:history` - View messages in public channels
- [ ] `groups:history` - View messages in private channels
- [ ] `im:history` - View messages in direct messages
- [ ] `mpim:history` - View messages in group direct messages
- [ ] `users:read` - Read user information
- [ ] `chat:write` - Send messages
- [ ] `commands` - Slash commands

## ✅ **Step 4: App Installation**
- [ ] App is **installed to workspace**
- [ ] After adding new scopes/events, you clicked **"Reinstall to Workspace"**

## ✅ **Step 5: Bot Presence in Channels**
- [ ] Bot is **invited to test channel** (use `/invite @pesto`)
- [ ] Bot appears in channel member list
- [ ] Bot is **online/active** (green dot in Slack)

## ✅ **Step 6: DigitalOcean App Status**
- [ ] DigitalOcean app is **running** (not paused/crashed)
- [ ] Latest code with message handlers is **deployed**
- [ ] Environment variables are **properly set** (especially NEO4J_* variables)

## ✅ **Step 7: Test Message**
Send a test message in a channel where the bot is present:

**Expected in DigitalOcean logs:**
```
🚨 DEBUG: Raw message event received: {...}
🔍 DEBUG: Message event received! Event keys: [...]
📨 Message received in channel...
👤 User info: ...
🧠 Extracted topics: ...
```

## 🚨 **Troubleshooting**

**If you see NO debug output:**
1. Check Slack Event Subscriptions URL is correct
2. Verify bot is invited to the channel
3. Check DigitalOcean app is running and deployed

**If you see "Request URL failed":**
1. Check DigitalOcean app is running
2. Verify URL format: `https://your-app.ondigitalocean.app/slack/events`
3. Check app logs for startup errors

**If events are received but handler doesn't trigger:**
1. Check for message `subtype` (our handler ignores subtypes)
2. Verify message has `text` content
3. Check for bot messages (ignored automatically)

## 📋 **Quick Test Commands**

**In Slack:**
1. `/invite @pesto` (invite bot to channel)
2. `Hello world this is a test message` (simple text message)
3. Check DigitalOcean Runtime Logs immediately

**Expected Response:**
- Should see debug logs within 1-2 seconds
- Should see topic extraction attempt
- Should see Neo4j update (if topics found) 