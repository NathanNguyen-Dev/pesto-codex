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
from prompts import (
    get_system_prompt, 
    get_warm_tagging_personality_prompt,
    get_topic_expansion_prompt,
    get_tagging_decision_prompt
)
# Removed unused import: extract_topics
from graph import update_knowledge_graph, get_relevant_users_for_topics

# Configuration
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE", "SlackUsers")
AIRTABLE_COLUMN_NAME = os.environ.get("AIRTABLE_COLUMN_NAME", "SlackID")
ADMIN_USER_IDS = os.environ.get("ADMIN_USER_IDS", "").split(",")

# Global state management
conversation_state = {}
conversation_lock = threading.Lock()

# Cooldown tracking for tagging
user_tag_cooldowns = {}
cooldown_lock = threading.Lock()

# Cooldown configuration (in seconds)
USER_TAG_COOLDOWN = 3600  # 1 hour cooldown per user
CHANNEL_TAG_COOLDOWN = 300  # 5 minutes between any tags in a channel

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

def is_admin(user_id: str) -> bool:
    """Check if user is an admin."""
    return user_id in ADMIN_USER_IDS

def get_conversation_state(user_id: str) -> dict:
    """Get conversation state for a user."""
    with conversation_lock:
        return conversation_state.get(user_id, {})

def set_conversation_state(user_id: str, state: dict):
    """Set conversation state for a user."""
    with conversation_lock:
        conversation_state[user_id] = state

def is_user_in_cooldown(user_id: str) -> bool:
    """Check if a user is in cooldown period for tagging."""
    with cooldown_lock:
        last_tagged = user_tag_cooldowns.get(user_id, 0)
        return time.time() - last_tagged < USER_TAG_COOLDOWN

def update_user_cooldown(user_id: str):
    """Update the cooldown timestamp for a user."""
    with cooldown_lock:
        user_tag_cooldowns[user_id] = time.time()

def get_cooldown_remaining(user_id: str) -> int:
    """Get remaining cooldown time in seconds for a user."""
    with cooldown_lock:
        last_tagged = user_tag_cooldowns.get(user_id, 0)
        elapsed = time.time() - last_tagged
        return max(0, int(USER_TAG_COOLDOWN - elapsed))

