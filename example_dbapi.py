#!/usr/bin/env python3
"""
DB-API 2.0 Compatibility Example

This demonstrates how existing psycopg2 code can be easily converted
to work with wormhole @remote functions with minimal changes.
"""

import psycopg2
from wormhole import remote, cursor, set_connection, transaction


def setup_database(conn):
    """Create example tables"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                stock INTEGER DEFAULT 0
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                product_id INTEGER REFERENCES products(id),
                quantity INTEGER NOT NULL,
                order_date TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Insert sample data
        cur.execute("""
            INSERT INTO products (sku, name, price, stock)
            VALUES 
                ('WIDGET-001', 'Super Widget', 19.99, 100),
                ('GADGET-001', 'Mega Gadget', 49.99, 50),
                ('DOOHICKEY-001', 'Ultra Doohickey', 99.99, 25)
            ON CONFLICT (sku) DO NOTHING
        """)
        
        conn.commit()
        print("✓ Database setup complete")


# ============================================================================
# BEFORE: Traditional psycopg2 code (multiple round-trips)
# ============================================================================

def get_product_info_traditional(conn, sku):
    """Traditional approach - multiple round-trips to database"""
    
    # Query 1: Get product
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM products WHERE sku = %s", (sku,))
        product = cur.fetchone()
        if not product:
            return None
        
        columns = [desc[0] for desc in cur.description]
        product_dict = dict(zip(columns, product))
    
    # Query 2: Get order history
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) as order_count, SUM(quantity) as total_quantity
            FROM orders 
            WHERE product_id = %s
        """, (product_dict['id'],))
        stats = cur.fetchone()
    
    # Query 3: Check if low stock
    with conn.cursor() as cur:
        cur.execute("""
            SELECT AVG(price) as avg_price 
            FROM products 
            WHERE stock > 0
        """)
        avg_price = cur.fetchone()[0]
    
    return {
        "product": product_dict,
        "order_count": stats[0],
        "total_sold": stats[1],
        "is_low_stock": product_dict['stock'] < 10,
        "vs_avg_price": product_dict['price'] - avg_price
    }


# ============================================================================
# AFTER: Wormhole @remote version (single round-trip)
# ============================================================================

