# Wormhole for PostgreSQL

A Python library for seamlessly executing code inside PostgreSQL, moving computation to the data. Write Python functions that run server-side with the same syntax for queries whether executing client-side or server-side.

Warning: very experimental concept code translated from Scheme by an AI, requiring lots of human work to make into a real thing, not for real use yet!

## Concept

The "wormhole" allows you to write Python code that runs inside PostgreSQL:

```python
@remote
def update_user_stats(user_id):
    # This code runs INSIDE PostgreSQL
    messages = query("SELECT COUNT(*) FROM messages WHERE user_id = $1", user_id)
    query("UPDATE users SET message_count = $1 WHERE id = $2", messages[0]['count'], user_id)
    return query("SELECT username, message_count FROM users WHERE id = $1", user_id)

# Single round-trip to database, runs entirely server-side
result = update_user_stats(42)
```

## Features

- **Code migration**: Functions decorated with `@remote` automatically execute server-side
- **Unified query syntax**: Same `query()` API works client-side and server-side  
- **Security**: Server-side safety analysis prevents dangerous operations
- **Caching**: Functions are compiled once and cached in PostgreSQL
- **Transactions**: Automatic retry on serialization failures and deadlocks
- **Admin control**: DBAs control which Python modules are allowed

## Installation

### 1. Install the SQL schema (as PostgreSQL superuser)

```bash
psql -U postgres -d mydb -f schema.sql
```

This creates:
- `wormhole_install()` - Installs and caches functions
- `wormhole_execute()` - Executes cached functions
- `wormhole_query()` - Query function for server-side code
- `wormhole_allowed_modules` - Module whitelist
- `wormhole_functions` - Function cache

### 2. Install the Python package

```bash
pip install psycopg2  # or psycopg2-binary
cd wormhole-pg
pip install -e .
```

## Usage

### Basic Example

```python
import psycopg2
from wormhole import remote, query, set_connection, transaction

# Connect to database
conn = psycopg2.connect("dbname=mydb user=myuser")
set_connection(conn)

# Define a remote function
@remote
def get_user_summary(user_id):
    user = query("SELECT * FROM users WHERE id = $1", user_id)[0]
    message_count = query("SELECT COUNT(*) FROM messages WHERE user_id = $1", user_id)[0]['count']
    
    return {
        "username": user['username'],
        "message_count": message_count
    }

# Call it - runs entirely in PostgreSQL
with transaction():
    result = get_user_summary(123)
    print(result)
```

### Transaction Management

Automatic retry on serialization failures:

```python
from wormhole import transaction, query

with transaction(max_retries=5):
    # These operations run in a transaction
    # Automatically retried on deadlock or serialization failure
    query("UPDATE accounts SET balance = balance - $1 WHERE id = $2", 100, 1)
    query("UPDATE accounts SET balance = balance + $1 WHERE id = $2", 100, 2)
```

### Complex Example

```python
@remote
def process_order(order_id, user_id):
    # Get order details
    order = query("SELECT * FROM orders WHERE id = $1", order_id)[0]
    
    # Check inventory
    inventory = query(
        "SELECT quantity FROM inventory WHERE product_id = $1",
        order['product_id']
    )[0]
    
    if inventory['quantity'] < order['quantity']:
        raise Exception("Insufficient inventory")
    
    # Update inventory
    query(
        "UPDATE inventory SET quantity = quantity - $1 WHERE product_id = $2",
        order['quantity'],
        order['product_id']
    )
    
    # Record transaction
    query(
        "INSERT INTO transactions (order_id, user_id, amount) VALUES ($1, $2, $3)",
        order_id,
        user_id,
        order['total']
    )
    
    return {"status": "success", "order_id": order_id}

# Single round-trip, all safety checks happen server-side
with transaction():
    result = process_order(456, 789)
```

## Security

### Module Whitelist

Administrators control which Python modules can be used in wormhole functions:

```sql
-- Allow a module
UPDATE wormhole_allowed_modules SET allowed = true WHERE module_name = 'decimal';

-- Block a module  
UPDATE wormhole_allowed_modules SET allowed = false WHERE module_name = 'requests';

-- Add a new module to the whitelist
INSERT INTO wormhole_allowed_modules (module_name, allowed, notes)
VALUES ('pandas', true, 'Data analysis library');
```

### Safety Analysis

The server performs AST analysis on all submitted functions:

- ✅ **Allowed**: Safe operations, whitelisted modules, wormhole_query()
- ❌ **Blocked**: eval(), exec(), file I/O, network access, dangerous imports

Example of blocked code:

```python
@remote
def dangerous_function():
    import os  # ❌ Blocked - 'os' module not allowed
    os.system("rm -rf /")  # Would never execute
```

### Permissions

- Regular users can install and execute wormhole functions
- Users cannot create arbitrary PL/Python functions  
- Only superusers can modify the module whitelist
- All function installations are audited

## Architecture

```
Client Application
       ↓
   @remote function
       ↓
wormhole_install()  ← AST safety analysis
       ↓
wormhole_functions  ← Cached PL/Python function
       ↓
wormhole_execute()  ← Runs with restricted namespace
       ↓
  PostgreSQL SPI    ← Query execution
```

## Comparison to Alternatives

| Approach | Round-trips | Safety | Caching | Language |
|----------|-------------|--------|---------|----------|
| **Wormhole** | 1 | Server-validated | Yes | Python |
| PL/Python | 1 | Manual | No | Python |
| ORM queries | N | N/A | No | Python |
| Stored procs | 1 | Manual | Yes | SQL/PL/pgSQL |

## Limitations

- Functions must be defined in files (not REPL/notebooks)
- Limited to whitelisted Python modules
- No direct access to filesystem or network
- Function source must be serializable as text

## Future Enhancements

- [ ] Automatic query batching and optimization
- [ ] Support for streaming results
- [ ] Read-replica routing for read-only functions

## Inspiration

This project is a port to Python of an earlier experiment using Scheme.  As shown in a 2018 PGCon lightning talk "Devious Schemes: Adventures in distributed computing with PostgreSQL and Scheme."

## License

MIT License - see LICENSE file

## Contributing

Contributions welcome! This is an experimental project exploring new ways to work with databases.
