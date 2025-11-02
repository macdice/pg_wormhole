# Migrating Existing psycopg2 Code to Wormhole

This guide shows how to convert existing psycopg2 code to use Wormhole for server-side execution with minimal changes.

## TL;DR - The 3-Step Migration

1. Import `cursor` from `wormhole` instead of using `conn.cursor()`
2. Add `@remote` decorator to functions you want to run server-side
3. Done! Everything else stays the same.

## Why Migrate?

**Performance**: Reduce multiple round-trips to a single one
**Same API**: DB-API 2.0 compatible, minimal code changes
**Easy**: Usually just adding a decorator and changing import

## Parameter Styles

Wormhole supports both parameter styles automatically:

```python
# Both of these work!
cursor.execute("SELECT * FROM users WHERE id = %s", (42,))
cursor.execute("SELECT * FROM users WHERE id = $1", (42,))
```

Client-side: Converts to psycopg2's `%s` style
Server-side: Converts to PostgreSQL's `$1` style

## Migration Examples

### Example 1: Simple Query Function

**Before (Traditional psycopg2):**
```python
import psycopg2

def get_user(conn, user_id):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))

# Usage
conn = psycopg2.connect(...)
user = get_user(conn, 42)  # Round-trip to database
```

**After (Wormhole):**
```python
import psycopg2
from wormhole import remote, cursor, set_connection

@remote  # ← Add decorator
def get_user(user_id):  # ← Remove conn parameter
    with cursor() as cur:  # ← Use wormhole cursor instead of conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))

# Usage
conn = psycopg2.connect(...)
set_connection(conn)  # ← Set connection once
user = get_user(42)  # Same call, but runs server-side!
```

### Example 2: Multiple Queries

**Before (3 round-trips):**
```python
def get_order_details(conn, order_id):
    # Query 1: Get order
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    
    # Query 2: Get items
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
        items = cur.fetchall()
    
    # Query 3: Get customer
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM customers WHERE id = %s", (order['customer_id'],))
        customer = cur.fetchone()
    
    return {"order": order, "items": items, "customer": customer}
```

**After (1 round-trip):**
```python
from wormhole import remote, cursor

@remote  # ← Just add this!
def get_order_details(order_id):
    # Everything else is identical!
    with cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    
    with cursor() as cur:
        cur.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
        items = cur.fetchall()
    
    with cursor() as cur:
        cur.execute("SELECT * FROM customers WHERE id = %s", (order['customer_id'],))
        customer = cur.fetchone()
    
    return {"order": order, "items": items, "customer": customer}
```

### Example 3: Transactions

**Before:**
```python
def transfer_money(conn, from_account, to_account, amount):
    try:
        with conn.cursor() as cur:
            # Check balance
            cur.execute("SELECT balance FROM accounts WHERE id = %s", (from_account,))
            balance = cur.fetchone()[0]
            
            if balance < amount:
                raise ValueError("Insufficient funds")
            
            # Debit
            cur.execute(
                "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                (amount, from_account)
            )
            
            # Credit
            cur.execute(
                "UPDATE accounts SET balance = balance + %s WHERE id = %s",
                (amount, to_account)
            )
        
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

**After:**
```python
from wormhole import remote, cursor, transaction

@remote
def transfer_money(from_account, to_account, amount):
    # Exact same code, just using wormhole cursor
    with cursor() as cur:
        cur.execute("SELECT balance FROM accounts WHERE id = %s", (from_account,))
        balance = cur.fetchone()[0]
        
        if balance < amount:
            raise ValueError("Insufficient funds")
        
        cur.execute(
            "UPDATE accounts SET balance = balance - %s WHERE id = %s",
            (amount, from_account)
        )
        
        cur.execute(
            "UPDATE accounts SET balance = balance + %s WHERE id = %s",
            (amount, to_account)
        )

# Usage with automatic retry
with transaction():
    transfer_money(1, 2, 100.00)
