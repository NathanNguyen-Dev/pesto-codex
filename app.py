"""
Clean MLAI Slack Survey Bot - Pure Bolt SDK with Slash Commands
Only admins can trigger the bot using /trigger-survey command.
"""

import os
import time
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
from slack_bolt import App
from slack_sdk.errors import SlackApiError
from pyairtable import Api
from openai import OpenAI
from prompts import get_system_prompt
from nlp import extract_topics
from graph import update_knowledge_graph

load_dotenv()

# Slack Bolt app
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# Configuration
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE", "SlackUsers")
AIRTABLE_COLUMN_NAME = os.environ.get("AIRTABLE_COLUMN_NAME", "SlackID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Admin user IDs - MUST be actual Slack User IDs of community admins
# To find Slack User ID: Right-click profile → "Copy member ID" 
ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "").split(",")

# Initialize clients
# openai_client = OpenAI(api_key=OPENAI_API_KEY)  # Lazy load this
api = Api(AIRTABLE_API_KEY)

# Lazy loading for OpenAI client
_openai_client = None

def get_openai_client():
    """Get OpenAI client with lazy loading."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client

# In-memory conversation state storage with thread safety
conversation_state = {}
conversation_lock = threading.Lock()

# Rate limiting for OpenAI API calls
from collections import defaultdict
openai_last_call = defaultdict(float)
OPENAI_RATE_LIMIT = 1.0  # Minimum 1 second between calls per user

def is_admin(user_id: str) -> bool:
    """Check if user is an admin."""
    return user_id in ADMIN_USER_IDS

def safe_get_conversation_state(user_id: str):
    """Thread-safe get conversation state."""
    with conversation_lock:
        return conversation_state.get(user_id, {}).copy()

def safe_update_conversation_state(user_id: str, updates: dict):
    """Thread-safe update conversation state."""
    with conversation_lock:
        if user_id not in conversation_state:
            conversation_state[user_id] = {}
        conversation_state[user_id].update(updates)

def can_call_openai(user_id: str) -> bool:
    """Check if we can make an OpenAI call for this user (rate limiting)."""
    now = time.time()
    if now - openai_last_call[user_id] < OPENAI_RATE_LIMIT:
        return False
    openai_last_call[user_id] = now
    return True

def safe_say(say_func, message: str, user_id: str = None, max_retries: int = 3):
    """Safely send a message with rate limiting protection."""
    for attempt in range(max_retries):
        try:
            say_func(message)
            return True
        except SlackApiError as e:
            if e.response.get('error') == 'ratelimited':
                wait_time = 2 ** attempt
                print(f"Rate limited. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
            else:
                print(f"Slack API error for user {user_id}: {e}")
                return False
        except Exception as e:
            print(f"Unexpected error sending message to {user_id}: {e}")
            return False
    
    print(f"Failed to send message to {user_id} after {max_retries} attempts")
    return False

def safe_dm(user_id, message):
    """Send message directly to user's DM, maintaining thread continuity."""
    try:
        dm_channel = app.client.conversations_open(users=user_id)["channel"]["id"]
        
        # Get the thread_ts for this conversation to maintain continuity
        state = safe_get_conversation_state(user_id)
        thread_ts = state.get("thread_ts")
        
        # Build message payload
        payload = {
            "channel": dm_channel,
            "text": message
        }
        
        # Use thread_ts if we have one to keep all messages in the same DM thread
        if thread_ts:
            payload["thread_ts"] = thread_ts
        
        app.client.chat_postMessage(**payload)
        return True
    except Exception as e:
        print(f"Failed to DM {user_id}: {e}")
        return False

def get_user_ids_from_table(table_id: str = None, column_name: str = None, name_column: str = "Name"):
    """Fetch Slack User IDs and names from a specific Airtable table."""
    target_table_id = table_id or AIRTABLE_TABLE_NAME
    target_column = column_name or AIRTABLE_COLUMN_NAME
    
    print(f"Fetching user IDs and names from Airtable base '{AIRTABLE_BASE_ID}', table '{target_table_id}', columns '{target_column}' and '{name_column}'...")
    
    try:
        airtable_table = api.table(AIRTABLE_BASE_ID, target_table_id)
        records = airtable_table.all()
        
        users = []
        for rec in records:
            user_id = rec["fields"].get(target_column)
            user_name = rec["fields"].get(name_column, "there")  # Default to "there" if no name
            
            if user_id:  # Only include records with valid user IDs
                users.append({
                    "id": user_id,
                    "name": user_name
                })
        
        print(f"Found {len(users)} user(s) in table '{target_table_id}'.")
        return users, target_table_id
        
    except Exception as e:
        print(f"Error fetching from table '{target_table_id}': {e}")
        return [], target_table_id

