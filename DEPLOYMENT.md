# DigitalOcean App Platform Deployment Guide - MLAI Slack Survey Bot

## 🚀 **Quick Deploy to DigitalOcean**

### **1. Prerequisites**
- [DigitalOcean Account](https://digitalocean.com) (free $200 credit available)
- GitHub repository with your bot code
- Slack workspace with admin access
- OpenAI API key
- Airtable account and API key

### **2. Environment Variables Setup**

You'll need these environment variables for DigitalOcean App Platform:

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

#### **Step 1: Prepare Repository**
1. **Push your code** to GitHub (this repository)
2. **Ensure all files** are committed:
   - `app.py` - Main application
   - `prompts.py` - AI conversation logic
   - `requirements.txt` - Dependencies
   - `.env.example` - Environment template

#### **Step 2: Create DigitalOcean App**
1. **Login to DigitalOcean** → [Apps Console](https://cloud.digitalocean.com/apps)
2. **Click "Create App"**
3. **Choose "GitHub"** as source
4. **Select your repository** and branch (main)
5. **Choose "Autodeploy"** for automatic updates

#### **Step 3: Configure Build Settings**
DigitalOcean will auto-detect your Python app. Verify these settings:

- **Source Directory**: `/` (root)
- **Build Command**: `pip install -r requirements.txt`
- **Run Command**: `python app.py`
- **Port**: `3000` (auto-detected from your code)

#### **Step 4: Add Environment Variables**
In the DigitalOcean App settings:
1. **Go to "Settings" tab**
2. **Click "App-Level Environment Variables"**
3. **Add all variables** from step 2 above
4. **Make sure to encrypt sensitive values**

#### **Step 5: Deploy**
1. **Click "Create Resources"**
2. **Wait for deployment** (usually 3-5 minutes)
3. **Get your app URL** (format: `https://your-app-name-xxxxx.ondigitalocean.app`)

### **4. Slack App Configuration**

After deployment, update your Slack app endpoints with your DigitalOcean URL:

#### **Event Subscriptions**:
```
Request URL: https://your-app-name-xxxxx.ondigitalocean.app/slack/events
```

#### **Slash Commands** (`/trigger-survey`):
```
Request URL: https://your-app-name-xxxxx.ondigitalocean.app/slack/commands
```

#### **Interactivity & Shortcuts**:
```
Request URL: https://your-app-name-xxxxx.ondigitalocean.app/slack/events
```

### **5. Required Slack Bot Permissions**

Ensure your Slack app has these OAuth scopes:
- `chat:write` - Send messages
- `im:write` - Send direct messages
- `commands` - Slash commands
- `app_mentions:read` - Handle mentions

### **6. Test Your Deployment**

1. **Check App Status**: DigitalOcean Apps console should show "Running"
2. **Test Slack Command**: Use `/trigger-survey` in your Slack workspace
3. **Test Bot Mention**: Try mentioning `@YourBotName` in a channel
4. **Check Logs**: Monitor deployment logs in DigitalOcean console

## 🔧 **DigitalOcean-Specific Features**

### **Automatic Scaling**
- DigitalOcean automatically scales your app based on traffic
- No manual server management required
- Built-in load balancing for high availability

### **Continuous Deployment**
- **Auto-deploy** from GitHub on every push to main branch
- **Build logs** available in real-time
- **Rollback** to previous deployments with one click

### **Monitoring & Logs**
- **Real-time logs** accessible from DigitalOcean console
- **Performance metrics** and resource usage
- **Health checks** and uptime monitoring

## 💰 **Pricing**

### **Basic Plan** ($5/month):
- **512MB RAM / 1 vCPU**
- Perfect for development and light usage
- Handles dozens of concurrent surveys

### **Professional Plan** ($12/month):
- **1GB RAM / 1 vCPU**
- Recommended for production
- Handles hundreds of concurrent users

## 🔧 **Troubleshooting**

### **Common Issues**

**❌ App won't start**
- Check environment variables are set correctly
- Verify `requirements.txt` includes all dependencies
- Check deployment logs for Python errors

**❌ Slack endpoints not responding**
- Ensure your app URL is correct in Slack app settings
- Verify app is "Running" in DigitalOcean console
- Check firewall/security settings

**❌ OpenAI API errors**
- Verify `OPENAI_API_KEY` is set correctly
- Check OpenAI API quota and billing
- Monitor app logs for specific error messages

### **Logs & Debugging**

1. **DigitalOcean Logs**: Apps → Your App → Runtime Logs
2. **Slack Request Logs**: Your Slack App → Event Subscriptions → Request Logs
3. **Real-time Monitoring**: Apps → Your App → Insights

### **Performance Optimization**

- **Monitor memory usage** in DigitalOcean Insights
- **Scale up** if you see high CPU/memory usage
- **Enable auto-scaling** for variable traffic

## 🎯 **Production Checklist**

- [ ] All environment variables configured
- [ ] Slack app endpoints updated to DigitalOcean URL
- [ ] Admin user IDs properly set
- [ ] Airtable permissions configured
- [ ] Bot tested with `/trigger-survey` command
- [ ] App mention functionality verified
- [ ] Auto-deployment from GitHub enabled
- [ ] Monitoring and alerts configured

## 🔗 **Useful Links**

- [DigitalOcean Apps Documentation](https://docs.digitalocean.com/products/app-platform/)
- [Slack Bolt Framework](https://slack.dev/bolt-python/tutorial/getting-started)
- [OpenAI API Docs](https://platform.openai.com/docs)
- [Airtable API Reference](https://airtable.com/developers/web/api/introduction)

## 🚀 **Advantages of DigitalOcean vs Other Platforms**

### **vs Heroku**
- ✅ **Better pricing** - $5/month vs $7/month for similar specs
- ✅ **No sleep mode** - Apps stay running 24/7
- ✅ **Better performance** - Dedicated resources

### **vs Vercel**
- ✅ **No serverless constraints** - Full Python application support
- ✅ **Persistent storage** - In-memory state maintained
- ✅ **Longer execution times** - No 10-second timeout limits

### **vs AWS/GCP**
- ✅ **Simpler setup** - No complex configuration needed
- ✅ **Transparent pricing** - Fixed monthly cost
- ✅ **Better developer experience** - GitHub integration

---

**Deployment completed!** Your MLAI Slack Survey Bot is now running on DigitalOcean! 🚀

### **Next Steps:**
1. **Monitor performance** in DigitalOcean console
2. **Test survey workflows** with real users
3. **Set up alerts** for downtime or errors
4. **Scale resources** as your community grows 