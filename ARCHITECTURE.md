# Wormhole Architecture & Design

## Core Concept

**Problem**: Applications often make many round-trips to the database, fetching data, processing it, and writing results back. This is slow, especially over networks.

**Solution**: Ship the computation to the data. Write Python functions that execute inside PostgreSQL, accessing data through the same query API they'd use client-side.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│ Client Application (Python)                              │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  @remote                                                  │
│  def my_function(args):                                   │
│      result = query("SELECT ...")  ◄─── Same API         │
│      return result                                        │
│                                                           │
│  my_function(args)  ────────┐                            │
│                              │                            │
└──────────────────────────────┼────────────────────────────┘
                               │ 1. Serialize function
                               │ 2. wormhole_install()
                               ▼
┌─────────────────────────────────────────────────────────┐
│ PostgreSQL Server                                        │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────────────────────────────────┐            │
│  │ wormhole_install()                       │            │
│  │   • Parse AST                            │            │
│  │   • Check imports against whitelist      │            │
│  │   • Validate no dangerous operations     │            │
│  │   • Cache if safe                        │            │
│  └──────────────────────────────────────────┘            │
│                      │                                    │
│                      ▼                                    │
│  ┌──────────────────────────────────────────┐            │
│  │ wormhole_functions (cache)               │            │
│  │   func_id, func_name, func_code, ...     │            │
│  └──────────────────────────────────────────┘            │
│                      │                                    │
│                      ▼                                    │
│  ┌──────────────────────────────────────────┐            │
│  │ wormhole_execute(func_id, args)          │            │
│  │   • Look up cached function              │            │
│  │   • Create restricted namespace          │            │
│  │   • Inject wormhole_query()              │            │
│  │   • Execute function                     │            │
│  └──────────────────────────────────────────┘            │
│                      │                                    │
│                      ▼                                    │
│  ┌──────────────────────────────────────────┐            │
│  │ wormhole_query(sql, args)                │            │
│  │   • Execute via SPI           ◄─── Same API          │
│  │   • Return results as JSON                │            │
│  └──────────────────────────────────────────┘            │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Client Library (`wormhole/` package)

#### remote.py - The @remote Decorator
- **Purpose**: Mark functions for server-side execution
- **Process**:
  1. Extract function source code using `inspect.getsource()`
  2. Remove decorator lines
  3. Extract function signature with type hints
  4. Create a `RemoteFunction` wrapper
- **Key Methods**:
  - `_install_on_server()`: Calls PostgreSQL to install the function
  - `__call__()`: Intercepts function calls and routes to server

#### query.py - Query Abstraction
- **Purpose**: Unified query API for client and server
- **Client Mode**: Uses psycopg2 to execute queries
- **Server Mode**: Would call `wormhole_query()` (injected by server)
- **Features**:
  - Converts `$1, $2` placeholders to `%s` for psycopg2
  - Returns consistent dict-based results
  - Helper methods: `query_single()`, `query_value()`

#### connection.py - Connection Management
- **Purpose**: Thread-safe connection stack
- **Pattern**: Thread-local storage
- **Usage**: 
  ```python
  set_connection(conn)
  # ... do work ...
  pop_connection()
  ```

#### transaction.py - Transaction Management
- **Purpose**: Automatic retry on transient errors
- **Retryable Errors**:
  - Serialization failures
  - Deadlocks
  - Read-only standby errors
- **Features**:
  - Exponential backoff
  - Configurable retry count
  - Context manager API

### 2. Server Infrastructure (`schema.sql`)

#### wormhole_allowed_modules
```sql
CREATE TABLE wormhole_allowed_modules (
    module_name text PRIMARY KEY,
    allowed boolean DEFAULT true,
    notes text
);
```
- **Purpose**: Security whitelist for Python modules
- **Management**: Controlled by DBAs (superuser only)
- **Default Policy**: Deny by default, explicit allow

#### wormhole_functions
```sql
CREATE TABLE wormhole_functions (
    func_id text PRIMARY KEY,
    func_name text NOT NULL,
    func_code text NOT NULL,
    func_signature jsonb NOT NULL,
    source_hash text NOT NULL,
    created_by name NOT NULL,
    created_at timestamptz NOT NULL,
    last_executed timestamptz,
    execution_count bigint DEFAULT 0
);
```
- **Purpose**: Cache compiled functions
- **Cache Key**: `func_id` = name + hash of source code
- **Audit**: Tracks who created functions and usage stats

