"""
Clean MLAI Slack Survey Bot - Pure Bolt SDK with Slash Commands
Only admins can trigger the bot using /trigger-survey command.
"""

import os
import threading
from datetime import datetime
from dotenv import load_dotenv
from slack_bolt import App
from utils import (
    is_admin, safe_get_conversation_state, safe_update_conversation_state,
    get_openai_response, notify_users_in_table, conversation_state,
    suggest_relevant_users, format_user_suggestions, should_suggest_users
)
from nlp import extract_topics_with_relationships
from graph import update_knowledge_graph

load_dotenv()

# Slack Bolt app
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# Slash command handler
@app.command("/trigger-survey")
def handle_trigger_survey_command(ack, respond, command):
    """Handle the /trigger-survey slash command (admin only)."""
    ack()
    
    user_id = command["user_id"]
    
    # Check if user is admin
    if not is_admin(user_id):
        respond({
            "response_type": "ephemeral",
            "text": "❌ *Access Denied*\n\nOnly administrators can use this command."
        })
        return
    
    # Parse command arguments
    text = command.get("text", "").strip()
    
    if not text:
        respond({
            "response_type": "ephemeral",
            "text": "📋 *MLAI Survey Bot - Usage*\n\n"
                   "`/trigger-survey <table_id> [test|all] [column_name]`\n\n"
                   "*Examples:*\n"
                   "• `/trigger-survey tbl123ABC456DEF test` - Send to first user only\n"
                   "• `/trigger-survey tbl123ABC456DEF all` - Send to all users\n"
                   "• `/trigger-survey tbl123ABC456DEF test UserSlackID` - Custom column name\n\n"
                   f"*Current active conversations:* {len(conversation_state)}"
        })
        return
    
    # Parse arguments
    args = text.split()
    
    if len(args) < 2:
        respond({
            "response_type": "ephemeral",
            "text": "❌ *Invalid arguments*\n\n"
                   "Usage: `/trigger-survey <table_id> [test|all] [column_name]`"
        })
        return
    
    table_id = args[0]
    mode = args[1].lower()
    column_name = args[2] if len(args) > 2 else "SlackID"
    
    if mode not in ["test", "all"]:
        respond({
            "response_type": "ephemeral",
            "text": "❌ *Invalid mode*\n\nMode must be either `test` or `all`"
        })
        return
    
    test_mode = (mode == "test")
    
    # Acknowledge the command
    respond({
        "response_type": "ephemeral",
        "text": f"🚀 *Triggering Survey Bot*\n\n"
               f"• Table ID: `{table_id}`\n"
               f"• Mode: `{mode}`\n"
               f"• Column: `{column_name}`\n\n"
               f"_Processing in background..._"
    })
    
    # Run the operation in background
    def run_survey():
        try:
            print(f"🔄 Starting background survey operation...")
            print(f"   Table ID: {table_id}")
            print(f"   Mode: {mode}")
            print(f"   Column: {column_name}")
            print(f"   Test mode: {test_mode}")
            
            users_messaged = notify_users_in_table(app.client, table_id, column_name, test_mode)
            print(f"✅ Background operation completed successfully. Users messaged: {users_messaged}")
            
            # Send completion message
            print(f"🔄 Sending completion message to user {user_id} in channel {command['channel_id']}")
            completion_result = app.client.chat_postEphemeral(
                channel=command["channel_id"],
                user=user_id,
                text=f"✅ *Survey Bot Completed*\n\n"
                     f"Successfully sent messages to **{users_messaged}** user(s) from table `{table_id}`\n\n"
                     f"Mode: `{mode}` | Column: `{column_name}`"
            )
            print(f"✅ Completion message sent successfully: {completion_result.get('ok', 'Unknown')}")
            
        except Exception as e:
            print(f"❌ ERROR in background survey operation:")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Error message: {str(e)}")
            
            # Print full traceback for debugging
            import traceback
            print(f"   Full traceback:")
            traceback.print_exc()
            
            try:
                print(f"🔄 Attempting to send error message to user {user_id}")
                error_result = app.client.chat_postEphemeral(
                    channel=command["channel_id"],
                    user=user_id,
                    text=f"❌ *Survey Bot Error*\n\n"
                         f"Error processing table `{table_id}`: {str(e)}\n\n"
                         f"Check server logs for details."
                )
                print(f"✅ Error message sent successfully: {error_result.get('ok', 'Unknown')}")
            except Exception as error_send_exception:
                print(f"❌ FAILED to send error message: {error_send_exception}")
                print(f"   This might be why you're seeing dispatch_failed!")
    
    # Start background thread
    print(f"🚀 Starting background thread for survey operation...")
    thread = threading.Thread(target=run_survey)
    thread.daemon = True
    thread.start()
    print(f"✅ Background thread started successfully")

