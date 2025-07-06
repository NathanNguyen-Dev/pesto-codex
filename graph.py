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