# Vercel Deployment Guide - MLAI Slack Survey Bot

## 🚀 **Quick Deploy to Vercel**

### **1. Prerequisites**
- [Vercel Account](https://vercel.com) (free tier works)
- Slack workspace with admin access
- OpenAI API key
- Airtable account and API key

### **2. Environment Variables Setup**

In your Vercel project dashboard, add these environment variables:

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
ADMIN_USER_IDS=U1234567890,U0987654321
OPENAI_API_KEY=sk-your-openai-api-key-here
AIRTABLE_API_KEY=your-airtable-api-key-here
AIRTABLE_BASE_ID=your-airtable-base-id-here
AIRTABLE_TABLE=SlackUsers
AIRTABLE_COLUMN_NAME=SlackID
```

### **3. Deploy Steps**

1. **Fork/Clone** this repository to your GitHub account

2. **Connect to Vercel**:
   - Go to [vercel.com](https://vercel.com)
   - Click "Import Project"
   - Connect your GitHub repository
   - Select this project

3. **Configure Build Settings**:
   - **Framework Preset**: Other
   - **Build Command**: (leave empty)
   - **Output Directory**: (leave empty)
   - **Install Command**: `pip install -r requirements.txt`

4. **Add Environment Variables**:
   - In Vercel dashboard → Project → Settings → Environment Variables
   - Add all variables from step 2

5. **Deploy**: Click "Deploy" button

### **4. Slack App Configuration**

After deployment, update your Slack app endpoints:

1. **Event Subscriptions**:
   ```
   Request URL: https://your-app-name.vercel.app/slack/events
   ```

2. **Slash Commands** (`/trigger-survey`):
   ```
   Request URL: https://your-app-name.vercel.app/slack/commands
   ```

3. **Interactivity & Shortcuts**:
   ```
   Request URL: https://your-app-name.vercel.app/slack/events
   ```

### **5. Required Slack Bot Permissions**

Ensure your Slack app has these OAuth scopes:
- `chat:write`
- `im:write`
- `commands`
- `app_mentions:read`

### **6. Test Your Deployment**

1. **Health Check**: Visit `https://your-app-name.vercel.app/health`
2. **Admin Test**: Use `/trigger-survey` command in Slack
3. **Bot Mention**: Try mentioning `@YourBotName` in a channel

## 🔧 **Troubleshooting**

### **Common Issues**

**❌ "dispatch_failed" error**
- Check environment variables are set correctly in Vercel
- Verify Slack app endpoints match your Vercel URL

**❌ Import errors**
- Ensure `requirements.txt` includes all dependencies
- Check Python version compatibility (Vercel uses Python 3.9+)

**❌ Timeout issues**
- Vercel serverless functions have 10s timeout (hobby) / 60s (pro)
- The bot's 10-minute survey timeout works within these limits

### **Logs & Debugging**

1. **Vercel Logs**: Dashboard → Functions → View logs
2. **Slack Logs**: Your Slack app → Event Subscriptions → View requests
3. **Bot Logs**: Check console output in Vercel function logs

## 📊 **Vercel-Specific Features**

### **Automatic Scaling**
- Vercel automatically scales based on demand
- No server maintenance required
- Handles concurrent surveys efficiently

### **Environment Management**
- Use Vercel's environment variable system
- Different environments (preview/production) supported
- Secure storage of API keys

### **Domain & SSL**
- Automatic HTTPS with custom domains
- Built-in SSL certificates
- Global CDN for fast response times

## 🎯 **Production Checklist**

- [ ] All environment variables configured in Vercel
- [ ] Slack app endpoints updated to Vercel URLs  
- [ ] Admin user IDs properly set
- [ ] Airtable permissions configured
- [ ] Bot tested with `/trigger-survey` command
- [ ] App mention functionality verified
- [ ] Error handling tested

## 🔗 **Useful Links**

- [Vercel Python Documentation](https://vercel.com/docs/functions/serverless-functions/runtimes/python)
- [Slack Bolt Framework](https://slack.dev/bolt-python/tutorial/getting-started)
- [OpenAI API Docs](https://platform.openai.com/docs)
- [Airtable API Reference](https://airtable.com/developers/web/api/introduction)

---

**Deployment completed!** Your MLAI Slack Survey Bot is now running on Vercel! 🚀 