# Slack Bolt event handlers
@app.action("start_survey_button")
def handle_survey_start_button(ack, body, client):
    """Handle the Start Survey button click."""
    ack()  # Acknowledge the button click
    
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    
    print(f"User {user_id} clicked the Start Survey button")
    
    # Get current state safely
    state = safe_get_conversation_state(user_id)
    
    # Initialize conversation state with all required fields if not exists
    if not state:
        safe_update_conversation_state(user_id, {
            "step": "not_started",
            "conversation_history": [],
            "start_time": None,
            "thread_ts": message_ts
        })
        state = safe_get_conversation_state(user_id)
    
    # Ensure thread_ts is maintained from original message
    existing_thread_ts = state.get("thread_ts", message_ts)
    safe_update_conversation_state(user_id, {"thread_ts": existing_thread_ts})
    
    # Check if already completed
    if state.get("step") == "completed":
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text="Survey already completed!",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "✅ Thank you! Your survey responses have already been recorded.\n\nNo further input is needed."
                    }
                }
            ]
        )
        return
    
    # Start the survey and record timestamp
    safe_update_conversation_state(user_id, {
        "step": "started",
        "start_time": datetime.now()
    })
    
    updated_state = safe_get_conversation_state(user_id)
    print(f"🕐 Survey started for user {user_id} at {updated_state['start_time']}")
    
    # Get first question from OpenAI with a neutral trigger (like working version)
    response = get_openai_response(user_id, "Please ask the first question")
    
    # Update the original message with the first question
    if response and response.strip():
        question_text = response
    else:
        question_text = "Great! Let's start with the first question:\n\n**What motivated you to become a part of MLAI?**"
    
    # Replace the button message with the first question
    client.chat_update(
        channel=channel_id,
        ts=message_ts,
        text="Survey Started!",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🚀 Survey Started!\n\n{question_text}"
                }
            }
        ]
    )

@app.event("app_mention")
def handle_app_mention(body, say, event, client):
    """Handle when someone mentions the bot in a channel."""
    try:
        user_id = event["user"]
        channel_id = event["channel"]
        
        print(f"Bot mentioned by user {user_id} in channel {channel_id}")
        
        # Respond in the channel with a helpful message
        say(
            text=f"Hi <@{user_id}>! 👋",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Hi <@{user_id}>! 👋\n\nI'm Pesto, the MLAI community survey bot. I conduct surveys through **private DM conversations** to keep things personal and focused.\n\n*I don't respond to channel mentions* - but I'd love to chat with you privately! 😊"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "💬 Send me a DM"
                            },
                            "style": "primary",
                            "action_id": "start_dm_button",
                            "value": user_id
                        }
                    ]
                }
            ]
        )
        
    except Exception as e:
        print(f"Error handling app mention: {e}")

@app.action("start_dm_button")
def handle_start_dm_button(ack, body, client):
    """Handle the 'Send me a DM' button click from app mentions."""
    ack()
    
    user_id = body["user"]["id"]
    
    try:
        # Send a helpful DM to the user
        dm_channel = client.conversations_open(users=user_id)["channel"]["id"]
        
        client.chat_postMessage(
            channel=dm_channel,
            text="Hi there! 👋",
            blocks=[
                {
                    "type": "section", 
                    "text": {
                        "type": "mrkdwn",
                        "text": "👋 Hi there! Thanks for your interest in chatting with me.\n\n**Survey Participation**: I currently only conduct surveys when triggered by MLAI admins through special commands.\n\n**How it works**: When a survey is active, you'll receive an invitation with a button to start the conversation.\n\nKeep an eye out for survey invitations from the MLAI team! 🚀"
                    }
                }
            ]
        )
        
        print(f"Sent informational DM to user {user_id} who clicked start_dm_button")
        
    except Exception as e:
        print(f"Error sending DM to {user_id}: {e}")

