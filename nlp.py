import os
from openai import OpenAI
from prompts import (
    get_enhanced_topic_extraction_prompt,
    get_enhanced_interest_extraction_prompt
)

client = OpenAI()

def extract_topics_with_relationships(text):
    """
    Enhanced extraction that returns topics AND relationship types from Slack messages.
    
    Args:
        text (str): Slack message content
    
    Returns:
        list: List of tuples (topic, relationship_type) where relationship_type is 
              one of: MENTIONS, WORKING_ON, INTERESTED_IN
    """
    response = client.responses.create(
        model="o3-mini",
        reasoning={"effort": "low"},
        input=[
            {
                "role": "user", 
                "content": f"{get_enhanced_topic_extraction_prompt()}\n\nMessage to analyze:\n{text}"
            }
        ]
    )
    
    if response.status == "incomplete" and response.incomplete_details.reason == "max_output_tokens":
        print("Ran out of tokens during topic relationship extraction")
        if response.output_text:
            content = response.output_text.strip()
        else:
            print("Ran out of tokens during reasoning")
            return []
    else:
        content = response.output_text.strip()
    
    topic_relationships = []
    
    # Parse the Topic|RelationshipType format
    for item in content.split(","):
        item = item.strip()
        if "|" in item:
            topic, relationship = item.split("|", 1)
            topic_relationships.append((topic.strip(), relationship.strip()))
        else:
            # Fallback: if no relationship specified, default to MENTIONS
            topic_relationships.append((item.strip(), "MENTIONS"))
    
    return topic_relationships

def extract_interests_with_relationships(text):
    """
    Enhanced extraction that returns interests AND relationship types from LinkedIn profiles.
    
    Args:
        text (str): LinkedIn profile or detailed bio content
    
    Returns:
        list: List of tuples (interest, relationship_type) where relationship_type is 
              one of: IS_EXPERT_IN, WORKING_ON, INTERESTED_IN
    """
    response = client.responses.create(
        model="o3-mini",
        reasoning={"effort": "low"},
        input=[
            {
                "role": "user", 
                "content": f"{get_enhanced_interest_extraction_prompt()}\n\nProfile to analyze:\n{text}"
            }
        ]
    )
    
    if response.status == "incomplete" and response.incomplete_details.reason == "max_output_tokens":
        print("Ran out of tokens during interest extraction")
        if response.output_text:
            content = response.output_text.strip()
        else:
            print("Ran out of tokens during reasoning")
            return []
    else:
        content = response.output_text.strip()
    
    interest_relationships = []
    
    # Parse the Interest|RelationshipType format
    for item in content.split(","):
        item = item.strip()
        if "|" in item:
            interest, relationship = item.split("|", 1)
            interest_relationships.append((interest.strip(), relationship.strip()))
        else:
            # Fallback: if no relationship specified, default to IS_EXPERT_IN for profiles
            interest_relationships.append((item.strip(), "IS_EXPERT_IN"))
    
    return interest_relationships 