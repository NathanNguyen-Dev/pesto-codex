"""
MLAI Slack Survey Bot with Bulk Messaging

This bot conducts conversational surveys using OpenAI and saves responses to Airtable.

Usage Examples:
    # Test mode - message first user from default table
    python slack_bot.py

    # Test mode - message first user from specific table
    python slack_bot.py --table-id tbl123ABC456DEF --test-mode

    # Message ALL users from a specific table
    python slack_bot.py --table-id tbl123ABC456DEF --message-all

    # Use custom column name for Slack IDs
    python slack_bot.py --table-id tbl123ABC456DEF --column-name UserSlackID --message-all

Required Environment Variables:
    - AIRTABLE_API_KEY
    - AIRTABLE_BASE_ID
    - SLACK_BOT_TOKEN
    - SLACK_SIGNING_SECRET
    - OPENAI_API_KEY
"""

import os
import sys
import argparse
import time
from dotenv import load_dotenv
from slack_bolt import App
from slack_sdk.errors import SlackApiError
from pyairtable import Api
from openai import OpenAI
import json
from bot_prompts import get_system_prompt

load_dotenv()

# Airtable configuration
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE", "SlackUsers")
AIRTABLE_COLUMN_NAME = os.environ.get("AIRTABLE_COLUMN_NAME", "SlackID")

# OpenAI configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Slack configuration with rate limiting handling
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# Create Airtable API client
api = Api(AIRTABLE_API_KEY)

# In-memory conversation state storage
conversation_state = {}

def safe_say(say_func, message: str, user_id: str = None, max_retries: int = 3):
    """Safely send a message with rate limiting protection."""
    for attempt in range(max_retries):
        try:
            say_func(message)
            return True
        except SlackApiError as e:
            if e.response.get('error') == 'ratelimited':
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
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

def get_user_ids_from_table(table_id: str = None, column_name: str = None):
    """Fetch Slack User IDs from a specific Airtable table."""
    # Use provided table_id or fall back to environment variable
    target_table_id = table_id or AIRTABLE_TABLE_NAME
    target_column = column_name or AIRTABLE_COLUMN_NAME
    
    print(f"Fetching user IDs from Airtable base '{AIRTABLE_BASE_ID}', table '{target_table_id}', column '{target_column}'...")
    
    try:
        # Create table client for the specific table
        airtable_table = api.table(AIRTABLE_BASE_ID, target_table_id)
        records = airtable_table.all()
        
        user_ids = [
            rec["fields"].get(target_column)
            for rec in records
            if target_column in rec["fields"] and rec["fields"].get(target_column)
        ]
        
        print(f"Found {len(user_ids)} user ID(s) in table '{target_table_id}'.")
        return user_ids, target_table_id
        
    except Exception as e:
        print(f"Error fetching from table '{target_table_id}': {e}")
        return [], target_table_id

def get_user_ids():
    """Fetch Slack User IDs from Airtable (legacy function for backward compatibility)."""
    user_ids, _ = get_user_ids_from_table()
    return user_ids

def get_openai_response(user_id: str, user_message: str):
    """Get conversational response from OpenAI based on conversation state."""
    
    # Initialize conversation state if new user
    if user_id not in conversation_state:
        conversation_state[user_id] = {
            "step": "not_started",
            "answer1": None,
            "answer2": None,
            "conversation_history": [],
            "question1_asked": False,
            "question2_asked": False
        }
    
    state = conversation_state[user_id]
    
    # If conversation is completed, don't process anymore
    if state["step"] == "completed":
        return "Thank you! Your responses have been recorded. The survey is now complete."
    
    # If not started and no trigger, ask them to use the button
    if state["step"] == "not_started":
        return "Please click the '🚀 Yes, I'd love to help!' button above to begin the community survey."
    
    # Get system prompt from the prompts file
    system_prompt = get_system_prompt(state["step"])
    
    # Don't add trigger messages to conversation history
    is_trigger_message = user_message in ["Please ask the first question", "Please ask the second question"]
    
    # Add conversation history
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add previous conversation
    for msg in state["conversation_history"]:
        messages.append(msg)
    
    # Only add non-trigger messages to conversation
    if not is_trigger_message:
        messages.append({"role": "user", "content": user_message})
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=200,
            temperature=0.7
        )
        
        bot_response = response.choices[0].message.content
        
        # Ensure we have a valid response
        if not bot_response or bot_response.strip() == "":
            bot_response = "I'm sorry, I didn't catch that. Could you please try again?"
        
        # Handle conversation flow based on current step
        if not is_trigger_message:
            state["conversation_history"].append({"role": "user", "content": user_message})
            state["conversation_history"].append({"role": "assistant", "content": bot_response})
            
            # Process responses based on conversation step
            if state["step"] == "question1":
                if not state["question1_asked"]:
                    # This is the bot asking the first question, mark it as asked
                    state["question1_asked"] = True
                else:
                    # This is the user's response to question 1
                    # Use OpenAI to determine if this is a relevant answer
                    if is_relevant_answer(user_message, "motivation to join MLAI"):
                        state["answer1"] = user_message
                        state["step"] = "question2"
                        state["question2_asked"] = False
                        print(f"Captured Answer1 for {user_id}: {user_message}")
                    else:
                        # Ask for clarification - don't advance the step
                        print(f"User {user_id} gave unclear response to Q1: {user_message}")
                        
            elif state["step"] == "question2":
                if not state["question2_asked"]:
                    # This is the bot asking the second question, mark it as asked
                    state["question2_asked"] = True
                else:
                    # This is the user's response to question 2
                    if is_relevant_answer(user_message, "goals and expectations from MLAI community"):
                        state["answer2"] = user_message
                        state["step"] = "completed"
                        # Save to Airtable
                        save_answers_to_airtable(user_id, state["answer1"], state["answer2"])
                        print(f"Captured Answer2 for {user_id}: {user_message}")
                        print(f"Survey completed for user {user_id}")
                    else:
                        # Ask for clarification - don't advance the step
                        print(f"User {user_id} gave unclear response to Q2: {user_message}")
        
        return bot_response
        
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return "Sorry, I'm having trouble responding right now. Please try again!"

