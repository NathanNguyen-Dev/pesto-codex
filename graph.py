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

def update_knowledge_graph(user_id, display_name, topics, slack_ts):
    """
    For each topic, create/update:
      - User node (id, name)
      - Topic node (name)
      - MENTIONS relationship (count, firstMentioned, lastMentioned)
    """
    driver = get_driver()
    with driver.session() as session:
        for topic in topics:
            session.run(
                """
                MERGE (u:User {id: $user_id})
                SET u.name = $display_name
                MERGE (t:Topic {name: $topic})
                MERGE (u)-[r:MENTIONS]->(t)
                ON CREATE SET r.count = 1, r.firstMentioned = $ts, r.lastMentioned = $ts
                ON MATCH SET r.count = r.count + 1, r.lastMentioned = $ts
                """,
                user_id=user_id,
                display_name=display_name,
                topic=topic,
                ts=slack_ts
            )

def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None 