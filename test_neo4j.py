#!/usr/bin/env python3
"""
Test script for Neo4j Aura connection and graph functions.
Run this to verify everything works before starting the Slack bot.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_neo4j_connection():
    """Test basic Neo4j connection."""
    print("🔌 Testing Neo4j connection...")
    
    try:
        from graph import get_driver
        
        driver = get_driver()
        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            print(f"✅ Neo4j connected! Test query returned: {record['test']}")
            return True
            
    except Exception as e:
        print(f"❌ Neo4j connection failed: {e}")
        return False

def test_topic_extraction():
    """Test OpenAI topic extraction."""
    print("\n🧠 Testing OpenAI topic extraction...")
    
    try:
        from nlp import extract_topics
        
        test_message = "I'm really excited about machine learning and artificial intelligence. I've been working on some deep learning projects with PyTorch lately."
        topics = extract_topics(test_message)
        
        print(f"✅ Topics extracted: {topics}")
        return topics
        
    except Exception as e:
        print(f"❌ Topic extraction failed: {e}")
        return False

def test_graph_update():
    """Test full pipeline: topic extraction + Neo4j update."""
    print("\n📊 Testing full graph update pipeline...")
    
    topics = test_topic_extraction()
    if not topics:
        print("❌ Skipping graph update - no topics extracted")
        return False
    
    try:
        from graph import update_knowledge_graph
        import time
        
        # Test data
        test_user_id = "U_TEST_USER"
        test_display_name = "Test User"
        test_timestamp = str(int(time.time()))
        
        update_knowledge_graph(test_user_id, test_display_name, topics, test_timestamp)
        print(f"✅ Graph updated successfully for user {test_user_id}")
        
        # Verify the data was written
        from graph import get_driver
        driver = get_driver()
        with driver.session() as session:
            result = session.run(
                "MATCH (u:User {id: $user_id})-[r:MENTIONS]->(t:Topic) RETURN u.name, t.name, r.count",
                user_id=test_user_id
            )
            records = list(result)
            print(f"✅ Verification: Found {len(records)} topic mentions for {test_user_id}")
            for record in records:
                print(f"   - {record['u.name']} mentions '{record['t.name']}' (count: {record['r.count']})")
        
        return True
        
    except Exception as e:
        print(f"❌ Graph update failed: {e}")
        return False

def test_constraints():
    """Add recommended Neo4j constraints for better performance."""
    print("\n🔧 Adding Neo4j constraints...")
    
    try:
        from graph import get_driver
        
        driver = get_driver()
        constraints = [
            "CREATE CONSTRAINT FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT FOR (t:Topic) REQUIRE t.name IS UNIQUE"
        ]
        
        with driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    print(f"✅ Added constraint: {constraint}")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"⚠️  Constraint already exists: {constraint}")
                    else:
                        print(f"❌ Failed to add constraint: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Constraint setup failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Neo4j & Graph Pipeline Test Suite")
    print("=" * 50)
    
    # Check environment variables
    required_vars = ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {missing_vars}")
        print("Please add them to your .env file and try again.")
        exit(1)
    
    # Run tests
    success = True
    success &= test_neo4j_connection()
    topics_result = test_topic_extraction()
    success &= bool(topics_result)  # Convert topics list to boolean
    success &= test_graph_update()
    success &= test_constraints()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 All tests passed! Your pipeline is ready.")
        print("\nNext steps:")
        print("1. Start your Slack bot: python app.py")
        print("2. Send messages in Slack")
        print("3. Check Neo4j Browser for your knowledge graph")
    else:
        print("❌ Some tests failed. Check the errors above.") 