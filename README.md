# MLAI Slack Bot - Intelligent Community Tagging System

An AI-powered Slack bot that intelligently tags relevant community members when interesting topics are discussed, using a Neo4j knowledge graph and OpenAI's o3-mini model for contextual understanding.

## 🌟 Overview

The MLAI Slack Bot enhances community engagement by:
- **Automatically detecting topics** in conversations using AI
- **Finding relevant experts** from a Neo4j knowledge graph
- **Suggesting users** with warm, casual personality responses
- **Preventing spam** with intelligent cooldown systems
- **Learning relationships** between users and topics over time

## 🏗️ System Architecture

### Core Components

```
📨 Slack Message → 🧠 Topic Extraction → 📊 Neo4j Graph → 🔍 User Matching → 🎭 LLM Response → ✅ Slack Delivery
```

**1. Message Processing Pipeline**
- Filters original messages only (skips threaded replies)
- Extracts user information and content
- Comprehensive logging with timing metrics

**2. Topic Extraction (OpenAI o3-mini)**
- Analyzes message content for relevant topics
- Determines relationship types: `MENTIONS`, `WORKING_ON`, `INTERESTED_IN`
- Expands topics dynamically for better matching

**3. Knowledge Graph (Neo4j)**
- Stores user-topic relationships over time
- Tracks expertise levels and activity patterns
- Enables intelligent user discovery

**4. User Matching System**
- Finds relevant users based on topic expertise
- Prioritizes: Expert → Working → Interested
- Filters users in cooldown (trickle down to next best)

**5. Response Generation (OpenAI o3-mini)**
- Creates warm, casual tagging responses
- Matches original message tone and energy
- Uses fun personality: "Oooh, this looks siiiiiiick!", "Legend!"

### Tech Stack

- **Python 3.9+** - Core application
- **Slack Bolt SDK** - Slack integration
- **OpenAI API** - o3-mini for AI processing
- **Neo4j** - Knowledge graph database
- **Airtable** - User data management
- **Heroku** - Cloud deployment

## 🚀 Key Features

### 🏷️ Intelligent Tagging

**Smart Topic Detection**
- Extracts 1-5 broad topic categories from messages
- Determines user relationship to each topic
- Expands topics with synonyms for better matching

**Expert Discovery**
- Finds users with relevant expertise
- Considers relationship strength and activity level
- Suggests 1-3 most relevant people

**Contextual Responses**
- Adapts tone to match original message
- Uses casual, fun personality ("sick", "legend", "GAWD")
- Feels like a friend hyping up other friends

### ⏱️ Anti-Spam Protection

**User Cooldown System**
- 1-hour protection per user to prevent repeat tagging
- Thread-safe tracking with automatic cleanup
- Detailed logging of cooldown status

**Trickle Down Functionality**
- When top experts are in cooldown, suggests next best available
- Requests 3x more candidates to ensure good suggestions
- Maintains quality while avoiding spam

**Smart Filtering**
- Only processes original messages, not threaded replies
- Saves AI credits and prevents conversation clutter
- Intelligent decision making about when to suggest users

### 📊 Production Monitoring

**Comprehensive Logging**
- End-to-end timing metrics for performance monitoring
- Detailed error tracking with full context
- Success/failure indicators for each pipeline stage

**Performance Metrics**
- Topic extraction timing and token usage
- Neo4j query performance
- LLM response generation timing
- User suggestion success rates

**Error Handling**
- Graceful fallbacks for each component
- Partial response recovery
- Conservative heuristics when AI fails

### 🤖 LLM-Powered Intelligence

**Topic Expansion Agent**
- Dynamically expands canonical topics with synonyms
- Conservative expansion (3-5 variations vs hardcoded lists)
- Focused on direct synonyms, not sub-fields

**Tagging Decision Agent**
- Context-aware decisions about when to tag
- Considers channel ID and topic combinations
- Professional relevance vs casual conversation filtering

**Personality Response Agent**
- Generates warm, contextual tagging messages
- Matches energy but stays casual and fun
- Creates genuine enthusiasm and engagement

## ⚙️ Setup & Configuration

### Environment Variables

