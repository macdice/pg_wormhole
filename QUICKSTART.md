# Wormhole for PostgreSQL - Quick Start Guide

## What You've Got

A complete, working implementation of the "wormhole" concept for PostgreSQL with Python!

## Project Structure

```
wormhole-pg/
├── schema.sql              # PostgreSQL server-side infrastructure
├── setup.py                # Python package setup
├── requirements.txt        # Python dependencies
├── README.md               # Full documentation
├── example.py              # Complete working examples
├── test_smoke.py           # Basic functionality tests
└── wormhole/               # Python client library
    ├── __init__.py         # Package exports
    ├── connection.py       # Connection management
    ├── query.py            # Query abstraction layer
    ├── remote.py           # @remote decorator (the magic!)
    └── transaction.py      # Transaction retry logic
```

## Installation (5 minutes)

### 1. Install PostgreSQL Extension

```bash
# As PostgreSQL superuser
psql -U postgres -d your_database -f schema.sql
```

This creates the server-side infrastructure:
- `wormhole_install()` - Validates and caches Python functions
- `wormhole_execute()` - Runs cached functions with security sandbox
- `wormhole_query()` - Query API for server-side code
- Module whitelist table
- Function cache table

### 2. Install Python Package

```bash
pip install psycopg2-binary
cd wormhole-pg
pip install -e .
```

### 3. Verify Installation

```bash
python test_smoke.py
```

Should show: ✓ All smoke tests passed!

## Your First Wormhole Function (2 minutes)

```python
import psycopg2
from wormhole import remote, query, set_connection, transaction

# Connect
conn = psycopg2.connect("dbname=mydb user=myuser")
set_connection(conn)

# Define a function that runs SERVER-SIDE
@remote
def count_users():
    result = query("SELECT COUNT(*) as count FROM users")
    return result[0]['count']

# Call it - runs entirely in PostgreSQL!
with transaction():
    count = count_users()
    print(f"Users: {count}")
```

## How It Works

1. **You write a Python function** with the `@remote` decorator
2. **On first call**, the client:
   - Serializes the function source code
   - Calls `wormhole_install()` on the server
3. **Server validates** the code:
   - Parses AST to find imports
   - Checks imports against whitelist
   - Blocks dangerous operations (eval, file I/O, etc.)
   - Caches the function if safe
4. **Client calls** `wormhole_execute()` with arguments
5. **Server runs** the cached function with restricted namespace
6. **Results returned** as JSON

## Key Features

### ✅ Security First
- Server-side validation of all code
- Admin-controlled module whitelist
- Sandboxed execution environment
- Audit trail of all installed functions

### ✅ Performance
- Single round-trip to database
- Functions cached and reused
- No repeated compilation

### ✅ Same API Everywhere
```python
# Client-side
query("SELECT * FROM users WHERE id = $1", user_id)

# Server-side (in @remote function)
query("SELECT * FROM users WHERE id = $1", user_id)
# Exact same syntax! Uses SPI internally.
```

### ✅ Transaction Management
```python
with transaction(max_retries=5):
    # Automatically retried on:
    # - Serialization failures
    # - Deadlocks
    # - Read-only standby errors
    result = my_remote_function()
```

## Example Use Cases

### 1. Complex Aggregations

Instead of multiple round-trips:
```python
# Bad: 3 round-trips
user = query("SELECT * FROM users WHERE id = $1", user_id)
orders = query("SELECT * FROM orders WHERE user_id = $1", user_id)
total = query("SELECT SUM(amount) FROM orders WHERE user_id = $1", user_id)
```

Do this:
```python
# Good: 1 round-trip
@remote
def get_user_dashboard(user_id):
    user = query("SELECT * FROM users WHERE id = $1", user_id)[0]
    orders = query("SELECT * FROM orders WHERE user_id = $1", user_id)
    total = query("SELECT SUM(amount) FROM orders WHERE user_id = $1", user_id)[0]
    return {"user": user, "orders": orders, "total": total['sum']}

dashboard = get_user_dashboard(123)
```

