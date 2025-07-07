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
    import time
    start_time = time.time()
    
    print(f"🧠 TOPIC EXTRACTION: Starting analysis")
    print(f"   Text length: {len(text)} chars")
    print(f"   Text preview: {text[:100]}...")
    
    try:
        # Call OpenAI API
        api_start = time.time()
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
        api_time = time.time() - api_start
        
        print(f"   OpenAI API call completed ({api_time:.2f}s)")
        
        # Handle response
        if response.status == "incomplete" and response.incomplete_details.reason == "max_output_tokens":
            print("   ⚠️ Token limit reached during extraction")
            if response.output_text:
                content = response.output_text.strip()
                print(f"   Partial response recovered: {content}")
            else:
                print("   ❌ No response text available - token limit hit during reasoning")
                return []
        else:
            content = response.output_text.strip()
            print(f"   ✅ Full response received: {content}")
        
        # Parse the response
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
        
        # Log extraction results
        total_time = time.time() - start_time
        print(f"🧠 TOPIC EXTRACTION: Complete ({total_time:.2f}s)")
        print(f"   Extracted {len(topic_relationships)} topic-relationship pairs")
        
        # Log relationship distribution
        if topic_relationships:
            rel_counts = {}
            for _, rel in topic_relationships:
                rel_counts[rel] = rel_counts.get(rel, 0) + 1
            print(f"   Relationship distribution: {rel_counts}")
        
        return topic_relationships
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ TOPIC EXTRACTION FAILED: {e} ({total_time:.2f}s)")
        import traceback
        traceback.print_exc()
        return []

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