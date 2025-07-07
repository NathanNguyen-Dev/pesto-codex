from neo4j import GraphDatabase
import os

# Neo4j connection setup from environment variables
NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USER = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

# Lazy loading for Neo4j driver
_driver = None

def get_driver():
    """Get Neo4j driver with lazy loading."""
    global _driver
    if _driver is None:
        if not NEO4J_URI:
            raise ValueError("NEO4J_URI environment variable is not set")
        if not NEO4J_PASSWORD:
            raise ValueError("NEO4J_PASSWORD environment variable is not set")
        
        print(f"🔌 Connecting to Neo4j at {NEO4J_URI}")
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    return _driver

def update_knowledge_graph_with_relationships(user_id, display_name, topic_relationships, timestamp):
    """
    Enhanced version that creates different relationship types.
    
    Args:
        user_id (str): User identifier
        display_name (str): User's display name
        topic_relationships (list): List of tuples (topic, relationship_type)
        timestamp (str): Timestamp for tracking
    
    Relationship types:
        - MENTIONS: Casual mention in conversation
        - INTERESTED_IN: Expressed interest or wants to learn
        - WORKING_ON: Currently working on projects/topics
        - IS_EXPERT_IN: Has expertise/experience in this area
    """
    driver = get_driver()
    with driver.session() as session:
        for topic, relationship_type in topic_relationships:
            # Validate relationship type
            valid_relationships = ["MENTIONS", "INTERESTED_IN", "WORKING_ON", "IS_EXPERT_IN"]
            if relationship_type not in valid_relationships:
                print(f"⚠️  Invalid relationship type '{relationship_type}', defaulting to 'MENTIONS'")
                relationship_type = "MENTIONS"
            
            # Create dynamic Cypher query based on relationship type
            query = f"""
                MERGE (u:User {{id: $user_id}})
                SET u.name = $display_name
                MERGE (t:Topic {{name: $topic}})
                MERGE (u)-[r:{relationship_type}]->(t)
                ON CREATE SET r.count = 1, r.firstMentioned = $ts, r.lastMentioned = $ts, r.context = $context
                ON MATCH SET r.count = r.count + 1, r.lastMentioned = $ts
            """
            
            # Set context based on relationship type
            context_map = {
                "MENTIONS": "conversation",
                "INTERESTED_IN": "learning_goal", 
                "WORKING_ON": "active_project",
                "IS_EXPERT_IN": "professional_expertise"
            }
            
            session.run(
                query,
                user_id=user_id,
                display_name=display_name,
                topic=topic,
                ts=timestamp,
                context=context_map[relationship_type]
            )

def update_knowledge_graph(user_id, display_name, topics, slack_ts):
    """
    Legacy function for backward compatibility - treats all as MENTIONS.
    Use update_knowledge_graph_with_relationships for enhanced functionality.
    """
    topic_relationships = [(topic, "MENTIONS") for topic in topics]
    update_knowledge_graph_with_relationships(user_id, display_name, topic_relationships, slack_ts)

def get_user_relationships(user_id, relationship_type=None):
    """
    Query user's relationships to topics.
    
    Args:
        user_id (str): User identifier
        relationship_type (str, optional): Filter by specific relationship type
    
    Returns:
        list: List of relationships with topic and metadata
    """
    driver = get_driver()
    with driver.session() as session:
        if relationship_type:
            query = f"""
                MATCH (u:User {{id: $user_id}})-[r:{relationship_type}]->(t:Topic)
                RETURN t.name as topic, r.count as count, r.context as context, 
                       r.firstMentioned as first, r.lastMentioned as last
                ORDER BY r.count DESC
            """
        else:
            query = """
                MATCH (u:User {id: $user_id})-[r]->(t:Topic)
                RETURN t.name as topic, type(r) as relationship, r.count as count, 
                       r.context as context, r.firstMentioned as first, r.lastMentioned as last
                ORDER BY r.count DESC
            """
        
        result = session.run(query, user_id=user_id)
        return [dict(record) for record in result]

def get_topic_experts(topic_name, limit=10):
    """
    Find users who are experts in a specific topic.
    
    Args:
        topic_name (str): Topic to find experts for
        limit (int): Maximum number of experts to return
    
    Returns:
        list: List of users with their expertise level
    """
    driver = get_driver()
    with driver.session() as session:
        query = """
            MATCH (u:User)-[r:IS_EXPERT_IN]->(t:Topic {name: $topic_name})
            RETURN u.id as user_id, u.name as name, r.count as expertise_level
            ORDER BY r.count DESC
            LIMIT $limit
        """
        
        result = session.run(query, topic_name=topic_name, limit=limit)
        return [dict(record) for record in result]

def get_users_working_on_topic(topic_name, limit=10):
    """
    Find users who are currently working on a specific topic.
    
    Args:
        topic_name (str): Topic to find active workers for
        limit (int): Maximum number of users to return
    
    Returns:
        list: List of users actively working on the topic
    """
    driver = get_driver()
    with driver.session() as session:
        query = """
            MATCH (u:User)-[r:WORKING_ON]->(t:Topic {name: $topic_name})
            RETURN u.id as user_id, u.name as name, r.count as activity_level,
                   r.lastMentioned as last_activity
            ORDER BY r.count DESC, r.lastMentioned DESC
            LIMIT $limit
        """
        
        result = session.run(query, topic_name=topic_name, limit=limit)
        return [dict(record) for record in result]

