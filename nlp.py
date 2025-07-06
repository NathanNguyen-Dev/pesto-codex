import os
from openai import OpenAI
from prompts import get_topic_extraction_prompt

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

def extract_topics(text):
    """
    Use OpenAI to extract 1-5 short topics from the input text.
    Returns a list of topics (strings).
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": get_topic_extraction_prompt()},
            {"role": "user", "content": text}
        ]
    )
    topics = response.choices[0].message.content.strip().split(",")
    return [t.strip() for t in topics if t.strip()] 