def is_relevant_answer(user_message: str, question_topic: str) -> bool:
    """Use OpenAI to determine if the user's message is a relevant answer to the question topic."""
    try:
        # Simple heuristics first
        if len(user_message.strip()) < 3:
            return False
            
        # Check for obvious non-answers
        non_answers = ["why", "what", "who", "how", "explain", "i don't know", "hm", "interesting", "wanna say", "thankyou"]
        message_lower = user_message.lower()
        
        # If it's mostly a question or confusion, reject it
        if any(phrase in message_lower for phrase in non_answers) and len(user_message.split()) < 6:
            return False
        
        # For goals/expectations, be more lenient with short answers
        if "goals and expectations" in question_topic:
            positive_keywords = ["network", "learn", "grow", "connect", "skill", "job", "career", "project", "knowledge", "community", "mentor", "base", "build"]
            if any(keyword in message_lower for keyword in positive_keywords):
                return True
        
        # For motivation, also be more lenient
        if "motivation" in question_topic:
            positive_keywords = ["interest", "passion", "learn", "grow", "ai", "ml", "machine", "technology", "career", "curious", "improve"]
            if any(keyword in message_lower for keyword in positive_keywords):
                return True
            
        # Use OpenAI to check relevance for complex cases
        validation_prompt = f"""
        Is this message a relevant answer to a question about "{question_topic}"?
        
        Message: "{user_message}"
        
        Consider even short answers like "networking", "learning", "career growth" as valid.
        Respond with only "YES" if it's a relevant answer, or "NO" if it's clearly a question, confusion, or completely unrelated.
        """
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": validation_prompt}],
            max_tokens=10,
            temperature=0.1
        )
        
        result = response.choices[0].message.content.strip().upper()
        return result == "YES"
        
    except Exception as e:
        print(f"Error validating answer relevance: {e}")
        # If validation fails, be more lenient with fallback
        return len(user_message.strip()) > 3 and not any(phrase in user_message.lower() for phrase in ["why", "what", "who", "explain"])

def save_answers_to_airtable(user_id: str, answer1: str, answer2: str):
    """Save the conversation answers to Airtable."""
    try:
        print(f"Saving answers for user {user_id} to Airtable...")
        
        # Create table client for the default table
        airtable_table = api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)
        
        # Find the record for the user
        records = airtable_table.all(formula=f"{{{AIRTABLE_COLUMN_NAME}}} = '{user_id}'")
        
        if records:
            record_id = records[0]["id"]
            print(f"Found record ID {record_id}. Updating with answers.")
            airtable_table.update(record_id, {"Answer1": answer1, "Answer2": answer2})
            print("Successfully updated Airtable record.")
        else:
            # Create new record if user not found
            print(f"No record found for {user_id}. Creating a new one.")
            airtable_table.create({
                AIRTABLE_COLUMN_NAME: user_id, 
                "Answer1": answer1, 
                "Answer2": answer2
            })
            print("Successfully created new Airtable record.")
            
    except Exception as e:
        print(f"Error saving to Airtable: {e}")