def get_users_interested_in_topic(topic_name, limit=10):
    """
    Find users who are interested in learning about a specific topic.
    
    Args:
        topic_name (str): Topic to find interested learners for
        limit (int): Maximum number of users to return
    
    Returns:
        list: List of users interested in the topic
    """
    driver = get_driver()
    with driver.session() as session:
        query = """
            MATCH (u:User)-[r:INTERESTED_IN]->(t:Topic {name: $topic_name})
            RETURN u.id as user_id, u.name as name, r.count as interest_level,
                   r.lastMentioned as last_mentioned
            ORDER BY r.count DESC, r.lastMentioned DESC
            LIMIT $limit
        """
        
        result = session.run(query, topic_name=topic_name, limit=limit)
        return [dict(record) for record in result]

def get_relevant_users_for_topics(topics, exclude_user_id=None, limit=5):
    """
    Find the most relevant users for a list of topics across all relationship types.
    Prioritizes experts, then active workers, then interested learners.
    
    Args:
        topics (list): List of topic names to find relevant users for
        exclude_user_id (str, optional): User ID to exclude from results (e.g., message author)
        limit (int): Maximum number of users to return per topic
    
    Returns:
        dict: Dictionary mapping topics to lists of relevant users
    """
    import time
    start_time = time.time()
    
    print(f"📊 GRAPH QUERY: Finding relevant users for {len(topics)} topics")
    print(f"   Topics: {topics}")
    print(f"   Exclude user: {exclude_user_id}")
    print(f"   Limit per topic: {limit}")
    
    driver = get_driver()
    results = {}
    
    try:
        with driver.session() as session:
            for i, topic in enumerate(topics):
                print(f"   Querying topic {i+1}/{len(topics)}: '{topic}'")
                
                # Build query to find users with any relationship to this topic
                # Order by relationship priority and activity level
                query = """
                    MATCH (u:User)-[r]->(t:Topic {name: $topic_name})
                    WHERE NOT u.id = $exclude_user_id
                    RETURN u.id as user_id, u.name as name, type(r) as relationship,
                           r.count as activity_level, r.lastMentioned as last_activity
                    ORDER BY 
                        CASE type(r)
                            WHEN 'IS_EXPERT_IN' THEN 1
                            WHEN 'WORKING_ON' THEN 2
                            WHEN 'INTERESTED_IN' THEN 3
                            ELSE 4
                        END,
                        r.count DESC,
                        r.lastMentioned DESC
                    LIMIT $limit
                """
                
                query_start = time.time()
                result = session.run(query, topic_name=topic, exclude_user_id=exclude_user_id, limit=limit)
                topic_users = [dict(record) for record in result]
                query_time = time.time() - query_start
                
                print(f"     Found {len(topic_users)} users ({query_time:.2f}s)")
                
                if topic_users:
                    results[topic] = topic_users
                    
                    # Log user details
                    rel_counts = {}
                    for user in topic_users:
                        rel = user['relationship']
                        rel_counts[rel] = rel_counts.get(rel, 0) + 1
                    
                    print(f"     Relationship distribution: {rel_counts}")
                    
                    # Log top users
                    for j, user in enumerate(topic_users[:3]):  # Show top 3
                        print(f"       {j+1}. {user['name']} ({user['relationship']}, activity: {user['activity_level']})")
                else:
                    print(f"     No users found for topic '{topic}'")
        
        total_time = time.time() - start_time
        unique_users = set()
        total_matches = 0
        
        for topic_users in results.values():
            total_matches += len(topic_users)
            for user in topic_users:
                unique_users.add(user['user_id'])
        
        print(f"📊 GRAPH QUERY: Complete ({total_time:.2f}s)")
        print(f"   Total matches: {total_matches}")
        print(f"   Unique users: {len(unique_users)}")
        print(f"   Topics with results: {len(results)}/{len(topics)}")
        
        return results
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ GRAPH QUERY FAILED: {e} ({total_time:.2f}s)")
        import traceback
        traceback.print_exc()
        return {}

def get_community_interests():
    """
    Get community-wide interest analysis across all relationship types.
    
    Returns:
        dict: Analysis of topics by relationship type
    """
    driver = get_driver()
    with driver.session() as session:
        query = """
            MATCH (u:User)-[r]->(t:Topic)
            RETURN t.name as topic, type(r) as relationship, 
                   count(r) as total_connections, 
                   count(DISTINCT u) as unique_users
            ORDER BY total_connections DESC
        """
        
        result = session.run(query)
        relationships = {}
        
        for record in result:
            rel_type = record["relationship"]
            if rel_type not in relationships:
                relationships[rel_type] = []
            
            relationships[rel_type].append({
                "topic": record["topic"],
                "total_connections": record["total_connections"],
                "unique_users": record["unique_users"]
            })
        
        return relationships

def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None 