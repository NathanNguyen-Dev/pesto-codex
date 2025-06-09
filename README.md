# MLAI Slack Survey Bot

A conversational survey bot for the MLAI community built with Slack Bolt SDK, OpenAI GPT-4o-mini, and Airtable integration.

## 📋 **Overview**

This bot conducts natural, conversational surveys with MLAI community members to gather insights about:
- **Motivation**: Why they joined the MLAI community
- **Goals**: Their expectations and objectives from the community

The bot uses AI to have natural conversations (3-4 exchanges) and automatically saves responses to Airtable.

## 🏗️ **Architecture**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Slack       │    │   Python Bot    │    │    Airtable    │
│   Workspace     │◄──►│   Application   │◄──►│   Database      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                               │
                               ▼
                       ┌─────────────────┐
                       │   OpenAI API    │
                       │   (GPT-4o-mini) │
                       └─────────────────┘
```

### **Core Components**

#### **1. Slack Integration (`app.py`)**
- **Admin Commands**: `/trigger-survey` slash command for authorized users
- **Button Interactions**: Survey start button handling
- **Message Processing**: Natural conversation flow with users
- **DM Management**: Direct message routing and conversation threading

#### **2. AI Conversation Engine (`prompts.py`)**
- **Natural Language Processing**: OpenAI GPT-4o-mini for conversational responses
- **Conversation Flow**: Guided 3-4 exchange conversations
- **Topic Coverage**: Ensures both motivation and goals topics are covered
- **Auto-Completion**: Detects when sufficient information is gathered

#### **3. Data Storage**
- **Airtable Integration**: Stores full conversation logs
- **User Tracking**: Maps Slack User IDs to survey responses
- **Conversation State**: In-memory tracking of active surveys

#### **4. Admin Controls**
- **User Authorization**: Admin-only access to survey triggers
- **Bulk Operations**: Send surveys to specific Airtable tables
- **Test Mode**: Single-user testing capability

## 🚀 **Features**

### **Survey Management**
- ✅ Admin-only survey triggering via slash commands
- ✅ Bulk messaging to users from Airtable tables
- ✅ Test mode for single-user testing
- ✅ Custom table and column support

### **Conversation Flow**
- ✅ Natural, AI-powered conversations
- ✅ 3-4 exchange limit for efficiency
- ✅ Automatic topic coverage detection
- ✅ 10-minute timeout with auto-save
- ✅ Conversation state tracking

### **Data Management**
- ✅ Full conversation logging to Airtable
- ✅ User ID mapping and record updates
- ✅ Automatic response saving
- ✅ Error handling and retry logic

## 🛠️ **Setup**

### **Prerequisites**
- Python 3.13+
- Slack workspace with bot permissions
- OpenAI API key
- Airtable account and API key

### **Installation**

1. **Clone the repository**
```bash
git clone <repository-url>
cd pesto-codex
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Environment Configuration**
Create a `.env` file with:
```env
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret

# Admin User IDs (comma-separated)
ADMIN_USER_IDS=U1234567890,U0987654321

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key

# Airtable Configuration
AIRTABLE_API_KEY=your-airtable-api-key
AIRTABLE_BASE_ID=your-base-id
AIRTABLE_TABLE=SlackUsers
AIRTABLE_COLUMN_NAME=SlackID
```

4. **Slack App Setup**
- Create a Slack app in your workspace
- Enable Bot Token Scopes: `chat:write`, `im:write`, `commands`
- Add slash command: `/trigger-survey`
- Install app to workspace

### **Running the Bot**

**Local Development:**
```bash
python app.py
```

**Vercel Deployment:**
See [DEPLOYMENT.md](DEPLOYMENT.md) for complete Vercel deployment guide.

## 📖 **Usage**

### **Admin Commands**

#### **Trigger Survey**
```
/trigger-survey <table_id> [test|all] [column_name]
```

**Examples:**
```bash
# Test mode - send to first user only
/trigger-survey tbl123ABC456DEF test

# Send to all users in table
/trigger-survey tbl123ABC456DEF all

# Use custom column name
/trigger-survey tbl123ABC456DEF test UserSlackID
```

### **Survey Flow**

