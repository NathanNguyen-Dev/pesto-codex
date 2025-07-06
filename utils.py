"""
Utility functions for the MLAI Slack Survey Bot
"""

import os
import time
import threading
from datetime import datetime, timedelta
from slack_sdk.errors import SlackApiError
from pyairtable import Api
from openai import OpenAI
from prompts import get_system_prompt
# Removed unused import: extract_topics
from graph import update_knowledge_graph

# Configuration
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE", "SlackUsers")
AIRTABLE_COLUMN_NAME = os.environ.get("AIRTABLE_COLUMN_NAME", "SlackID")
ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "").split(",")

# Initialize clients
api = Api(AIRTABLE_API_KEY)

# Lazy loading for OpenAI client
_openai_client = None

def get_openai_client():
    """Get OpenAI client with lazy loading."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client

# In-memory conversation state storage with thread safety
conversation_state = {}
conversation_lock = threading.Lock()

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

def safe_dm(app_client, user_id, message):
    """Send message directly to user's DM, maintaining thread continuity."""
    try:
        dm_channel = app_client.conversations_open(users=user_id)["channel"]["id"]
        
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
        
        app_client.chat_postMessage(**payload)
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
    state = safe_get_conversation_state(user_id)
    if not state:
        return False
    
    start_time = state.get("start_time")
    if not start_time:
        return False
    
    elapsed = datetime.now() - start_time
    return elapsed > timedelta(minutes=10)

def get_openai_response(user_id: str, user_message: str):
    """Get conversational response from OpenAI based on conversation state."""
    
    # Get current state safely
    state = safe_get_conversation_state(user_id)
    
    # Initialize conversation state if new user
    if not state:
        safe_update_conversation_state(user_id, {
            "step": "not_started",
            "conversation_history": [],
            "start_time": None
        })
        state = safe_get_conversation_state(user_id)
    
    # Check if survey has timed out (10 minutes)
    if state["step"] == "started" and is_survey_timed_out(user_id):
        print(f"⏰ Survey timed out for user {user_id} after 10 minutes")
        safe_update_conversation_state(user_id, {"step": "completed"})
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
        response = get_openai_client().responses.create(
            model="o3-mini",
            reasoning={"effort": "low"},
            input=[
                {
                    "role": "user", 
                    "content": f"System instructions and conversation context:\n{messages[0]['content']}\n\n" + 
                             "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages[1:]])
                }
            ]
        )
        
        if response.status == "incomplete" and response.incomplete_details.reason == "max_output_tokens":
            print("Ran out of tokens during conversation response")
            if response.output_text:
                bot_response = response.output_text.strip()
            else:
                print("Ran out of tokens during reasoning")
                bot_response = "I'm sorry, I need to think more about that. Could you please try again?"
        else:
            bot_response = response.output_text.strip()
        
        # Ensure we have a valid response
        if not bot_response or bot_response.strip() == "":
            bot_response = "I'm sorry, I didn't catch that. Could you please try again?"
        
        # Add to conversation history
        if not is_trigger_message:
            current_state = safe_get_conversation_state(user_id)
            updated_history = current_state["conversation_history"].copy()
            updated_history.append({"role": "user", "content": user_message})
            updated_history.append({"role": "assistant", "content": bot_response})
            safe_update_conversation_state(user_id, {"conversation_history": updated_history})
        
        # Check if bot is ending the conversation
        if "thank you for sharing" in bot_response.lower() and "responses have been recorded" in bot_response.lower():
            safe_update_conversation_state(user_id, {"step": "completed"})
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
        state = safe_get_conversation_state(user_id)
        if state:
            conversation_history = state.get("conversation_history", [])
            
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

def send_dm_to_user_id(app_client, user_id: str, user_name: str = "there"):
    """Send initial DM to start the conversation."""
    try:
        print(f"Attempting to open DM with User ID: {user_id} ({user_name})")
        res = app_client.conversations_open(users=user_id)
        channel_id = res["channel"]["id"]
        
        time.sleep(0.5)
        
        response = app_client.chat_postMessage(
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
        safe_update_conversation_state(user_id, {
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

def notify_users_in_table(app_client, table_id: str = None, column_name: str = None, test_mode: bool = False):
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
            send_dm_to_user_id(app_client, first_user_id, user_ids[0]["name"])
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
                send_dm_to_user_id(app_client, user_id, user_name)
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