# Enhanced message handler with comprehensive logging
@app.event("message")
def process_message_with_tagging(event, client, logger):
    """Process message events with topic extraction and smart tagging."""
    import time
    start_time = time.time()
    
    # Basic event logging
    print(f"📨 MESSAGE EVENT | {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Type: {event.get('type')} | Subtype: {event.get('subtype')}")
    print(f"   User: {event.get('user')} | Channel: {event.get('channel')}")
    print(f"   Text Preview: {event.get('text', '')[:80]}...")
    
    # Extract event data
    user_id = event.get("user")
    text = event.get("text")
    ts = event.get("ts")
    channel = event.get("channel")
    subtype = event.get("subtype")

    # Early exit conditions
    if event.get("bot_id"):
        print(f"⏩ SKIP: Bot message (bot_id={event.get('bot_id')})")
        return
    
    if not user_id or not text:
        print(f"⏩ SKIP: Missing required fields (user_id={bool(user_id)}, text={bool(text)})")
        return
    
    if subtype and subtype in ['message_changed', 'message_deleted']:
        print(f"⏩ SKIP: Message subtype '{subtype}' - not processing")
        return

    print(f"🔄 PROCESSING: Message from {user_id} in {channel}")

    # Get user display name with timing
    display_name = "unknown"
    try:
        user_lookup_start = time.time()
        user_info = client.users_info(user=user_id)
        display_name = user_info["user"].get("profile", {}).get("display_name") or user_info["user"].get("real_name", "unknown")
        user_lookup_time = time.time() - user_lookup_start
        print(f"👤 USER LOOKUP: {user_id} = '{display_name}' ({user_lookup_time:.2f}s)")
    except Exception as e:
        print(f"❌ USER LOOKUP FAILED: {user_id} - {e}")

    # Topic extraction with timing and detailed logging
    topics = []
    topic_relationships = []
    try:
        extraction_start = time.time()
        topic_relationships = extract_topics_with_relationships(text)
        topics = [topic for topic, relationship in topic_relationships]
        extraction_time = time.time() - extraction_start
        
        print(f"🧠 TOPIC EXTRACTION: SUCCESS ({extraction_time:.2f}s)")
        print(f"   Relationships: {topic_relationships}")
        print(f"   Topics: {topics}")
        
        # Log topic extraction metrics
        if topic_relationships:
            relationship_counts = {}
            for _, relationship in topic_relationships:
                relationship_counts[relationship] = relationship_counts.get(relationship, 0) + 1
            print(f"   Relationship distribution: {relationship_counts}")
        
    except Exception as e:
        extraction_time = time.time() - extraction_start
        print(f"❌ TOPIC EXTRACTION FAILED: {user_id} - {e} ({extraction_time:.2f}s)")

    # Neo4j update with timing
    neo4j_updated = False
    if topics:
        try:
            neo4j_start = time.time()
            update_knowledge_graph(user_id, display_name, topics, ts)
            neo4j_time = time.time() - neo4j_start
            neo4j_updated = True
            print(f"📊 NEO4J UPDATE: SUCCESS for {user_id} with {len(topics)} topics ({neo4j_time:.2f}s)")
        except Exception as e:
            neo4j_time = time.time() - neo4j_start
            print(f"❌ NEO4J UPDATE FAILED: {user_id} - {e} ({neo4j_time:.2f}s)")
    else:
        print(f"⏩ NEO4J: Skip - no topics extracted")

    # Smart tagging with comprehensive logging
    tagging_attempted = False
    tagging_successful = False
    suggested_users_count = 0
    
    if topics and should_suggest_users(channel, topics):
        tagging_attempted = True
        try:
            tagging_start = time.time()
            print(f"🏷️ TAGGING: Starting suggestion process for topics: {topics}")
            
            # Find relevant users
            suggestions = suggest_relevant_users(topics, exclude_user_id=user_id, channel_id=channel)
            
            if suggestions:
                suggested_users_count = len(suggestions['users'])
                print(f"🔍 USER MATCHING: Found {suggested_users_count} relevant users")
                
                # Log user details
                for i, user in enumerate(suggestions['users']):
                    print(f"   {i+1}. {user['name']} ({user['user_id']}) - {user['best_relationship']} in {user['topics']}")
                
                # Generate warm response
                llm_start = time.time()
                suggestion_message = format_user_suggestions(suggestions, original_message=text)
                llm_time = time.time() - llm_start
                
                if suggestion_message:
                    print(f"🎭 LLM RESPONSE: Generated warm message ({llm_time:.2f}s)")
                    print(f"   Message: {suggestion_message}")
                    
                    # Send to Slack
                    slack_start = time.time()
                    response = client.chat_postMessage(
                        channel=channel,
                        thread_ts=ts,
                        text=suggestion_message,
                        unfurl_links=False,
                        unfurl_media=False
                    )
                    slack_time = time.time() - slack_start
                    
                    if response.get("ok"):
                        tagging_successful = True
                        print(f"✅ SLACK POST: Warm tagging response sent ({slack_time:.2f}s)")
                        print(f"   Message TS: {response.get('ts')}")
                    else:
                        print(f"❌ SLACK POST FAILED: {response}")
                else:
                    print(f"❌ LLM RESPONSE: Failed to generate message ({llm_time:.2f}s)")
            else:
                print(f"⚠️ USER MATCHING: No relevant users found for topics: {topics}")
                
            tagging_time = time.time() - tagging_start
            print(f"🏷️ TAGGING: Process completed ({tagging_time:.2f}s)")
            
        except Exception as e:
            tagging_time = time.time() - tagging_start
            print(f"❌ TAGGING FAILED: {e} ({tagging_time:.2f}s)")
            import traceback
            traceback.print_exc()
    else:
        # Log why tagging was skipped
        if not topics:
            print(f"⏩ TAGGING: Skip - no topics extracted")
        else:
            should_suggest = should_suggest_users(channel, topics)
            print(f"⏩ TAGGING: Skip - should_suggest={should_suggest} for topics={topics}")

    # Final processing summary
    total_time = time.time() - start_time
    print(f"📋 PROCESSING SUMMARY:")
    print(f"   Total time: {total_time:.2f}s")
    print(f"   Topics extracted: {len(topics)}")
    print(f"   Neo4j updated: {neo4j_updated}")
    print(f"   Tagging attempted: {tagging_attempted}")
    print(f"   Tagging successful: {tagging_successful}")
    print(f"   Users suggested: {suggested_users_count}")
    print(f"   Channel: {channel} | User: {display_name} ({user_id})")
    print("─" * 80)