def get_cooldown_stats() -> dict:
    """Get statistics about current cooldown state."""
    with cooldown_lock:
        now = time.time()
        active_cooldowns = []
        for user_id, last_tagged in user_tag_cooldowns.items():
            remaining = USER_TAG_COOLDOWN - (now - last_tagged)
            if remaining > 0:
                active_cooldowns.append({
                    'user_id': user_id,
                    'remaining_seconds': int(remaining),
                    'remaining_minutes': int(remaining // 60)
                })
        
        return {
            'total_users_tracked': len(user_tag_cooldowns),
            'active_cooldowns': len(active_cooldowns),
            'cooldown_duration_hours': USER_TAG_COOLDOWN / 3600,
            'users_in_cooldown': active_cooldowns
        }

def clear_expired_cooldowns():
    """Clear expired cooldowns to prevent memory bloat."""
    with cooldown_lock:
        now = time.time()
        expired_users = []
        for user_id, last_tagged in list(user_tag_cooldowns.items()):
            if now - last_tagged > USER_TAG_COOLDOWN:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del user_tag_cooldowns[user_id]
        
        if expired_users:
            print(f"🧹 COOLDOWN CLEANUP: Removed {len(expired_users)} expired cooldowns")
        
        return len(expired_users)

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

def expand_topics_for_matching(canonical_topics):
    """
    Expand canonical topics to include synonyms and variations using o3-mini for better matching.
    
    Args:
        canonical_topics (list): List of canonical topic names
    
    Returns:
        list: Expanded list including original topics and their synonyms
    """
    import time
    start_time = time.time()
    
    print(f"🔍 TOPIC EXPANSION: Expanding {len(canonical_topics)} canonical topics using o3-mini")
    print(f"   Canonical topics: {canonical_topics}")
    
    try:
        # Create prompt for LLM to expand topics
        topics_str = ", ".join(canonical_topics)
        prompt = get_topic_expansion_prompt(topics_str)

        # Call o3-mini
        llm_start = time.time()
        client = OpenAI()
        response = client.responses.create(
            model="o3-mini",
            reasoning={"effort": "low"},
            input=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        llm_time = time.time() - llm_start
        
        print(f"   o3-mini API call completed ({llm_time:.2f}s)")
        
        # Handle response
        if response.status == "incomplete" and response.incomplete_details.reason == "max_output_tokens":
            print("   ⚠️ Token limit reached during topic expansion")
            if response.output_text:
                content = response.output_text.strip()
                print(f"   Partial response recovered")
            else:
                print("   ❌ No response text available - falling back to original topics")
                return canonical_topics
        else:
            content = response.output_text.strip()
            print(f"   ✅ Full expansion received")
        
        # Parse the response
        expanded_topics = []
        seen_topics = set()
        
        # Split by | to get different topic groups
        topic_groups = content.split('|')
        
        for group in topic_groups:
            # Split by comma to get individual terms
            terms = [term.strip() for term in group.split(',')]
            for term in terms:
                term = term.strip()
                if term and term not in seen_topics:
                    expanded_topics.append(term)
                    seen_topics.add(term)
        
        # Ensure all original topics are included
        for topic in canonical_topics:
            if topic not in seen_topics:
                expanded_topics.append(topic)
                seen_topics.add(topic)
        
        total_time = time.time() - start_time
        print(f"🔍 TOPIC EXPANSION: Complete ({total_time:.2f}s)")
        print(f"   Original: {len(canonical_topics)} topics")
        print(f"   Expanded: {len(expanded_topics)} topics")
        print(f"   Expansion ratio: {len(expanded_topics)/len(canonical_topics):.1f}x")
        
        return expanded_topics
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ TOPIC EXPANSION FAILED: {e} ({total_time:.2f}s)")
        import traceback
        traceback.print_exc()
        
        # Fallback to original topics
        print(f"   🔄 Falling back to original topics: {canonical_topics}")
        return canonical_topics

def suggest_relevant_users(topics, exclude_user_id=None, channel_id=None, max_suggestions=3):
    """
    Find relevant users for discussed topics and format suggestions.
    
    Args:
        topics (list): List of canonical topics being discussed
        exclude_user_id (str, optional): User ID to exclude (usually message author)
        channel_id (str, optional): Channel ID for context
        max_suggestions (int): Maximum number of user suggestions to return
    
    Returns:
        dict: Formatted suggestions with users and rationale
    """
    import time
    start_time = time.time()
    
    print(f"🔍 USER SUGGESTION: Starting for canonical topics={topics}, exclude={exclude_user_id}")
    
    try:
        # Expand topics to include synonyms for better matching
        expanded_topics = expand_topics_for_matching(topics)
        print(f"   Expanded to {len(expanded_topics)} topic variations: {expanded_topics}")
        
        # Get relevant users for all expanded topics
        # Request more users than needed to account for cooldowns (trickle down)
        extended_limit = max_suggestions * 3  # Request 3x more users for trickle down
        graph_start = time.time()
        relevant_users = get_relevant_users_for_topics(expanded_topics, exclude_user_id, limit=extended_limit)
        graph_time = time.time() - graph_start
        
        print(f"   Graph query completed ({graph_time:.2f}s)")
        print(f"   Requested {extended_limit} users (3x {max_suggestions}) for trickle down")
        
        if not relevant_users:
            print(f"   No relevant users found in graph")
            return None
        
        # Log raw results
        total_matches = sum(len(users) for users in relevant_users.values())
        print(f"   Found {total_matches} total user matches across {len(relevant_users)} topics")
        
        # Format suggestions (use original canonical topics, not expanded ones)
        suggestions = {
            "topics": topics,  # Keep original canonical topics for consistency
            "users": [],
            "message": ""
        }
        
        # Collect unique users across all topics with their best relationship
        user_map = {}
        for found_topic, users in relevant_users.items():
            print(f"   Topic '{found_topic}': {len(users)} users")
            
            # Map found topic back to canonical topic for consistency
            canonical_topic = found_topic
            for canonical in topics:
                if canonical.lower() in found_topic.lower() or found_topic.lower() in canonical.lower():
                    canonical_topic = canonical
                    break
            
            for user in users:
                user_id = user['user_id']
                if user_id not in user_map:
                    user_map[user_id] = {
                        'user_id': user_id,
                        'name': user['name'],
                        'relationships': [],
                        'best_relationship': user['relationship'],
                        'activity_level': user['activity_level'],
                        'topics': []
                    }
                
                # Add canonical topic and relationship info
                if canonical_topic not in user_map[user_id]['topics']:
                    user_map[user_id]['topics'].append(canonical_topic)
                    
                user_map[user_id]['relationships'].append({
                    'topic': canonical_topic,
                    'relationship': user['relationship'],
                    'activity_level': user['activity_level']
                })
                
                # Keep the best relationship (expert > working > interested)
                if user['relationship'] == 'IS_EXPERT_IN':
                    user_map[user_id]['best_relationship'] = 'IS_EXPERT_IN'
                elif user['relationship'] == 'WORKING_ON' and user_map[user_id]['best_relationship'] != 'IS_EXPERT_IN':
                    user_map[user_id]['best_relationship'] = 'WORKING_ON'
        
        print(f"   Consolidated to {len(user_map)} unique users")
        
        # Sort by relationship priority and activity level
        sorted_users = sorted(user_map.values(), key=lambda u: (
            1 if u['best_relationship'] == 'IS_EXPERT_IN' else 
            2 if u['best_relationship'] == 'WORKING_ON' else 3,
            -u['activity_level']
        ))
        
        print(f"   Sorted candidate pool: {len(sorted_users)} users")
        
        # Filter out users in cooldown
        available_users = []
        cooldown_filtered = []
        
        for i, user in enumerate(sorted_users):
            user_id = user['user_id']
            if is_user_in_cooldown(user_id):
                cooldown_remaining = get_cooldown_remaining(user_id)
                minutes_remaining = cooldown_remaining // 60
                cooldown_filtered.append({
                    'user': user,
                    'remaining_minutes': minutes_remaining,
                    'original_rank': i + 1
                })
                continue
            available_users.append(user)
        
        # Log cooldown filtering with trickle down effect
        if cooldown_filtered:
            print(f"⏱️ COOLDOWN FILTER: {len(cooldown_filtered)} users in cooldown (trickle down in effect):")
            for item in cooldown_filtered[:3]:  # Show first 3
                user = item['user']
                minutes = item['remaining_minutes']
                rank = item['original_rank']
                print(f"     - #{rank} {user['name']} ({minutes}m remaining)")
            if len(cooldown_filtered) > 3:
                print(f"     ... and {len(cooldown_filtered) - 3} more")
        else:
            print(f"⏱️ COOLDOWN FILTER: No users in cooldown")
        
        # Take top suggestions from available users
        top_users = available_users[:max_suggestions]
        suggestions['users'] = top_users
        
        # Check if we have enough users after trickle down
        if len(top_users) < max_suggestions and len(available_users) < max_suggestions:
            shortage = max_suggestions - len(available_users)
            print(f"⚠️ TRICKLE DOWN: Only {len(available_users)} users available (need {max_suggestions})")
            print(f"   Consider: {shortage} top users are in cooldown - this is working as intended!")
        
        # Log trickle down effect
        if available_users:
            print(f"🔄 TRICKLE DOWN: Final selection from {len(available_users)} available users:")
            for i, user in enumerate(top_users):
                rel_count = len(user['relationships'])
                # Find original ranking before cooldown filtering
                original_rank = next((j+1 for j, u in enumerate(sorted_users) if u['user_id'] == user['user_id']), "?")
                trickle_note = f" (trickled down from #{original_rank})" if original_rank > i + 1 else ""
                print(f"     {i+1}. {user['name']}{trickle_note} - {user['best_relationship']} ({rel_count} relationships)")
        else:
            print(f"⚠️ TRICKLE DOWN: No available users after cooldown filtering")
        
        processing_time = time.time() - start_time
        print(f"🔍 USER SUGGESTION: Complete ({processing_time:.2f}s)")
        
        return suggestions
        
    except Exception as e:
        processing_time = time.time() - start_time
        print(f"❌ USER SUGGESTION FAILED: {e} ({processing_time:.2f}s)")
        import traceback
        traceback.print_exc()
        return None

def format_user_suggestions_with_personality(suggestions, original_message):
    """
    Use LLM to generate warm, engaging tagging responses based on personality prompt.
    
    Args:
        suggestions (dict): Suggestions from suggest_relevant_users()
        original_message (str): The original message that triggered the tagging
    
    Returns:
        str: LLM-generated warm tagging response
    """
    import time
    start_time = time.time()
    
    if not suggestions or not suggestions['users']:
        print(f"❌ LLM FORMATTING: No suggestions provided")
        return None
    
    print(f"🎭 LLM FORMATTING: Generating warm response for {len(suggestions['users'])} users")
    
    try:
        # Prepare context for the LLM
        topics = suggestions['topics']
        users = suggestions['users']
        
        # Create user context with explicit relationship types
        user_context = []
        for user in users[:3]:  # Limit to top 3 users
            user_id = user['user_id']
            name = user['name']
            best_rel = user['best_relationship']
            user_topics = user['topics']
            
            # Create relationship-specific descriptions
            if best_rel == 'IS_EXPERT_IN':
                expertise = f"IS_EXPERT_IN {', '.join(user_topics)} - the go-to authority"
            elif best_rel == 'WORKING_ON':
                expertise = f"WORKING_ON {', '.join(user_topics)} - actively building/developing"
            elif best_rel == 'INTERESTED_IN':
                expertise = f"INTERESTED_IN {', '.join(user_topics)} - learning/curious about"
            else:  # MENTIONS
                expertise = f"MENTIONS {', '.join(user_topics)} - has discussed"
            
            user_context.append(f"<@{user_id}> ({name} - {expertise})")
        
        print(f"   Topics: {topics}")
        print(f"   Users: {[u['name'] for u in users[:3]]}")
        print(f"   Original message preview: {original_message[:60]}...")
        
        # Analyze message characteristics for context-aware response
        message_length = len(original_message.split())
        has_question = '?' in original_message
        has_excitement = any(char in original_message for char in ['!', '🔥', '🚀', '💯', '🎉'])
        is_casual = any(word in original_message.lower() for word in ['hey', 'yo', 'sup', 'lol', 'haha'])
        is_technical = any(word in original_message.lower() for word in ['algorithm', 'model', 'architecture', 'implementation'])
        
        print(f"   📊 Message analysis: {message_length} words | Question: {has_question} | Excited: {has_excitement} | Casual: {is_casual} | Technical: {is_technical}")
        print(f"   🎯 Using o3-mini model with enhanced context awareness")
        
        # Create enhanced context for the LLM
        context = f"""You need to generate a tagging response that matches the tone and style of the original message AND customizes based on each person's relationship type.

ORIGINAL MESSAGE ANALYSIS:
- Content: "{original_message}"
- Length: {message_length} words
- Has question: {has_question}
- Has excitement: {has_excitement}  
- Casual tone: {is_casual}
- Technical tone: {is_technical}

TOPICS BEING DISCUSSED: {', '.join(topics)}

RELEVANT COMMUNITY MEMBERS TO TAG (WITH RELATIONSHIP TYPES):
{chr(10).join(user_context)}

CRITICAL: Use each person's relationship type to customize how you refer to them:
- IS_EXPERT_IN: Position as authority/expert ("the expert", "your expertise", "knows this inside out")
- WORKING_ON: Connect to their active projects ("working on this", "building something similar", "right up your alley")
- INTERESTED_IN: Frame as learning opportunity ("would love to learn", "perfect for your interests", "fascinating for you")
- MENTIONS: Use general enthusiasm ("check this out", "one for you", "thoughts?")

TASK: Generate ONE LINE that tags people while customizing the language based on their specific relationship to the topic.
- Match the original message energy and tone
- Use relationship-appropriate language for each person
- Feel like a natural continuation of the conversation"""
        
        # Get LLM response using o3 for better contextual formatting
        llm_start = time.time()
        client = OpenAI()
        response = client.responses.create(
            model="o3-mini", 
            input=[
                {
                    "role": "user",
                    "content": f"{get_warm_tagging_personality_prompt()}\n\n{context}"
                }
            ]
        )
        llm_time = time.time() - llm_start
        
        print(f"   o3-mini API call completed ({llm_time:.2f}s)")
        
        if response.status == "incomplete" and response.incomplete_details.reason == "max_output_tokens":
            print("   ⚠️ Token limit reached during response generation")
            if response.output_text:
                warm_response = response.output_text.strip()
                print(f"   Partial response recovered: {warm_response}")
            else:
                print("   ❌ No response text available - token limit hit during reasoning")
                return None
        else:
            warm_response = response.output_text.strip()
            print(f"   ✅ Full response generated: {warm_response}")
        
        # Validate response quality
        if not warm_response:
            print(f"   ❌ Empty response from LLM")
            return None
        
        # Check if response contains user mentions
        mentioned_users = [u for u in users if f"<@{u['user_id']}>" in warm_response]
        print(f"   Response mentions {len(mentioned_users)} users")
        
        if not mentioned_users:
            print(f"   ⚠️ Response doesn't mention any users - may be malformed")
        
        total_time = time.time() - start_time
        print(f"🎭 LLM FORMATTING: Complete ({total_time:.2f}s)")
        
        return warm_response
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ LLM FORMATTING FAILED: {e} ({total_time:.2f}s)")
        import traceback
        traceback.print_exc()
        
        # Fallback to simple format
        print(f"   🔄 Falling back to simple formatting")
        return format_user_suggestions_simple(suggestions)

def format_user_suggestions_simple(suggestions):
    """
    Simple fallback formatting if LLM fails.
    
    Args:
        suggestions (dict): Suggestions from suggest_relevant_users()
    
    Returns:
        str: Simple formatted message
    """
    if not suggestions or not suggestions['users']:
        return None
    
    users = suggestions['users']
    
    # Simple format with first user
    if users:
        user = users[0]
        return f"<@{user['user_id']}>, this one's for you!"
    
    return None

def format_user_suggestions(suggestions, original_message=""):
    """
    Format user suggestions with warm personality (maintains backward compatibility).
    
    Args:
        suggestions (dict): Suggestions from suggest_relevant_users()
        original_message (str): The original message that triggered the tagging
    
    Returns:
        str: Formatted message with warm personality
    """
    return format_user_suggestions_with_personality(suggestions, original_message)

def should_suggest_users(channel_id, topics, last_suggestion_time=None):
    """
    Determine if we should suggest users using o3-mini mini agent.
    
    Args:
        channel_id (str): Channel ID
        topics (list): Topics being discussed
        last_suggestion_time (datetime, optional): Last time suggestions were made
    
    Returns:
        bool: Whether to suggest users
    """
    import time
    start_time = time.time()
    
    print(f"🤔 SHOULD SUGGEST: Evaluating for channel {channel_id} using o3-mini")
    print(f"   Topics: {topics}")
    
    if not topics:
        print(f"   ❌ No topics provided")
        return False
    
    if len(topics) > 8:  # Hard limit to avoid overwhelming
        print(f"   ❌ Too many topics ({len(topics)}) - avoiding overwhelming discussions")
        return False
    
    try:
        # Create prompt for mini agent to decide
        topics_str = ", ".join(topics)
        prompt = get_tagging_decision_prompt(channel_id, topics_str)

        # Call o3-mini
        llm_start = time.time()
        client = OpenAI()
        response = client.responses.create(
            model="o3-mini",
            reasoning={"effort": "low"},
            input=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        llm_time = time.time() - llm_start
        
        print(f"   o3-mini decision call completed ({llm_time:.2f}s)")
        
        # Handle response
        if response.status == "incomplete" and response.incomplete_details.reason == "max_output_tokens":
            print("   ⚠️ Token limit reached during decision")
            if response.output_text:
                decision = response.output_text.strip().upper()
                print(f"   Partial decision recovered: {decision}")
            else:
                print("   ❌ No decision available - defaulting to NO")
                return False
        else:
            decision = response.output_text.strip().upper()
            print(f"   ✅ Full decision received: {decision}")
        
        # Parse decision
        should_suggest = decision == "YES"
        
        total_time = time.time() - start_time
        print(f"🤔 SHOULD SUGGEST: Decision '{decision}' → {should_suggest} ({total_time:.2f}s)")
        
        return should_suggest
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ SHOULD SUGGEST FAILED: {e} ({total_time:.2f}s)")
        import traceback
        traceback.print_exc()
        
        # Conservative fallback - only suggest for clearly tech topics
        print(f"   🔄 Falling back to conservative heuristic")
        tech_keywords = ['ai', 'ml', 'machine learning', 'artificial intelligence', 
                        'data', 'software', 'programming', 'robotics', 'research']
        
        has_tech = any(keyword in topic.lower() for topic in topics for keyword in tech_keywords)
        fallback_decision = has_tech and len(topics) <= 3
        
        print(f"   Fallback decision: {fallback_decision} (has_tech={has_tech}, topic_count={len(topics)})")
        return fallback_decision 