#### wormhole_install(func_name, func_code, func_signature)
```sql
CREATE FUNCTION wormhole_install(...) RETURNS text
```
- **Purpose**: Validate and cache Python functions
- **Security Checks**:
  1. Parse Python source into AST
  2. Extract all imports (Import, ImportFrom nodes)
  3. Check each import against `wormhole_allowed_modules`
  4. Scan for dangerous operations:
     - eval, exec, compile, __import__
     - open, file, input
     - globals, locals, getattr, setattr
     - Dunder attribute access (except safe ones)
     - Direct plpy module usage
  5. Generate cache key from source hash
  6. Store in `wormhole_functions` if safe
- **Returns**: JSON with `func_id` and `cached` status

#### wormhole_execute(func_id, args)
```sql
CREATE FUNCTION wormhole_execute(...) RETURNS jsonb
```
- **Purpose**: Execute a cached function in a sandbox
- **Process**:
  1. Look up function in cache
  2. Parse arguments from JSON
  3. Create restricted execution namespace:
     - Limited `__builtins__` (no dangerous functions)
     - Allowed modules (json, datetime, math, etc.)
     - `wormhole_query()` function injected
     - `print` redirected to `plpy.notice()`
  4. Execute function code with `exec()`
  5. Call the function with provided arguments
  6. Return result as JSON
- **Security**: Uses `SECURITY DEFINER` but with restricted namespace

#### wormhole_query(sql, args)
```sql
CREATE FUNCTION wormhole_query(...) RETURNS jsonb
```
- **Purpose**: Query execution API for sandboxed functions
- **Uses**: PostgreSQL SPI (Server Programming Interface)
- **Returns**: JSON with rows, status, count

## Security Model

### Defense in Depth

1. **Client-Side** (Convenience):
   - Source extraction and serialization
   - No security enforcement (can be bypassed)

2. **Server-Side** (Trust Boundary):
   - AST parsing and validation
   - Module whitelist enforcement
   - Dangerous operation detection
   - Namespace restriction
   - Audit logging

3. **Execution Sandbox**:
   - Limited `__builtins__` 
   - No file system access
   - No network access
   - No process spawning
   - No import machinery access

### Attack Surface Analysis

#### What's Protected:
- ✅ Arbitrary code execution (AST validation)
- ✅ Module imports (whitelist)
- ✅ File system access (no file operations)
- ✅ Network access (no socket/urllib)
- ✅ SQL injection (parameterized queries only)
- ✅ Privilege escalation (no plpy access)

#### Potential Vulnerabilities:
- ⚠️ **Denial of Service**: 
  - Infinite loops (no timeout yet)
  - Memory exhaustion (no limits yet)
  - **Mitigation**: Add execution timeout, memory limits
  
- ⚠️ **Information Disclosure**:
  - Error messages might leak schema info
  - **Mitigation**: Sanitize error messages
  
- ⚠️ **Resource Exhaustion**:
  - Large cache of functions
  - **Mitigation**: Add cache size limits, LRU eviction

### Trust Model

```
┌────────────────────────┐
│ Database Superuser     │  Full trust
│ - Creates extension    │  - Can modify whitelist
│ - Manages whitelist    │  - Can create PL/Python
└────────────────────────┘

┌────────────────────────┐
│ Regular Database User  │  Limited trust  
│ - Installs functions   │  - Cannot modify whitelist
│ - Executes functions   │  - Cannot bypass sandbox
│ - Views function list  │  - Audited usage
└────────────────────────┘

┌────────────────────────┐
│ Wormhole Functions     │  Zero trust
│ - Run in sandbox       │  - No dangerous operations
│ - Access via SPI only  │  - Whitelisted modules only
│ - Restricted namespace │  - No privilege escalation
└────────────────────────┘
```

## Performance Characteristics

### Latency Analysis

**Traditional approach** (N queries):
```
Total latency = N × (network_latency + query_time)
Example: 5 queries × (10ms + 2ms) = 60ms
```

**Wormhole approach** (1 remote call):
```
Total latency = network_latency + (N × query_time) + overhead
Example: 10ms + (5 × 2ms) + 5ms = 25ms
Improvement: 2.4× faster
```

### Overhead Breakdown

1. **First Call** (cache miss):
   - Source serialization: ~1ms
   - Network transfer: ~10ms
   - AST parsing: ~5ms
   - Security validation: ~10ms
   - Function storage: ~5ms
   - Execution: N × query_time
   - **Total overhead**: ~31ms + queries

2. **Subsequent Calls** (cache hit):
   - Network transfer: ~10ms
   - Cache lookup: ~1ms
   - Execution: N × query_time
   - **Total overhead**: ~11ms + queries

