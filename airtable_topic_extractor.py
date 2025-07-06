"""
Standalone Airtable Interest Extractor with Neo4j Integration
Reads InfoText from Airtable records, extracts professional interests with relationship types using OpenAI, and stores in Neo4j
"""

import os
import time
import argparse
from dotenv import load_dotenv
from pyairtable import Api
from nlp import extract_interests_with_relationships
from graph import update_knowledge_graph_with_relationships

# Load environment variables
load_dotenv()

# Configuration
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")

def get_airtable_records(base_id, table_name, info_text_column="InfoText", name_column="Name", slack_id_column="Slack ID"):
    """
    Fetch all records from Airtable that have InfoText data.
    
    Args:
        base_id (str): Airtable base ID
        table_name (str): Name of the Airtable table
        info_text_column (str): Name of the column containing info text
        name_column (str): Name of the column containing user names
        slack_id_column (str): Name of the column containing Slack IDs
    
    Returns:
        list: List of records with InfoText data
    """
    print(f"🔄 Fetching records from Airtable...")
    print(f"   Base ID: {base_id}")
    print(f"   Table: {table_name}")
    print(f"   InfoText Column: {info_text_column}")
    print(f"   Name Column: {name_column}")
    print(f"   Slack ID Column: {slack_id_column}")
    
    try:
        api = Api(AIRTABLE_API_KEY)
        airtable_table = api.table(base_id, table_name)
        
        # Get all records
        all_records = airtable_table.all()
        
        # Filter records that have InfoText data
        records_with_info = []
        for record in all_records:
            fields = record.get("fields", {})
            info_text = fields.get(info_text_column, "").strip()
            
            if info_text:  # Only include records with InfoText content
                # Use Slack ID if available, otherwise generate a unique ID from record ID
                slack_id = fields.get(slack_id_column, "").strip()
                user_id = slack_id if slack_id else f"airtable_{record['id']}"
                
                records_with_info.append({
                    "record_id": record["id"],
                    "user_id": user_id,  # For Neo4j (Slack ID or generated ID)
                    "name": fields.get(name_column, "Unknown"),
                    "slack_id": slack_id,
                    "info_text": info_text,
                    "fields": fields  # Keep all fields for reference
                })
        
        print(f"✅ Found {len(all_records)} total records")
        print(f"✅ Found {len(records_with_info)} records with InfoText data")
        
        return records_with_info
        
    except Exception as e:
        print(f"❌ Error fetching from Airtable: {e}")
        return []

def extract_interests_from_records(records, rate_limit_delay=1.0):
    """
    Extract professional interests with relationship types from InfoText for each record.
    
    Args:
        records (list): List of records with InfoText
        rate_limit_delay (float): Delay between API calls to avoid rate limits
    
    Returns:
        list: Records with extracted interest-relationship pairs added
    """
    print(f"\n🧠 Extracting professional interests with relationship types from {len(records)} records...")
    
    processed_records = []
    
    for i, record in enumerate(records, 1):
        name = record["name"]
        info_text = record["info_text"]
        
        print(f"\n📝 Processing {i}/{len(records)}: {name}")
        print(f"   InfoText preview: {info_text[:150]}...")
        
        try:
            # Extract interests with relationship types using the enhanced nlp function
            interest_relationships = extract_interests_with_relationships(info_text)
            
            # Add interest-relationship pairs to record
            record["interest_relationships"] = interest_relationships
            processed_records.append(record)
            
            # Display the results with relationship types
            print(f"   ✅ Extracted {len(interest_relationships)} interest-relationship pairs:")
            for interest, relationship in interest_relationships:
                print(f"      • {interest} ({relationship})")
            
            # Rate limiting to avoid OpenAI API limits
            if i < len(records):
                print(f"   ⏳ Waiting {rate_limit_delay}s before next extraction...")
                time.sleep(rate_limit_delay)
                
        except Exception as e:
            print(f"   ❌ Error extracting interests for {name}: {e}")
            # Still add the record but with empty interest relationships
            record["interest_relationships"] = []
            processed_records.append(record)
            continue
    
    print(f"\n✅ Interest extraction completed for {len(processed_records)} records")
    return processed_records

def save_interests_to_neo4j(records):
    """
    Save extracted interests with relationship types to Neo4j knowledge graph.
    
    Args:
        records (list): Records with extracted interest-relationship pairs
    
    Returns:
        int: Number of records successfully saved to Neo4j
    """
    print(f"\n📊 Saving interests with relationship types to Neo4j knowledge graph...")
    
    saved_count = 0
    current_timestamp = str(int(time.time()))  # Use current time as timestamp
    
    for i, record in enumerate(records, 1):
        user_id = record["user_id"]
        name = record["name"]
        interest_relationships = record["interest_relationships"]
        
        if not interest_relationships:
            print(f"   ⚠️  Skipping {i}/{len(records)}: {name} - No interests extracted")
            continue
        
        try:
            # Use the enhanced graph update function with relationship types
            update_knowledge_graph_with_relationships(user_id, name, interest_relationships, current_timestamp)
            
            # Count relationships by type for display
            relationship_counts = {}
            for _, rel_type in interest_relationships:
                relationship_counts[rel_type] = relationship_counts.get(rel_type, 0) + 1
            
            rel_summary = ", ".join([f"{count} {rel_type}" for rel_type, count in relationship_counts.items()])
            print(f"   ✅ Saved {i}/{len(records)}: {name} -> Neo4j ({rel_summary})")
            saved_count += 1
            
            # Small delay to avoid overwhelming Neo4j
            time.sleep(0.1)
            
        except Exception as e:
            print(f"   ❌ Failed to save {name} to Neo4j: {e}")
            continue
    
    print(f"\n✅ Successfully saved {saved_count}/{len(records)} records to Neo4j")
    return saved_count

