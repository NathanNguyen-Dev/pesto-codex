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
    extract_topics, update_knowledge_graph
)

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

# Single debug handler to avoid conflicts
@app.event("message")
def debug_and_process_message_events(event, client, logger):
    """Debug and process all message events."""
    print(f"🚨 DEBUG: Message event received!")
    print(f"🚨 DEBUG: Event data - type: {event.get('type')}, subtype: {event.get('subtype')}")
    print(f"🚨 DEBUG: User: {event.get('user')}, text: {event.get('text', '')[:50]}...")
    print(f"🚨 DEBUG: Channel: {event.get('channel')}, bot_id: {event.get('bot_id')}")
    
    # Now process for topic extraction (moved from the other handler)
    user_id = event.get("user")
    text = event.get("text")
    ts = event.get("ts")
    channel = event.get("channel")
    subtype = event.get("subtype")

    # Ignore bot messages only (temporarily allow subtypes to debug)
    if event.get("bot_id"):
        print(f"🔍 DEBUG: Ignoring bot message - bot_id={event.get('bot_id')}")
        return
    
    # Check if we have required fields
    if not user_id or not text:
        print(f"🔍 DEBUG: Missing required fields - user_id={user_id}, has_text={bool(text)}")
        return
    
    # Log subtype but don't filter yet
    if subtype:
        print(f"🔍 DEBUG: Message has subtype: {subtype} - processing anyway for debugging")

    print(f"📨 Message received in channel {channel} from user {user_id}: {text[:50]}...")

    # Get user display name
    try:
        user_info = client.users_info(user=user_id)
        display_name = user_info["user"].get("profile", {}).get("display_name") or user_info["user"].get("real_name", "unknown")
        print(f"👤 User info: {user_id} = {display_name}")
    except Exception as e:
        print(f"❌ Failed to fetch display name for {user_id}: {e}")
        display_name = "unknown"

    # Extract topics
    try:
        topics = extract_topics(text)
        print(f"🧠 Extracted topics for {user_id} ({display_name}): {topics}")
    except Exception as e:
        print(f"❌ OpenAI topic extraction failed for {user_id}: {e}")
        topics = []

    # Update Neo4j
    if topics:
        try:
            update_knowledge_graph(user_id, display_name, topics, ts)
            print(f"📊 Updated Neo4j for {user_id} with {len(topics)} topics")
        except Exception as e:
            print(f"❌ Neo4j update failed for {user_id}: {e}")
    else:
        print(f"⚠️ No topics extracted, skipping Neo4j update")

if __name__ == "__main__":
    from utils import ADMIN_USER_IDS
    
    print("🤖 Starting MLAI Survey Bot with Slash Commands...")
    print(f"📋 Admin Users: {ADMIN_USER_IDS}")
    print(f"📊 Active Conversations: {len(conversation_state)}")
    print("")
    print("💡 Usage: /trigger-survey <table_id> [test|all] [column_name]")
    print("🔒 Only admins can use slash commands")
    print("")
    
    # Ensure we're using port 3000
    port = int(os.environ.get("PORT", 3000))
    print(f"🚀 Starting server on port {port}")
    
    # Start Slack Bolt app
    app.start(port=port) 