### 2. Transactional Workflows

```python
@remote
def transfer_funds(from_account, to_account, amount):
    # Check balance
    balance = query(
        "SELECT balance FROM accounts WHERE id = $1", 
        from_account
    )[0]['balance']
    
    if balance < amount:
        raise Exception("Insufficient funds")
    
    # Transfer
    query("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, from_account)
    query("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, to_account)
    query("INSERT INTO transactions (from_id, to_id, amount) VALUES ($1, $2, $3)",
          from_account, to_account, amount)
    
    return {"success": True}

# Atomic, single round-trip
with transaction():
    transfer_funds(1, 2, 100.00)
```

### 3. Data Validation and Processing

```python
@remote
def validate_and_import_data(csv_data):
    import json
    
    valid_rows = []
    invalid_rows = []
    
    for row in json.loads(csv_data):
        # Validate against database constraints
        exists = query(
            "SELECT 1 FROM products WHERE sku = $1",
            row['sku']
        )
        
        if exists:
            invalid_rows.append(row)
        else:
            valid_rows.append(row)
            query(
                "INSERT INTO products (sku, name, price) VALUES ($1, $2, $3)",
                row['sku'], row['name'], row['price']
            )
    
    return {
        "imported": len(valid_rows),
        "rejected": len(invalid_rows),
        "invalid": invalid_rows
    }
```

## Administration

### View Installed Functions

```sql
SELECT func_name, created_by, created_at, execution_count
FROM wormhole_functions
ORDER BY execution_count DESC;
```

### Manage Module Whitelist

```sql
-- See what's allowed
SELECT * FROM wormhole_allowed_modules WHERE allowed = true;

-- Allow a new module
INSERT INTO wormhole_allowed_modules (module_name, allowed, notes)
VALUES ('requests', true, 'HTTP client library');

-- Block a module
UPDATE wormhole_allowed_modules 
SET allowed = false 
WHERE module_name = 'os';
```

### Clear Function Cache

```sql
-- Remove a specific function
DELETE FROM wormhole_functions WHERE func_name = 'old_function';

-- Clear all functions by a user
DELETE FROM wormhole_functions WHERE created_by = 'testuser';

-- Clear everything (careful!)
TRUNCATE wormhole_functions;
```

## Limitations

- Functions must be defined in Python files (not REPL/notebooks)
- Only whitelisted Python modules can be imported
- No file I/O or network access from wormhole functions
- Function code must be text-serializable

## Troubleshooting

### "Module 'X' is not allowed"
Add the module to the whitelist:
```sql
INSERT INTO wormhole_allowed_modules (module_name, allowed)
VALUES ('modulename', true);
```

### "No database connection set"
Always call `set_connection()` before using remote functions:
```python
conn = psycopg2.connect("...")
set_connection(conn)
```

### "Cannot get source for function"
Functions must be defined in files, not in interactive shells:
```python
# ✗ Won't work in REPL
>>> @remote
... def my_func():
...     pass

# ✓ Works in a .py file
# myscript.py
@remote
def my_func():
    pass
```

## Next Steps

1. **Run the example**: `python example.py`
2. **Read the full docs**: Check out `README.md`
3. **Try it with your data**: Convert some of your multi-query operations to remote functions
4. **Contribute**: This is an experimental project - ideas and PRs welcome!

## The Vision

Eventually, this could support:
- Automatic query optimization based on data locality
- Intelligent routing to read replicas
- Streaming result sets
- Integration with ORMs (SQLAlchemy, Django)
- Cross-database operations (federated queries)

The core idea is: **move computation to data, not data to computation**.

---

Inspired by Thomas Munro's "Devious Schemes" talk at PGCon 2018.
Built with the belief that databases should be programmable in the languages developers already know.