@remote
def get_product_info_wormhole(sku):
    """
    Wormhole version - runs entirely server-side.
    
    Notice: Almost identical code! Just using wormhole's cursor() instead of
    conn.cursor(), and it runs server-side automatically.
    """
    
    # Query 1: Get product - EXACT SAME API as psycopg2!
    with cursor() as cur:
        cur.execute("SELECT * FROM products WHERE sku = %s", (sku,))
        product = cur.fetchone()
        if not product:
            return None
        
        # Get column names from description (just like psycopg2)
        columns = [desc[0] for desc in cur.description]
        product_dict = dict(zip(columns, product))
    
    # Query 2: Get order history - same API!
    with cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) as order_count, SUM(quantity) as total_quantity
            FROM orders 
            WHERE product_id = %s
        """, (product_dict['id'],))
        stats = cur.fetchone()
    
    # Query 3: Check average price - same API!
    with cursor() as cur:
        cur.execute("""
            SELECT AVG(price) as avg_price 
            FROM products 
            WHERE stock > 0
        """)
        avg_price = cur.fetchone()[0]
    
    # Return same structure
    return {
        "product": product_dict,
        "order_count": stats[0] if stats[0] else 0,
        "total_sold": stats[1] if stats[1] else 0,
        "is_low_stock": product_dict['stock'] < 10,
        "vs_avg_price": float(product_dict['price']) - float(avg_price or 0)
    }


# ============================================================================
# More Examples: Common psycopg2 patterns
# ============================================================================

@remote
def insert_order(product_sku, quantity):
    """
    Example: INSERT with RETURNING clause
    Works exactly like psycopg2!
    """
    # Get product ID
    with cursor() as cur:
        cur.execute("SELECT id, stock FROM products WHERE sku = %s", (product_sku,))
        result = cur.fetchone()
        if not result:
            raise ValueError(f"Product {product_sku} not found")
        
        product_id, stock = result
        
        if stock < quantity:
            raise ValueError(f"Insufficient stock: have {stock}, need {quantity}")
    
    # Insert order and update stock
    with cursor() as cur:
        # Insert order
        cur.execute("""
            INSERT INTO orders (product_id, quantity)
            VALUES (%s, %s)
            RETURNING id, order_date
        """, (product_id, quantity))
        
        order_id, order_date = cur.fetchone()
        
        # Update stock
        cur.execute("""
            UPDATE products 
            SET stock = stock - %s
            WHERE id = %s
        """, (quantity, product_id))
    
    return {"order_id": order_id, "order_date": str(order_date)}


@remote
def batch_update_prices(price_adjustments):
    """
    Example: Batch operations with executemany-style loop
    """
    updated_count = 0
    
    for sku, new_price in price_adjustments.items():
        with cursor() as cur:
            cur.execute("""
                UPDATE products 
                SET price = %s
                WHERE sku = %s
            """, (new_price, sku))
            
            updated_count += cur.rowcount
    
    return {"updated": updated_count}


@remote
def get_inventory_report():
    """
    Example: Complex query with fetchall()
    """
    with cursor() as cur:
        cur.execute("""
            SELECT 
                p.sku,
                p.name,
                p.stock,
                p.price,
                COALESCE(SUM(o.quantity), 0) as total_sold,
                p.price * p.stock as inventory_value
            FROM products p
            LEFT JOIN orders o ON o.product_id = p.id
            GROUP BY p.id
            ORDER BY inventory_value DESC
        """)
        
        # DB-API standard: fetchall returns list of tuples
        rows = cur.fetchall()
        
        # Get column names (DB-API standard)
        columns = [desc[0] for desc in cur.description]
        
        # Convert to list of dicts
        return [dict(zip(columns, row)) for row in rows]


# ============================================================================
# Demonstration
# ============================================================================

def main():
    """Compare traditional vs wormhole approaches"""
    
    # Connect
    print("Connecting to database...")
    conn = psycopg2.connect(
        dbname="postgres",
        user="postgres",
        host="localhost",
        port=5432
    )
    set_connection(conn)
    
    # Setup
    setup_database(conn)
    
    print("\n" + "="*70)
    print("DB-API 2.0 COMPATIBILITY DEMONSTRATION")
    print("="*70)
    
    # Example 1: Compare traditional vs wormhole
    print("\n1. Getting product info...")
    print("   Traditional (3 round-trips):", end=" ")
    result_trad = get_product_info_traditional(conn, "WIDGET-001")
    print(f"✓ {result_trad['product']['name']}")
    
    print("   Wormhole (1 round-trip):    ", end=" ")
    with transaction():
        result_worm = get_product_info_wormhole("WIDGET-001")
    print(f"✓ {result_worm['product']['name']}")
    
    print(f"\n   Both returned same data: {result_trad['product']['name'] == result_worm['product']['name']}")
    
    # Example 2: Insert order
    print("\n2. Inserting order...")
    with transaction():
        order = insert_order("GADGET-001", 5)
        print(f"   ✓ Created order {order['order_id']}")
    
    # Example 3: Batch update
    print("\n3. Batch updating prices...")
    with transaction():
        result = batch_update_prices({
            "WIDGET-001": 21.99,
            "GADGET-001": 54.99
        })
        print(f"   ✓ Updated {result['updated']} products")
    
    # Example 4: Complex report
    print("\n4. Generating inventory report...")
    with transaction():
        report = get_inventory_report()
        print(f"   ✓ Report has {len(report)} products")
        for item in report:
            print(f"      {item['sku']}: {item['stock']} in stock, "
                  f"${item['inventory_value']:.2f} value")
    
    print("\n" + "="*70)
    print("KEY TAKEAWAYS")
    print("="*70)
    print("✓ DB-API 2.0 compatible - cursor(), execute(), fetchall(), etc.")
    print("✓ Minimal code changes - mostly just import and @remote decorator")
    print("✓ Same API client-side and server-side")
    print("✓ Easy to port existing psycopg2 code")
    print("✓ Works with both %s and $1 parameter styles")
    print()
    print("MIGRATION GUIDE:")
    print("1. Replace 'conn.cursor()' with 'cursor()' from wormhole")
    print("2. Add '@remote' decorator to functions")
    print("3. That's it! Everything else stays the same.")
    
    conn.close()


if __name__ == "__main__":
    main()