def is_survey_timed_out(user_id: str) -> bool:
    """Check if the survey has timed out (10 minutes since start)."""
    if user_id not in conversation_state:
        return False
    
    start_time = conversation_state[user_id].get("start_time")
    if not start_time:
        return False
    
    elapsed = datetime.now() - start_time
    return elapsed > timedelta(minutes=10)

def get_openai_response(user_id: str, user_message: str):
    """Get conversational response from OpenAI based on conversation state."""
    
    # Initialize conversation state if new user
    if user_id not in conversation_state:
        conversation_state[user_id] = {
            "step": "not_started",
            "conversation_history": [],
            "start_time": None
        }
    
    state = conversation_state[user_id]
    
    # Check if survey has timed out (10 minutes)
    if state["step"] == "started" and is_survey_timed_out(user_id):
        print(f"⏰ Survey timed out for user {user_id} after 10 minutes")
        state["step"] = "completed"
        save_full_conversation_to_airtable(user_id)
        return "Thanks for your time! The survey has timed out and your responses have been saved."
    
    # If conversation is completed, don't process anymore
    if state["step"] == "completed":
        return "Thank you! Your responses have been recorded. The survey is now complete."
    
    # If not started and no trigger, ask them to use the button
    if state["step"] == "not_started":
        return "Please click the '🚀 Yes, I'd love to help!' button above to begin the community survey."
    
    # Get system prompt for natural conversation
    if state["step"] == "started":
        system_prompt = get_system_prompt(user_id)
        
        # Add conversation flow context to help maintain continuity
        conversation_length = len(state["conversation_history"]) // 2  # Divide by 2 since we store both user and bot messages
        if conversation_length > 0:
            system_prompt += f"\n\nCONVERSATION CONTEXT: This is exchange #{conversation_length + 1} in an ongoing conversation. Maintain natural flow and reference previous responses when appropriate."
    else:
        system_prompt = "You are a helpful MLAI community bot."
    
    # Don't add trigger messages to conversation history
    is_trigger_message = user_message in ["Please ask the first question", "start survey"]
    
    # Add conversation history
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add previous conversation
    for msg in state["conversation_history"]:
        messages.append(msg)
    
    # Only add non-trigger messages to conversation
    if not is_trigger_message:
        messages.append({"role": "user", "content": user_message})
    
    try:
        response = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=200,
            temperature=0.1
        )
        
        bot_response = response.choices[0].message.content
        
        # Ensure we have a valid response
        if not bot_response or bot_response.strip() == "":
            bot_response = "I'm sorry, I didn't catch that. Could you please try again?"
        
        # Add to conversation history
        if not is_trigger_message:
            state["conversation_history"].append({"role": "user", "content": user_message})
            state["conversation_history"].append({"role": "assistant", "content": bot_response})
        
        # Check if bot is ending the conversation
        if "thank you for sharing" in bot_response.lower() and "responses have been recorded" in bot_response.lower():
            state["step"] = "completed"
            # Save the full conversation to Airtable
            save_full_conversation_to_airtable(user_id)
            print(f"✅ Survey completed for user {user_id}")
        
        return bot_response
        
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return "Sorry, I'm having trouble responding right now. Please try again!"

