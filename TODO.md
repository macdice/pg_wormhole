# TODO - Future Development

## Immediate Priorities (Week 1-2)

### Testing
- [ ] Set up proper test database
- [ ] Write integration tests that actually connect to PostgreSQL
- [ ] Test with real data and complex queries
- [ ] Test transaction retry logic with actual serialization failures
- [ ] Performance benchmarking vs traditional approaches

### Bug Fixes
- [ ] Handle query() calls that return no results properly
- [ ] Better error messages when function installation fails
- [ ] Handle PostgreSQL connection errors gracefully
- [ ] Test with different PostgreSQL versions (12, 13, 14, 15, 16, 17)

### Documentation
- [ ] Add more code examples
- [ ] Document all error conditions
- [ ] Create troubleshooting guide
- [ ] Video/screencast demo

## Short Term (Month 1)

### Core Features
- [ ] Add execution timeout for functions (prevent infinite loops)
- [ ] Add memory limits for function execution
- [ ] Implement query result streaming for large datasets
- [ ] Add support for query_single(), query_value() in server-side code
- [ ] Better handling of Python type hints
- [ ] Support for default parameter values

### Security
- [ ] Add rate limiting for function installation
- [ ] Sanitize error messages to prevent info disclosure
- [ ] Add function size limits (prevent huge function caching)
- [ ] Implement cache eviction policy (LRU)
- [ ] Add configurable GUCs for security settings

### Developer Experience
- [ ] Better error messages with line numbers
- [ ] Pretty-print function source in function cache
- [ ] CLI tool for managing wormhole functions
- [ ] Web UI for function management and monitoring
- [ ] Integration with popular ORMs (SQLAlchemy, Django ORM)

## Medium Term (Month 2-3)

### Performance
- [ ] Query plan caching for repeated queries
- [ ] Batch multiple function calls in one round-trip
- [ ] Connection pooling integration (pgbouncer)
- [ ] Prepared statement support
- [ ] Async/await support for concurrent operations

### Features
- [ ] Read-only transaction routing to replicas
- [ ] Support for generator functions (yield results incrementally)
- [ ] Support for async functions
- [ ] Context managers in remote functions
- [ ] Better exception handling and custom exception types

### Monitoring
- [ ] Execution time metrics per function
- [ ] Cache hit/miss rates
- [ ] Memory usage tracking
- [ ] Query statistics from SPI
- [ ] Integration with pg_stat_statements
- [ ] Prometheus metrics export

### Testing
- [ ] Load testing with concurrent users
- [ ] Chaos testing (network failures, database crashes)
- [ ] Security penetration testing
- [ ] Fuzz testing of AST parser

## Long Term (Month 4+)

### Advanced Features
- [ ] Cross-database queries (postgres_fdw integration)
- [ ] Automatic function migration based on data locality analysis
- [ ] ML-based query optimization
- [ ] JIT compilation for hot functions (via Cython or similar)
- [ ] Support for NumPy/Pandas for data science workloads

### Language Support
- [ ] JavaScript/TypeScript support (via PL/v8)
- [ ] Ruby support (via PL/Ruby)
- [ ] Generic AST-based approach for any language
- [ ] Polyglot functions (mix languages)

### Ecosystem Integration
- [ ] Jupyter notebook magic command (`%%wormhole`)
- [ ] VSCode extension for function development
- [ ] GraphQL integration
- [ ] REST API generator from remote functions
- [ ] Kubernetes operator for deployment

### Research Ideas
- [ ] Automatic partitioning decisions based on function analysis
- [ ] Distributed transaction coordination across shards
- [ ] Query result caching based on function purity analysis
- [ ] Automatic index recommendations from query patterns
- [ ] Cost-based optimizer for deciding client vs server execution

## Known Issues to Fix

### High Priority
- [ ] Function source extraction fails in REPL/notebooks
  - Consider allowing manual source specification
  - Or implement serialization via bytecode
  
- [ ] No way to update/replace existing functions
  - Add version management
  - Add migration path
  
- [ ] Transaction context not properly propagated
  - Nested transactions need savepoint support
  - Better integration with psycopg2 transaction state

### Medium Priority
- [ ] Limited JSON serialization for return values
  - Add support for custom types
  - Better date/time handling
  - Decimal/numeric precision
  
- [ ] No support for OUT parameters or multiple return values
  - Consider tuple unpacking syntax
  - Or named return values
  
- [ ] Module import restrictions too coarse
  - Allow specific functions from modules
  - Example: `from os.path import join` (safe) vs `import os` (unsafe)

### Low Priority
- [ ] Function source code in cache is large
  - Consider compression
  - Consider bytecode storage
  
- [ ] No function dependency tracking
  - If function A calls function B, track relationship
  - Enable cascading invalidation
  
- [ ] No support for class methods or static methods
  - Currently only module-level functions work
  - Could support classes with `@remote` on methods

## Documentation Needs

- [ ] API reference (auto-generated from docstrings)
- [ ] Performance tuning guide
- [ ] Security best practices guide
- [ ] Migration guide from stored procedures
- [ ] Comparison with alternatives (detailed)
- [ ] Case studies from real usage
- [ ] Contributing guide
- [ ] Code of conduct

## Community Building

- [ ] Create GitHub organization
- [ ] Set up CI/CD (GitHub Actions)
- [ ] Create Discord/Slack community
- [ ] Blog post series on design decisions
- [ ] Conference talk submissions (PGCon, PyCon)
- [ ] Academic paper on the approach

## Research Questions

1. **When should code run client-side vs server-side?**
   - Can we automatically decide based on data locality?
   - What about network conditions?
   - What about server load?

2. **How to handle versioning?**
   - What if function changes while cached?
   - Can we detect breaking changes?
   - How to migrate data using old function versions?

3. **What's the security boundary?**
   - Should users be able to see other users' functions?
   - Should functions be tenant-isolated?
   - What about row-level security?

4. **Can this scale to very large functions?**
   - What's the practical limit?
   - Should we split large functions automatically?
   - Can we do incremental compilation?

5. **How to debug server-side execution?**
   - Can we add breakpoints?
   - Can we get stack traces?
   - Can we profile execution?

## Nice to Have

- [ ] Function templates/snippets library
- [ ] AI assistant for converting multi-query code to wormhole functions
- [ ] Automatic test generation for functions
- [ ] Visual query flow diagrams
- [ ] Time-travel debugging (replay function execution)
- [ ] A/B testing framework for query optimization
- [ ] Cost estimation before execution
- [ ] Automatic documentation generation from functions

## Inspiration for Features

Look at these projects for ideas:
- **Dask**: Distributed Python for large datasets
- **Ray**: Distributed Python for ML workloads  
- **Pyodide**: Python in WebAssembly
- **Prefect/Airflow**: Workflow orchestration
- **Beam/Flink**: Stream processing
- **EdgeDB**: Next-gen database with computed properties

## Success Metrics

Track these to measure project success:
- [ ] Installation count
- [ ] GitHub stars
- [ ] Function execution performance vs alternatives
- [ ] Lines of code saved in user applications
- [ ] Community contributions
- [ ] Production deployments
- [ ] Academic citations

---

Remember: The goal is to make databases **programmable** in languages developers already know, while maintaining security and performance.

Start small, iterate fast, and always prioritize:
1. **Security** - Can't compromise
2. **Simplicity** - Easy to understand and use
3. **Performance** - Must be faster than alternatives
4. **Compatibility** - Work with existing tools