def print_interest_summary(records):
    """
    Print a detailed summary of all extracted interests and relationship types.
    
    Args:
        records (list): Records with extracted interest-relationship pairs
    """
    print(f"\n📊 PROFESSIONAL INTEREST & RELATIONSHIP EXTRACTION SUMMARY")
    print("=" * 65)
    
    # Count all interests by relationship type
    relationship_data = {
        "IS_EXPERT_IN": [],
        "WORKING_ON": [],
        "INTERESTED_IN": []
    }
    
    all_interests = []
    
    for record in records:
        for interest, rel_type in record["interest_relationships"]:
            all_interests.append(interest)
            if rel_type in relationship_data:
                relationship_data[rel_type].append(interest)
    
    # Count frequency of each interest
    interest_count = {}
    for interest in all_interests:
        interest_count[interest] = interest_count.get(interest, 0) + 1
    
    # Sort by frequency
    sorted_interests = sorted(interest_count.items(), key=lambda x: x[1], reverse=True)
    
    print(f"Total interest connections: {len(all_interests)}")
    print(f"Unique interests: {len(sorted_interests)}")
    
    # Show breakdown by relationship type
    print(f"\nBreakdown by relationship type:")
    for rel_type, interests in relationship_data.items():
        unique_interests = len(set(interests))
        total_connections = len(interests)
        print(f"  {rel_type}: {total_connections} connections ({unique_interests} unique interests)")
    
    print(f"\nTop interests overall (by frequency):")
    for interest, count in sorted_interests[:15]:  # Show top 15
        print(f"  {count:2d}x - {interest}")
    
    # Show top interests by relationship type
    for rel_type, interests in relationship_data.items():
        if interests:
            rel_count = {}
            for interest in interests:
                rel_count[interest] = rel_count.get(interest, 0) + 1
            
            sorted_rel = sorted(rel_count.items(), key=lambda x: x[1], reverse=True)
            print(f"\nTop {rel_type} interests:")
            for interest, count in sorted_rel[:8]:  # Show top 8 for each type
                print(f"  {count:2d}x - {interest}")
    
    print(f"\nPer-person breakdown:")
    for record in records:
        name = record["name"]
        interest_relationships = record["interest_relationships"]
        
        if interest_relationships:
            rel_summary = {}
            for interest, rel_type in interest_relationships:
                if rel_type not in rel_summary:
                    rel_summary[rel_type] = []
                rel_summary[rel_type].append(interest)
            
            print(f"  {name}:")
            for rel_type, interests in rel_summary.items():
                print(f"    {rel_type}: {interests}")

def main():
    """
    Main function to run the interest extraction process.
    """
    parser = argparse.ArgumentParser(description='Extract professional interests with relationship types from Airtable InfoText and save to Neo4j')
    parser.add_argument('--base-id', type=str, help='Airtable Base ID (overrides env variable)')
    parser.add_argument('--table', type=str, required=True, help='Airtable table name')
    parser.add_argument('--info-column', type=str, default='InfoText', help='InfoText column name (default: InfoText)')
    parser.add_argument('--name-column', type=str, default='Name', help='Name column name (default: Name)')
    parser.add_argument('--slack-id-column', type=str, default='Slack ID', help='Slack ID column name (default: Slack ID)')
    parser.add_argument('--rate-limit', type=float, default=1.5, help='Rate limit delay in seconds (default: 1.5)')
    parser.add_argument('--dry-run', action='store_true', help='Extract interests but do not save to Neo4j')
    
    args = parser.parse_args()
    
    print("🚀 AIRTABLE INTEREST EXTRACTOR -> NEO4J (Enhanced with Relationship Types)")
    print("=" * 75)
    
    # Use provided base ID or fall back to environment variable
    base_id = args.base_id or AIRTABLE_BASE_ID
    if not base_id:
        print("❌ No Airtable Base ID provided. Use --base-id or set AIRTABLE_BASE_ID in .env")
        return
    
    print(f"Configuration:")
    print(f"  Base ID: {base_id}")
    print(f"  Table: {args.table}")
    print(f"  InfoText Column: {args.info_column}")
    print(f"  Name Column: {args.name_column}")
    print(f"  Slack ID Column: {args.slack_id_column}")
    print(f"  Rate Limit: {args.rate_limit}s")
    print(f"  Dry Run: {args.dry_run}")
    print(f"\n🔗 Relationship Types: IS_EXPERT_IN, WORKING_ON, INTERESTED_IN")
    print()
    
    # Step 1: Fetch records from Airtable
    records = get_airtable_records(
        base_id, 
        args.table, 
        args.info_column, 
        args.name_column, 
        args.slack_id_column
    )
    
    if not records:
        print("❌ No records found with InfoText data. Exiting.")
        return
    
    # Step 2: Extract interests with relationship types from InfoText
    records_with_interests = extract_interests_from_records(records, args.rate_limit)
    
    # Step 3: Print detailed summary
    print_interest_summary(records_with_interests)
    
    # Step 4: Save to Neo4j (unless dry run)
    if not args.dry_run:
        save_interests_to_neo4j(records_with_interests)
    else:
        print(f"\n⚠️  DRY RUN: Skipping Neo4j save")
    
    print(f"\n🎉 Professional interest extraction with relationship types completed!")

if __name__ == "__main__":
    main() 