def save_full_conversation_to_airtable(user_id: str):
    """Save the full conversation to Airtable."""
    try:
        print(f"Saving full conversation for user {user_id} to Airtable...")
        
        # Create table client for the default table
        airtable_table = api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)
        
        # Format the full conversation for storage
        full_conversation = ""
        if user_id in conversation_state:
            conversation_history = conversation_state[user_id]["conversation_history"]
            
            for msg in conversation_history:
                role = "Bot" if msg["role"] == "assistant" else "User"
                full_conversation += f"{role}: {msg['content']}\n\n"
        
        # Find the record for the user
        print(f"Looking for user record with {AIRTABLE_COLUMN_NAME} = '{user_id}'")
        
        try:
            records = airtable_table.all()
            user_record = None
            
            # Find the matching record manually
            for record in records:
                if record["fields"].get(AIRTABLE_COLUMN_NAME) == user_id:
                    user_record = record
                    break
                    
            print(f"Found {len(records)} total records in table")
            
        except Exception as search_error:
            print(f"Error searching records: {search_error}")
            user_record = None
        
        # Prepare the data to save
        save_data = {
            "FullConvo": full_conversation.strip()
        }
        
        if user_record:
            record_id = user_record["id"]
            print(f"Found matching record ID {record_id} for user {user_id}. Updating with full conversation.")
            
            # Update only this specific record
            airtable_table.update(record_id, save_data)
            print(f"Successfully updated record {record_id} for user {user_id}")
            
        else:
            # Create new record if user not found
            print(f"No existing record found for user {user_id}. Creating a new one.")
            save_data[AIRTABLE_COLUMN_NAME] = user_id
            new_record = airtable_table.create(save_data)
            print(f"Successfully created new record {new_record['id']} for user {user_id}")
            
    except Exception as e:
        print(f"Error saving to Airtable for user {user_id}: {e}")
        import traceback
        traceback.print_exc()

def send_dm_to_user_id(user_id: str, user_name: str = "there"):
    """Send initial DM to start the conversation."""
    try:
        print(f"Attempting to open DM with User ID: {user_id} ({user_name})")
        res = app.client.conversations_open(users=user_id)
        channel_id = res["channel"]["id"]
        
        time.sleep(0.5)
        
        response = app.client.chat_postMessage(
            channel=channel_id,
            text=f"Hi {user_name}! Meet Pesto, the AI-powered community engagement bot!",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"""👋 Hi {user_name}! Meet Pesto, the AI-powered community engagement bot!\n\nPesto is here to help enhance our community experience by providing insightful conversations and fostering meaningful connections.\n\nWe're running an experiment to improve engagement and would love your input, can you please answer a few questions?"""
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🚀 Yes, I'd love to help!"
                            },
                            "style": "primary",
                            "action_id": "start_survey_button"
                        }
                    ]
                }
            ]
        )
        
        # Initialize conversation state with thread_ts to maintain DM continuity
        if user_id not in conversation_state:
            conversation_state[user_id] = {}
        
        conversation_state[user_id].update({
            "step": "not_started",
            "conversation_history": [],
            "start_time": None,
            "thread_ts": response["ts"],  # Save the timestamp for threading
            "user_name": user_name  # Store the user's name for future use
        })
        
        print(f"Successfully sent initial DM to User ID: {user_id} ({user_name}) (thread_ts: {response['ts']})")
    except SlackApiError as e:
        print(f"Error DM-ing {user_id} ({user_name}): {e.response['error']}")
    except Exception as e:
        print(f"Unexpected error sending DM to {user_id} ({user_name}): {e}")