if __name__ == "__main__":
    from utils import ADMIN_USER_IDS
    import time
    
    print("🤖 Starting MLAI Survey Bot with Enhanced Tagging System...")
    print(f"   Version: Production with comprehensive logging")
    print(f"   Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("")
    print("📋 Configuration:")
    print(f"   Admin Users: {ADMIN_USER_IDS}")
    print(f"   Active Conversations: {len(conversation_state)}")
    print("")
    print("🏷️ Smart Tagging Features:")
    print("   ✅ Topic extraction with relationships (MENTIONS, WORKING_ON, INTERESTED_IN)")
    print("   ✅ Neo4j knowledge graph integration")
    print("   ✅ Intelligent user matching with priority ranking")
    print("   ✅ LLM-powered warm personality responses")
    print("   ✅ Anti-spam filtering and rate limiting")
    print("   ✅ Comprehensive performance logging")
    print("")
    print("💡 Slash Commands:")
    print("   /trigger-survey <table_id> [test|all] [column_name]")
    print("   🔒 Only admins can use slash commands")
    print("")
    print("📊 Logging Format:")
    print("   📨 MESSAGE EVENT - Basic message processing")
    print("   🧠 TOPIC EXTRACTION - OpenAI analysis with timing")
    print("   📊 GRAPH QUERY - Neo4j user matching with details")
    print("   🔍 USER SUGGESTION - Matching and filtering logic")
    print("   🎭 LLM FORMATTING - Warm response generation")
    print("   ✅ SLACK POST - Final delivery confirmation")
    print("   📋 PROCESSING SUMMARY - End-to-end metrics")
    print("")
    
    # Ensure we're using port 3000
    port = int(os.environ.get("PORT", 3000))
    print(f"🚀 Starting server on port {port}")
    print("=" * 80)
    
    # Start Slack Bolt app
    app.start(port=port) 