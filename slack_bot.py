import os
from slack_bolt import App
from slack_sdk.errors import SlackApiError
from pyairtable import Table

# Airtable configuration
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE", "SlackUsers")

# Slack configuration
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# Create Airtable table client
airtable = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)


def get_handles():
    """Fetch Slack handles/emails from Airtable."""
    records = airtable.all()
    return [rec["fields"].get("Handle") for rec in records if "Handle" in rec["fields"]]


def open_questions_modal(trigger_id: str, user_id: str):
    """Open a modal with two questions."""
    app.client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": "survey_modal",
            "title": {"type": "plain_text", "text": "Questions"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "private_metadata": user_id,
            "blocks": [
                {
                    "type": "input",
                    "block_id": "q1",
                    "element": {"type": "plain_text_input", "action_id": "a1"},
                    "label": {"type": "plain_text", "text": "Question 1"},
                },
                {
                    "type": "input",
                    "block_id": "q2",
                    "element": {"type": "plain_text_input", "action_id": "a2"},
                    "label": {"type": "plain_text", "text": "Question 2"},
                },
            ],
        },
    )


def send_dm_to_handle(handle: str):
    """DM a user identified by handle/email with a button to open the modal."""
    try:
        user_info = app.client.users_lookupByEmail(email=handle)
        user_id = user_info["user"]["id"]
        res = app.client.conversations_open(users=user_id)
        channel_id = res["channel"]["id"]
        app.client.chat_postMessage(
            channel=channel_id,
            text="Hello! Please click the button to answer two quick questions.",
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "Click below:"},
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Answer Questions"},
                            "action_id": "open_modal",
                        }
                    ],
                },
            ],
        )
    except SlackApiError as e:
        print(f"Error DM-ing {handle}: {e.response['error']}")


@app.action("open_modal")
def handle_button_click(ack, body):
    ack()
    trigger_id = body["trigger_id"]
    user_id = body["user"]["id"]
    open_questions_modal(trigger_id, user_id)


@app.view("survey_modal")
def handle_submission(ack, body):
    ack()
    user_id = body["user"]["id"]
    q1_answer = body["view"]["state"]["values"]["q1"]["a1"]["value"]
    q2_answer = body["view"]["state"]["values"]["q2"]["a2"]["value"]
    airtable.create({"SlackHandle": user_id, "Answer1": q1_answer, "Answer2": q2_answer})


def notify_all_users():
    for handle in get_handles():
        send_dm_to_handle(handle)


if __name__ == "__main__":
    notify_all_users()
    app.start(port=int(os.environ.get("PORT", 3000)))
