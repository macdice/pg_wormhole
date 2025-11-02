#!/usr/bin/env python3
"""
Example usage of Wormhole for PostgreSQL

This script demonstrates:
1. Setting up a connection
2. Defining remote functions
3. Executing them server-side
4. Transaction management
"""

import psycopg2
from wormhole import remote, query, query_single, query_value, set_connection, transaction


def setup_database(conn):
    """Create example tables for demonstration"""
    with conn.cursor() as cur:
        # Create tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Insert sample data
        cur.execute("""
            INSERT INTO users (username, email)
            VALUES 
                ('alice', 'alice@example.com'),
                ('bob', 'bob@example.com'),
                ('charlie', 'charlie@example.com')
            ON CONFLICT DO NOTHING
        """)
        
        cur.execute("""
            INSERT INTO messages (user_id, content)
            SELECT u.id, 'Hello from ' || u.username
            FROM users u
            WHERE NOT EXISTS (SELECT 1 FROM messages WHERE user_id = u.id)
        """)
        
        conn.commit()
        print("✓ Database setup complete")


# Define remote functions that will run server-side
@remote
def update_user_message_count(user_id):
    """
    Update a user's message count.
    This entire function runs inside PostgreSQL.
    """
    # Count messages (runs via SPI)
    count_result = query(
        "SELECT COUNT(*) as count FROM messages WHERE user_id = $1",
        user_id
    )
    message_count = count_result[0]['count']
    
    # Update user record (runs via SPI)
    query(
        "UPDATE users SET message_count = $1 WHERE id = $2",
        message_count,
        user_id
    )
    
    # Return updated user (runs via SPI)
    user = query(
        "SELECT id, username, message_count FROM users WHERE id = $1",
        user_id
    )
    
    return user[0] if user else None


@remote
def get_user_summary(username):
    """
    Get a summary of a user's activity.
    Demonstrates multiple queries in a single server-side function.
    """
    # Get user
    user = query(
        "SELECT id, username, email, created_at FROM users WHERE username = $1",
        username
    )
    
    if not user:
        return {"error": "User not found"}
    
    user_data = user[0]
    
    # Get message stats
    stats = query("""
        SELECT 
            COUNT(*) as total_messages,
            MAX(created_at) as last_message_at
        FROM messages 
        WHERE user_id = $1
    """, user_data['id'])
    
    stats_data = stats[0] if stats else {"total_messages": 0, "last_message_at": None}
    
    return {
        "user": user_data,
        "stats": stats_data
    }


@remote  
def post_message(user_id, content):
    """
    Post a message and update user stats atomically.
    Demonstrates transactional behavior within a remote function.
    """
    # Insert message
    result = query("""
        INSERT INTO messages (user_id, content, created_at)
        VALUES ($1, $2, NOW())
        RETURNING id
    """, user_id, content)
    
    message_id = result[0]['id']
    
    # Update user's message count
    query("""
        UPDATE users 
        SET message_count = message_count + 1
        WHERE id = $1
    """, user_id)
    
    return {"message_id": message_id, "user_id": user_id}


def main():
    """Main demonstration"""
    
    # Connect to database (adjust connection string as needed)
    print("Connecting to database...")
    conn = psycopg2.connect(
        dbname="postgres",  # Change as needed
        user="postgres",    # Change as needed
        host="localhost",
        port=5432
    )
    set_connection(conn)
    print("✓ Connected")
    
    # Setup database
    setup_database(conn)
    
    print("\n" + "="*60)
    print("WORMHOLE FOR POSTGRESQL - EXAMPLES")
    print("="*60)
    
    # Example 1: Update message counts
    print("\n1. Updating user message counts (server-side)...")
    with transaction():
        result = update_user_message_count(1)
        print(f"   User: {result['username']}, Messages: {result['message_count']}")
    
    # Example 2: Get user summary
    print("\n2. Getting user summary (server-side)...")
    with transaction():
        summary = get_user_summary("alice")
        print(f"   Username: {summary['user']['username']}")
        print(f"   Email: {summary['user']['email']}")
        print(f"   Total messages: {summary['stats']['total_messages']}")
    
    # Example 3: Post a message
    print("\n3. Posting a message (server-side)...")
    with transaction():
        result = post_message(1, "This is a test message from wormhole!")
        print(f"   Created message ID: {result['message_id']}")
    
    # Example 4: Demonstrate single round-trip
    print("\n4. Demonstrating single round-trip efficiency...")
    print("   Without wormhole: 3 round-trips (SELECT, UPDATE, SELECT)")
    print("   With wormhole: 1 round-trip (entire function runs server-side)")
    
    with transaction():
        summary = get_user_summary("bob")
        print(f"   ✓ Got complete summary in single round-trip")
        print(f"     User: {summary['user']['username']}")
        print(f"     Messages: {summary['stats']['total_messages']}")
    
    # Example 5: Show caching
    print("\n5. Function caching...")
    print("   First call: Function installed on server")
    with transaction():
        update_user_message_count(2)
    print("   Second call: Using cached version (instant)")
    with transaction():
        result = update_user_message_count(2)
        print(f"   ✓ Cached execution: {result['username']}")
    
    print("\n" + "="*60)
    print("Examples complete!")
    print("="*60)
    print("\nKey takeaways:")
    print("• All @remote functions ran inside PostgreSQL")
    print("• Each call was a single round-trip to the database")
    print("• Functions are cached and reused automatically")
    print("• Same query() syntax works client-side and server-side")
    print("• Server validates safety before executing any code")
    
    conn.close()


if __name__ == "__main__":
    main()