def notify_users_in_table(table_id: str = None, column_name: str = None, test_mode: bool = False):
    """Send DMs to all users in a specific Airtable table."""
    print(f"🔄 notify_users_in_table called with:")
    print(f"   table_id: {table_id}")
    print(f"   column_name: {column_name}")
    print(f"   test_mode: {test_mode}")
    
    try:
        user_ids, actual_table_id = get_user_ids_from_table(table_id, column_name)
        print(f"📋 get_user_ids_from_table returned:")
        print(f"   user_ids: {user_ids}")
        print(f"   actual_table_id: {actual_table_id}")
    except Exception as e:
        print(f"❌ Error in get_user_ids_from_table: {e}")
        raise
    
    if not user_ids:
        print(f"⚠️ No user IDs found in table '{actual_table_id}'. Exiting.")
        return 0

    print(f"✅ Found {len(user_ids)} users in table '{actual_table_id}'")
    
    if test_mode:
        first_user_id = user_ids[0]["id"]
        print(f"🧪 TEST MODE: Sending DM to first user only: {first_user_id}")
        try:
            send_dm_to_user_id(first_user_id, user_ids[0]["name"])
            print(f"✅ Test DM sent successfully to {first_user_id}")
            return 1
        except Exception as e:
            print(f"❌ Error sending test DM to {first_user_id}: {e}")
            raise
    else:
        print(f"📤 Sending DMs to all {len(user_ids)} users...")
        success_count = 0
        
        for i, user_info in enumerate(user_ids, 1):
            user_id = user_info["id"]
            user_name = user_info["name"]
            try:
                print(f"📨 Sending DM {i}/{len(user_ids)} to user: {user_id} ({user_name})")
                send_dm_to_user_id(user_id, user_name)
                success_count += 1
                print(f"✅ DM {i} sent successfully")
                
                if i < len(user_ids):
                    print(f"⏳ Waiting 2 seconds before next DM...")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"❌ Error sending DM {i} to {user_id} ({user_name}): {e}")
                # Continue with other users instead of failing completely
                continue
            
        print(f"📊 Final results: {success_count}/{len(user_ids)} DMs sent successfully")
        return success_count

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
            
            users_messaged = notify_users_in_table(table_id, column_name, test_mode)
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
    
    # Initialize conversation state with all required fields
    if user_id not in conversation_state:
        conversation_state[user_id] = {}
    
    # Ensure all required fields exist and maintain the original thread_ts
    existing_thread_ts = conversation_state[user_id].get("thread_ts", message_ts)
    conversation_state[user_id].update({
        "step": conversation_state[user_id].get("step", "not_started"),
        "conversation_history": conversation_state[user_id].get("conversation_history", []),
        "start_time": conversation_state[user_id].get("start_time", None),
        "thread_ts": existing_thread_ts
    })
    
    # Check if already completed
    if conversation_state[user_id]["step"] == "completed":
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
    conversation_state[user_id]["step"] = "started"
    conversation_state[user_id]["start_time"] = datetime.now()
    print(f"🕐 Survey started for user {user_id} at {conversation_state[user_id]['start_time']}")
    
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

# Temporarily disabled to test event handler
# @app.message("")
def handle_direct_message_disabled(message, say):
    """Handle user messages for survey conversations (DMs only)."""
    user_id = message["user"]
    user_text = message["text"]
    channel_type = message.get("channel_type")
    channel_id = message["channel"]
    
    print(f"🔵 DM handler triggered - channel_type: {channel_type}, user: {user_id}")
    
    if message.get("bot_id"):
        return

    # Only handle direct messages for survey functionality
    if channel_type != "im":
        print(f"🔵 Not a DM, letting other handlers process - channel_type: {channel_type}")
        return  # Let other handlers process non-DM messages

    print(f"Received DM from {user_id}: {user_text}")

    # Check for timeout before processing any message
    if user_id in conversation_state and conversation_state[user_id]["step"] == "started" and is_survey_timed_out(user_id):
        print(f"⏰ Survey timed out for user {user_id} during message processing")
        conversation_state[user_id]["step"] = "completed"
        save_full_conversation_to_airtable(user_id)
        safe_dm(user_id, "Thanks for your time! The survey has timed out and your responses have been saved.")
        return
    
    # Check if user's conversation is completed - stop processing
    if user_id in conversation_state and conversation_state[user_id]["step"] == "completed":
        print(f"User {user_id} tried to message after completion. Ignoring.")
        safe_dm(user_id, "Thank you! Your survey responses have already been recorded. No further input is needed.")
        return
    
    # Get conversational response
    response = get_openai_response(user_id, user_text)
    
    # Send response only if we have a valid one
    if response and response.strip():
        success = safe_dm(user_id, response)
        if success:
            print(f"Sent response to {user_id}: {response[:50]}...")
        else:
            print(f"Failed to send response to {user_id}")
    else:
        # Fallback message if response is empty
        safe_dm(user_id, "Please click the '🚀 Yes, I'd love to help!' button to begin the MLAI community survey.")
    
    # Log completion status
    if user_id in conversation_state and conversation_state[user_id]["step"] == "completed":
        print(f"✅ Survey completed for user {user_id}")
        print(f"Full conversation saved to Airtable")

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

# --- Slack → OpenAI → Neo4j pipeline integration ---
# (Consolidated into debug_and_process_message_events above to avoid handler conflicts)

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