def send_dm_to_user_id(user_id: str):
    """Send initial DM to start the conversation."""
    try:
        print(f"Attempting to open DM with User ID: {user_id}")
        res = app.client.conversations_open(users=user_id)
        channel_id = res["channel"]["id"]
        
        # Add a small delay to avoid rate limits
        time.sleep(0.5)
        
        # Send a welcome message with a button
        app.client.chat_postMessage(
            channel=channel_id,
            text="Meet Pesto, the AI-powered community engagement bot!",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "👋 **Meet Pesto, the AI-powered community engagement bot!**\n\nPesto is here to help enhance our community experience by providing insightful conversations and fostering meaningful connections.\n\nWe're currently running an experiment to improve our community engagement, and we'd love your input!\n\nWould you be okay with answering a couple of questions to help us improve your experience here?"
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
        print(f"Successfully sent initial DM to User ID: {user_id}")
    except SlackApiError as e:
        print(f"Error DM-ing {user_id}: {e.response['error']}")
    except Exception as e:
        print(f"Unexpected error sending DM to {user_id}: {e}")

@app.action("start_survey_button")
def handle_survey_start_button(ack, body, client):
    """Handle the Start Survey button click."""
    ack()  # Acknowledge the button click
    
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    
    print(f"User {user_id} clicked the Start Survey button")
    
    # Initialize conversation state
    if user_id not in conversation_state:
        conversation_state[user_id] = {
            "step": "not_started",
            "answer1": None,
            "answer2": None,
            "conversation_history": [],
            "question1_asked": False,
            "question2_asked": False
        }
    
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
    
    # Start the survey by setting step to question1 (ready for first answer)
    conversation_state[user_id]["step"] = "question1"
    conversation_state[user_id]["question1_asked"] = False
    
    # Get first question from OpenAI with a neutral trigger
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
                    "text": f"🚀 **Survey Started!**\n\n{question_text}"
                }
            }
        ]
    )

@app.message("")
def handle_direct_message(message, say):
    """Handle all direct messages to the bot."""
    user_id = message["user"]
    user_text = message["text"]
    
    # Skip bot messages
    if message.get("bot_id"):
        return
    
    print(f"Received message from {user_id}: {user_text}")
    
    # Check if user's conversation is completed - stop processing
    if user_id in conversation_state and conversation_state[user_id]["step"] == "completed":
        print(f"User {user_id} tried to message after completion. Ignoring.")
        safe_say(say, "Thank you! Your survey responses have already been recorded. No further input is needed.", user_id)
        return
    
    # Get conversational response
    response = get_openai_response(user_id, user_text)
    
    # Ensure response is not empty before sending
    if response and response.strip():
        success = safe_say(say, response, user_id)
        if not success:
            print(f"Could not deliver response to {user_id}, but continuing...")
    else:
        # Fallback message if response is empty
        safe_say(say, "Please click the '🚀 Yes, I'd love to help!' button to begin the MLAI community survey.", user_id)
    
    # Check if conversation is completed
    if user_id in conversation_state and conversation_state[user_id]["step"] == "completed":
        print(f"Survey completed for user {user_id}. Answers saved: '{conversation_state[user_id]['answer1']}' and '{conversation_state[user_id]['answer2']}'")

def notify_users_in_table(table_id: str = None, column_name: str = None, test_mode: bool = False):
    """Send DMs to all users in a specific Airtable table."""
    user_ids, actual_table_id = get_user_ids_from_table(table_id, column_name)
    
    if not user_ids:
        print(f"No user IDs found in table '{actual_table_id}'. Exiting.")
        return

    print(f"Found {len(user_ids)} users in table '{actual_table_id}'")
    
    if test_mode:
        # In test mode, only message the first user
        first_user_id = user_ids[0]
        print(f"TEST MODE: Sending DM to first user only: {first_user_id}")
        send_dm_to_user_id(first_user_id)
    else:
        # Message all users with delays to avoid rate limits
        print(f"Sending DMs to all {len(user_ids)} users...")
        for i, user_id in enumerate(user_ids, 1):
            print(f"Sending DM {i}/{len(user_ids)} to user: {user_id}")
            send_dm_to_user_id(user_id)
            
            # Add delay between messages to avoid rate limits
            if i < len(user_ids):  # Don't delay after the last user
                print(f"Waiting 2 seconds before next DM...")
                time.sleep(2)
            
        print(f"Successfully sent DMs to all {len(user_ids)} users in table '{actual_table_id}'")

def notify_all_users():
    """Legacy function for backward compatibility."""
    notify_users_in_table(test_mode=True)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='MLAI Slack Survey Bot')
    parser.add_argument('--table-id', '-t', 
                       help='Airtable table ID to fetch users from')
    parser.add_argument('--column-name', '-c', 
                       help='Column name containing Slack IDs (default: SlackID)')
    parser.add_argument('--test-mode', action='store_true',
                       help='Test mode: only message the first user')
    parser.add_argument('--message-all', action='store_true',
                       help='Message all users in the specified table')
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    if args.message_all or args.table_id:
        # Bulk messaging mode
        if not args.table_id:
            print("Error: --table-id is required when using --message-all")
            sys.exit(1)
            
        print(f"🚀 Starting bulk messaging for table: {args.table_id}")
        notify_users_in_table(
            table_id=args.table_id,
            column_name=args.column_name,
            test_mode=args.test_mode
        )
        
        if not args.test_mode:
            print("✅ Bulk messaging complete! Starting bot server to handle responses...")
    else:
        # Default behavior - test mode with default table
        notify_all_users()
    
    # Start the bot server to handle responses
    print("🤖 Bot server starting to handle responses...")
    app.start(port=int(os.environ.get("PORT", 3000)))