```bash
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key

# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# Airtable Configuration
AIRTABLE_API_KEY=your-airtable-key
AIRTABLE_BASE_ID=your-base-id
AIRTABLE_TABLE=SlackUsers
AIRTABLE_COLUMN_NAME=SlackID

# Admin Configuration
ADMIN_USER_IDS=U1234567890,U0987654321

# Server Configuration
PORT=3000
```

### Installation

```bash
# Clone repository
git clone <repository-url>
cd pesto-codex

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your configuration

# Start the application
python app.py
```

### Dependencies

```
slack-bolt>=1.14.3
openai>=1.3.0
neo4j>=5.0.0
python-dotenv>=0.19.0
pyairtable>=1.0.0
```

## 🎯 Usage

### Automatic Tagging

**Original Message Processing**
- Bot monitors all channels for original messages
- Extracts topics and finds relevant users
- Posts warm, casual tagging suggestions

**Example Flow:**
```
User: "I'm building an AI MedTech platform, looking for co-founder"
Bot: "Oooh, this looks siiiiiiick! @DrMed, you gotta check this out!"
```

### Admin Commands

**Survey Management**
```bash
/trigger-survey <table_id> [test|all] [column_name]

# Examples
/trigger-survey tbl123ABC456DEF test          # Test mode (first user only)
/trigger-survey tbl123ABC456DEF all           # Send to all users
/trigger-survey tbl123ABC456DEF test UserID   # Custom column name
```

### Response Examples

**For Excitement/Sharing:**
- "Oooh, this looks siiiiiiick! <@USER_ID>!"
- "<@USER_ID>, you gotta check this out!"
- "<@USER_ID> is the expert here!"

**For Appreciation:**
- "Nice job <@USER_ID>!"
- "Legend, <@USER_ID>!"
- "Oh my GAWD! <@USER_ID>, you nailed it!"

**For Questions/Help:**
- "<@USER_ID> can totally help with this!"
- "<@USER_ID> is your person!"
- "<@USER_ID> knows this inside and out!"

## 📋 Monitoring & Logs

### Log Format

```
📨 MESSAGE EVENT | 2025-01-07 14:30:25
   Type: message | Subtype: None
   User: U1234567890 | Channel: C9876543210
   Text Preview: I'm building an AI MedTech platform...

🧠 TOPIC EXTRACTION: SUCCESS (1.23s)
   Relationships: [('AI', 'WORKING_ON'), ('Medical', 'WORKING_ON')]
   Topics: ['AI', 'Medical']
   Relationship distribution: {'WORKING_ON': 2}

📊 NEO4J UPDATE: SUCCESS for U1234567890 with 2 topics (0.45s)

🔍 USER SUGGESTION: Starting for canonical topics=['AI', 'Medical']
   Expanded to 8 topic variations: ['AI', 'Artificial Intelligence', ...]
   Graph query completed (0.67s)
   Found 5 total user matches across 2 topics

⏱️ COOLDOWN FILTER: 1 users in cooldown (trickle down in effect):
     - #2 DrTech (45m remaining)

🎭 LLM RESPONSE: Generated warm message (1.89s)
   Message: Oooh, this looks siiiiiiick! <@DrMed>, you gotta check this out!

✅ SLACK POST: Warm tagging response sent (0.32s)

📋 PROCESSING SUMMARY:
   Total time: 4.56s
   Topics extracted: 2
   Neo4j updated: true
   Tagging attempted: true
   Tagging successful: true
   Users suggested: 1
```

### Performance Metrics

**Typical Response Times:**
- Topic extraction: 0.5-2.0s
- Neo4j queries: 0.1-0.5s
- LLM response generation: 1.0-3.0s
- Total processing: 2.0-6.0s

**Success Rates:**
- Topic extraction: >95%
- User matching: >80%
- Response generation: >90%

## 🔧 Development

### File Structure

```
pesto-codex/
├── app.py              # Main Slack Bolt application
├── utils.py            # Core utility functions and logic
├── nlp.py              # OpenAI topic extraction
├── graph.py            # Neo4j knowledge graph operations
├── prompts.py          # Centralized prompt management
├── requirements.txt    # Python dependencies
├── README.md          # This documentation
└── .env               # Environment configuration
```

### Key Functions