### Optimization Opportunities

1. **Connection Pooling**: Reuse connections (pgbouncer)
2. **Prepared Statements**: Cache query plans in SPI
3. **Bulk Operations**: Batch multiple function calls
4. **Streaming**: Stream large result sets
5. **Compression**: Compress function source and results

## Comparison to Alternatives

### vs. Stored Procedures (PL/pgSQL)
| Feature | Wormhole | PL/pgSQL |
|---------|----------|----------|
| Language | Python | SQL/PL/pgSQL |
| Development | Client-side | Server-side |
| Deployment | Automatic | Manual |
| Safety | Validated | Manual review |
| Caching | Automatic | Manual |
| **Use Case** | **Rapid development** | **Performance critical** |

### vs. ORM Query Methods
| Feature | Wormhole | ORM |
|---------|----------|-----|
| Round-trips | 1 | N |
| Type safety | Runtime | Compile-time |
| Expressiveness | Python | DSL |
| Learning curve | Low | Medium |
| **Use Case** | **Complex workflows** | **Simple CRUD** |

### vs. Regular PL/Python
| Feature | Wormhole | PL/Python |
|---------|----------|-----------|
| Privileges | User | Superuser |
| Safety | Validated | Manual |
| Development | Client | Server |
| Deployment | Automatic | Manual |
| **Use Case** | **User functions** | **Extensions** |

## Design Decisions

### Why Python?
- ✅ Popular, widely known
- ✅ Rich standard library
- ✅ Good introspection (inspect, ast modules)
- ✅ PL/Python already exists
- ✅ Easy to sandbox
- ❌ Slower than compiled languages
- ❌ Not as "pure" as Scheme for code-as-data

### Why AST over Bytecode?
- ✅ Human-readable for audit
- ✅ Platform-independent
- ✅ Allows static analysis
- ❌ Slower to parse
- ❌ Larger to transfer

### Why JSON for Serialization?
- ✅ Universal format
- ✅ PostgreSQL native support
- ✅ Human-readable
- ✅ Safe (no code execution)
- ❌ Limited type support
- ❌ No circular references

### Why Function Caching?
- ✅ Avoid repeated validation
- ✅ Avoid repeated compilation
- ✅ Enable performance optimization
- ❌ Cache invalidation complexity
- ❌ Memory usage

## Future Enhancements

### Short Term
1. **Better Error Handling**: Sanitize error messages
2. **Execution Timeouts**: Prevent runaway functions
3. **Memory Limits**: Prevent memory exhaustion
4. **Streaming Results**: Handle large result sets
5. **Better Type Hints**: Leverage Python typing

### Medium Term
1. **Query Optimization**: Analyze and optimize query patterns
2. **Read Replica Routing**: Direct read-only functions to replicas
3. **Connection Pooling**: Integration with pgbouncer
4. **Monitoring**: Metrics for function execution
5. **Version Control**: Track function versions

### Long Term
1. **Cross-Database**: Federated queries across databases
2. **Automatic Migration**: Analyze functions to determine best execution location
3. **JIT Compilation**: Compile hot functions to C
4. **ML Integration**: Use ML to predict optimal execution strategy
5. **Language Support**: Extend to JavaScript, Ruby, etc.

## Known Limitations

1. **Function Source Required**: Can't serialize REPL functions
2. **Module Restrictions**: Only whitelisted modules
3. **No Globals**: Functions can't access module-level state
4. **Serialization Limits**: Some Python objects can't be JSON serialized
5. **Single Return Value**: Functions return one value (but can be dict/list)

## Testing Strategy

### Unit Tests
- Remote decorator application
- Source extraction
- Signature parsing
- AST analysis
- Connection management

### Integration Tests (require database)
- Function installation
- Function execution
- Query execution (client and server)
- Transaction retry logic
- Error handling

### Security Tests
- Blocked module imports
- Dangerous operation detection
- Namespace isolation
- Privilege escalation attempts

### Performance Tests
- Overhead measurement
- Cache hit/miss rates
- Scalability testing
- Memory profiling

## Conclusion

Wormhole for PostgreSQL demonstrates that:

1. **Computation can move to data** seamlessly
2. **Security can be enforced** without sacrificing usability
3. **Performance improves** through reduced round-trips
4. **Development is faster** with familiar languages

The core insight: databases don't have to be just storage. They can be **compute platforms** that run your code where your data lives.

Next step: **Try it with real workloads and iterate!**