1. **Admin triggers** survey via slash command
2. **Bot sends DM** with survey invitation and button
3. **User clicks button** to start survey
4. **Natural conversation** begins (3-4 exchanges)
5. **Bot automatically completes** when sufficient info gathered
6. **Responses saved** to Airtable

## 🔧 **Technical Details**

### **Message Handling**
```python
# Channel type detection ensures DM-only conversations
if channel_type != "im":
    safe_dm(user_id, "Let's continue this conversation in DM 😊")
    return
```

### **Conversation State Management**
```python
conversation_state = {
    "user_id": {
        "step": "started|completed",
        "conversation_history": [],
        "start_time": datetime,
    }
}
```

### **AI Prompt System**
- **System Prompt**: Guides conversation behavior and completion criteria
- **Context Awareness**: Maintains conversation flow and references
- **Completion Detection**: Automatically ends when both topics covered

### **Error Handling**
- **Rate Limiting**: Exponential backoff for Slack API calls
- **Timeout Management**: 10-minute survey timeout with auto-save
- **Fallback Responses**: Graceful handling of API failures

## 📊 **Data Schema**

### **Airtable Structure**
```
Table: SlackUsers
├── SlackID (string)          # Slack User ID
├── FullConvo (long text)     # Complete conversation log
├── Answer1 (text)            # First topic response (if using simple mode)
└── Answer2 (text)            # Second topic response (if using simple mode)
```

## ⚠️ **Known Issues**

### **✅ DM Threading Issue - RESOLVED**
**Previous Issue**: Bot responses were creating separate chat entries in Slack sidebar instead of maintaining one continuous DM conversation.

**✅ SOLUTION IMPLEMENTED**: Thread continuity using `thread_ts` tracking
- **Fix**: Save timestamp from initial message and use it for all follow-up messages
- **Result**: All messages now appear in single continuous DM conversation
- **Status**: ✅ **RESOLVED - Production Ready**

**Technical Implementation**:
```python
# Save thread_ts from initial message
response = app.client.chat_postMessage(...)
conversation_state[user_id]["thread_ts"] = response["ts"]

# Use thread_ts for all follow-up messages
if thread_ts:
    payload["thread_ts"] = thread_ts
```

## 🎯 **Production Status**

### **✅ Fully Operational Features**
- ✅ **Seamless DM conversations** - Single continuous thread
- ✅ **Admin-only controls** - Secure survey triggering  
- ✅ **Natural AI conversations** - GPT-4o-mini powered
- ✅ **Automatic data storage** - Full Airtable integration
- ✅ **Robust error handling** - Comprehensive logging and recovery
- ✅ **Professional UX** - Clean, intuitive user experience

### **✅ Testing Completed**
- ✅ Thread continuity verified
- ✅ Survey completion workflows tested
- ✅ Admin command functionality confirmed
- ✅ Data persistence validated
- ✅ Error scenarios handled properly

## 📁 **Project Structure**

```
├── app.py                   # Main bot application (production ready)
├── prompts.py               # AI conversation prompts and logic
├── requirements.txt         # Python dependencies
├── vercel.json             # Vercel deployment configuration
├── .env.example            # Environment variables template
├── DEPLOYMENT.md           # Vercel deployment guide
├── README.md               # This file
└── progress.md             # Development history
```

## 🔐 **Security & Permissions**

- **Admin-Only Access**: Survey triggering restricted to authorized users
- **Environment Variables**: Sensitive keys stored in `.env` file
- **Slack Permissions**: Minimal required bot scopes
- **Data Privacy**: Conversations stored securely in Airtable

## 🚀 **Development**

### **Adding New Features**
1. Modify conversation prompts in `prompts.py`
2. Update conversation logic in `app.py`
3. Test with `/trigger-survey` in test mode
4. Update documentation

### **Debugging**
- Check console logs for detailed error messages
- Use test mode for safe development
- Monitor Airtable for data persistence
- Verify Slack permissions and scopes

---

**Version**: 2.0.0  
**Last Updated**: December 18, 2024  
**Status**: ✅ **Production Ready - Fully Operational**

### **Recent Updates**:
- ✅ **v2.0.0**: Resolved DM threading issue with `thread_ts` implementation
- ✅ **Enhanced Error Handling**: Comprehensive logging and background operation monitoring  
- ✅ **Production Deployment**: Full testing completed and verified
- ✅ **Professional UX**: Seamless single-thread DM conversations