```

### Example 4: Batch Operations

**Before:**
```python
def import_products(conn, products):
    with conn.cursor() as cur:
        for product in products:
            cur.execute(
                "INSERT INTO products (sku, name, price) VALUES (%s, %s, %s)",
                (product['sku'], product['name'], product['price'])
            )
    conn.commit()
```

**After:**
```python
from wormhole import remote, cursor

@remote
def import_products(products):
    with cursor() as cur:
        for product in products:
            cur.execute(
                "INSERT INTO products (sku, name, price) VALUES (%s, %s, %s)",
                (product['sku'], product['name'], product['price'])
            )
```

### Example 5: Complex Reporting

**Before:**
```python
def generate_sales_report(conn, start_date, end_date):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                DATE(order_date) as date,
                COUNT(*) as order_count,
                SUM(total) as revenue
            FROM orders
            WHERE order_date BETWEEN %s AND %s
            GROUP BY DATE(order_date)
            ORDER BY date
        """, (start_date, end_date))
        
        columns = [desc[0] for desc in cur.description]
        results = []
        for row in cur.fetchall():
            results.append(dict(zip(columns, row)))
        
        return results
```

**After:**
```python
from wormhole import remote, cursor

@remote
def generate_sales_report(start_date, end_date):
    # Identical code!
    with cursor() as cur:
        cur.execute("""
            SELECT 
                DATE(order_date) as date,
                COUNT(*) as order_count,
                SUM(total) as revenue
            FROM orders
            WHERE order_date BETWEEN %s AND %s
            GROUP BY DATE(order_date)
            ORDER BY date
        """, (start_date, end_date))
        
        columns = [desc[0] for desc in cur.description]
        results = []
        for row in cur.fetchall():
            results.append(dict(zip(columns, row)))
        
        return results
```

## DB-API 2.0 Compatibility

Wormhole's cursor supports all standard DB-API 2.0 methods:

| Method | Supported | Notes |
|--------|-----------|-------|
| `execute(sql, params)` | ✅ | Both %s and $1 styles |
| `fetchone()` | ✅ | Returns tuple |
| `fetchmany(size)` | ✅ | Returns list of tuples |
| `fetchall()` | ✅ | Returns list of tuples |
| `description` | ✅ | Column metadata |
| `rowcount` | ✅ | Rows affected/returned |
| `close()` | ✅ | Cleanup |
| `__enter__` / `__exit__` | ✅ | Context manager |

### Wormhole Extensions

Additional methods for convenience:

```python
# Get results as dictionaries instead of tuples
cursor.fetchone_dict()   # Returns dict or None
cursor.fetchall_dict()   # Returns list of dicts
```

## What Can't Be Migrated (Yet)

Some psycopg2 features aren't supported yet:

### Not Supported
- ❌ `executemany()` - Use a loop instead
- ❌ `callproc()` - Call procedures via `execute()`
- ❌ Named cursors (server-side cursors)
- ❌ `copy_from()` / `copy_to()` - Use regular INSERT/SELECT
- ❌ Custom type adapters
- ❌ NOTIFY/LISTEN

### Workarounds

**For executemany:**
```python
# Instead of:
cursor.executemany("INSERT INTO ...", rows)

# Do:
for row in rows:
    cursor.execute("INSERT INTO ...", row)
```

**For COPY:**
```python
# Instead of:
cursor.copy_from(file, 'table')

# Do:
for row in csv_reader:
    cursor.execute("INSERT INTO table VALUES (%s, %s)", row)
```

## Migration Checklist

- [ ] Install wormhole: `pip install wormhole-pg`
- [ ] Install SQL schema: `psql -f schema.sql`
- [ ] Identify functions with multiple queries
- [ ] Add `from wormhole import remote, cursor, set_connection`
- [ ] Add `@remote` decorator to functions
- [ ] Replace `conn.cursor()` with `cursor()`
- [ ] Remove `conn` parameter from function signatures
- [ ] Call `set_connection(conn)` once at startup
- [ ] Test with your data
- [ ] Measure performance improvement

## Performance Tips

### Good Candidates for Migration

✅ Functions with 2+ queries
✅ Complex business logic with database access
✅ Report generation
✅ Data validation workflows
✅ Batch processing

### Poor Candidates

❌ Single simple queries (no benefit)
❌ Functions that need to stream large results
❌ Code that needs COPY or bulk operations

## Common Patterns

### Pattern 1: Reusable Query Functions

```python
# Before: Utility function
def get_user_by_email(conn, email):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()

# After: Still a utility, but can be called from @remote functions
@remote
def get_user_by_email(email):
    with cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()

# Can be called from other @remote functions!
@remote
def validate_login(email, password):
    user = get_user_by_email(email)  # This works!
    # ... validate password ...
```

### Pattern 2: Connection Management

```python
# Application setup (once)
import psycopg2
from wormhole import set_connection

conn = psycopg2.connect(...)
set_connection(conn)

# Now all @remote functions work without passing conn around
```

### Pattern 3: Transaction Management

```python
from wormhole import transaction

# Automatic retry on serialization failure
with transaction(max_retries=5):
    result = my_remote_function()
```

## Troubleshooting

### "No database connection set"
```python
# Make sure you call this:
from wormhole import set_connection
set_connection(conn)
```

### "Module 'X' is not allowed"
```sql
-- Admin adds to whitelist:
INSERT INTO wormhole_allowed_modules (module_name, allowed)
VALUES ('your_module', true);
```

### "Can't get function source"
Functions must be defined in .py files, not in REPL:
```python
# ✗ Won't work in REPL
>>> @remote
... def func(): pass

# ✓ Works in a .py file
# myfile.py
@remote
def func(): pass
```

## Benefits

**Before Wormhole:**
- Multiple round-trips
- Network latency × N
- Complex connection management
- Manual transaction handling

**After Wormhole:**
- Single round-trip
- Network latency × 1
- Simple connection setup
- Automatic transaction retry

## Real-World Example

Here's a complete before/after from a real application:

**Before (5 queries, ~50ms):**
```python
def process_order(conn, order_id):
    # Query 1: Get order
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    
    # Query 2: Get items
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
        items = cur.fetchall()
    
    # Query 3: Check inventory
    for item in items:
        with conn.cursor() as cur:
            cur.execute("SELECT stock FROM inventory WHERE product_id = %s", (item['product_id'],))
            stock = cur.fetchone()[0]
            if stock < item['quantity']:
                raise ValueError("Insufficient stock")
    
    # Query 4: Update inventory
    for item in items:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE inventory SET stock = stock - %s WHERE product_id = %s",
                (item['quantity'], item['product_id'])
            )
    
    # Query 5: Update order status
    with conn.cursor() as cur:
        cur.execute("UPDATE orders SET status = 'processed' WHERE id = %s", (order_id,))
    
    conn.commit()
```

**After (1 call, ~15ms):**
```python
from wormhole import remote, cursor

@remote  # ← Only change!
def process_order(order_id):
    # Exact same logic, but all runs server-side
    with cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    
    with cursor() as cur:
        cur.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
        items = cur.fetchall()
    
    for item in items:
        with cursor() as cur:
            cur.execute("SELECT stock FROM inventory WHERE product_id = %s", (item['product_id'],))
            stock = cur.fetchone()[0]
            if stock < item['quantity']:
                raise ValueError("Insufficient stock")
    
    for item in items:
        with cursor() as cur:
            cur.execute(
                "UPDATE inventory SET stock = stock - %s WHERE product_id = %s",
                (item['quantity'], item['product_id'])
            )
    
    with cursor() as cur:
        cur.execute("UPDATE orders SET status = 'processed' WHERE id = %s", (order_id,))

# 3x faster!
```

## Next Steps

1. Try the DB-API example: `python example_dbapi.py`
2. Migrate one function at a time
3. Measure performance improvements
4. Share your results!

---

**Questions?** Check out the full documentation in README.md or ARCHITECTURE.md