**Message Processing (`app.py`)**
- `process_message_with_tagging()` - Main message handler
- Thread filtering and early exit conditions
- Comprehensive logging and error handling

**User Suggestions (`utils.py`)**
- `suggest_relevant_users()` - Find and rank relevant users
- `format_user_suggestions_with_personality()` - Generate warm responses
- `should_suggest_users()` - Intelligent tagging decisions

**Topic Extraction (`nlp.py`)**
- `extract_topics_with_relationships()` - OpenAI-powered topic analysis
- Relationship type detection
- Token usage optimization

**Knowledge Graph (`graph.py`)**
- `update_knowledge_graph_with_relationships()` - Store user-topic data
- `get_relevant_users_for_topics()` - Query expertise
- Relationship strength tracking

### Cooldown System

**Implementation:**
```python
USER_TAG_COOLDOWN = 3600  # 1 hour
user_tag_cooldowns = {}   # Thread-safe tracking

def is_user_in_cooldown(user_id: str) -> bool:
    with cooldown_lock:
        return user_id in user_tag_cooldowns and 
               user_tag_cooldowns[user_id] > datetime.now()
```

**Features:**
- Thread-safe tracking with locks
- Automatic cleanup of expired cooldowns
- Trickle down when top users are in cooldown
- Detailed logging of cooldown status

### Prompt Management

**Centralized in `prompts.py`:**
- `get_enhanced_topic_extraction_prompt()` - Topic analysis
- `get_warm_tagging_personality_prompt()` - Response generation
- `get_topic_expansion_prompt()` - Synonym expansion
- `get_tagging_decision_prompt()` - Context-aware decisions

## 🚀 Deployment

### Heroku Deployment

```bash
# Create Heroku app
heroku create your-app-name

# Configure environment variables
heroku config:set SLACK_BOT_TOKEN=xoxb-...
heroku config:set OPENAI_API_KEY=sk-...
# ... other environment variables

# Deploy
git push heroku main

# Scale workers
heroku ps:scale web=1
```

### Production Considerations

**Scaling:**
- Single dyno handles moderate community load
- Monitor response times and consider scaling up for large communities
- Neo4j performance crucial for user queries

**Monitoring:**
- Use Heroku logs or external logging service
- Set up alerts for failed API calls or high response times
- Monitor OpenAI token usage and costs

**Security:**
- Secure environment variables in production
- Validate admin permissions for sensitive commands
- Rate limiting built into Slack Bolt SDK

## 📚 Advanced Features

### Topic Expansion System

**Dynamic Synonym Generation:**
```python
# Input: ["AI", "Medical"]
# Output: ["AI", "Artificial Intelligence", "Machine Learning", 
#          "Medical", "Healthcare", "MedTech"]
```

**Benefits:**
- Better user matching with varied terminology
- Conservative expansion to maintain relevance
- LLM-powered vs hardcoded mappings

### Relationship Tracking

**Three Relationship Types:**
- `IS_EXPERT_IN` - Professional expertise, leadership
- `WORKING_ON` - Active projects, current development
- `INTERESTED_IN` - Learning, curiosity, questions

**Prioritization:**
- Expert > Working > Interested for suggestions
- Activity level as secondary ranking factor
- Temporal decay for relevance

### Context-Aware Responses

**Message Analysis:**
- Length, tone, excitement level detection
- Question vs sharing vs problem categorization
- Technical vs casual language patterns

**Response Adaptation:**
- Match energy but maintain casual personality
- Contextual examples and phrasing
- Natural conversation flow integration

## 🤝 Contributing

### Development Workflow

1. Fork the repository
2. Create a feature branch
3. Make changes with comprehensive logging
4. Test with small user groups
5. Submit pull request with detailed description

### Testing

**Local Testing:**
- Use test Slack workspace
- Mock OpenAI responses for development
- Test cooldown edge cases
- Verify thread filtering

**Production Testing:**
- Deploy to staging environment
- Monitor logs for errors
- Test with real community messages
- Validate cost efficiency

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙋‍♂️ Support

For questions, issues, or contributions:
- Create GitHub issues for bugs
- Use discussions for feature requests
- Monitor logs for production issues
- Contact MLAI admins for access questions

---

*Built with ❤️ for the MLAI community to enhance engagement and knowledge sharing through intelligent user connections.* 