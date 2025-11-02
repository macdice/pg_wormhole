"""
Transaction management with automatic retry logic
"""

import time
from contextlib import contextmanager
from .connection import get_connection, connection_context


class TransactionRetryError(Exception):
    """Raised when a transaction fails after all retries"""
    pass


class SerializationFailure(Exception):
    """Raised when a serialization failure occurs"""
    pass


def _is_retryable_error(exc):
    """
    Check if a database error is retryable.
    
    Returns True for:
    - Serialization failures
    - Deadlocks
    - Read-only standby errors
    """
    error_msg = str(exc).lower()
    retryable_conditions = [
        'serialization failure',
        'deadlock detected',
        'cannot execute',
        'read-only transaction',
        'could not serialize'
    ]
    return any(cond in error_msg for cond in retryable_conditions)


@contextmanager
def transaction(max_retries=3, retry_delay=0.1):
    """
    Context manager for transactions with automatic retry on retryable errors.
    
    Usage:
        with transaction():
            query("INSERT INTO table VALUES ($1, $2)", val1, val2)
            result = some_remote_function()
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Base delay between retries in seconds (default: 0.1)
    
    Raises:
        TransactionRetryError: If transaction fails after all retries
    """
    conn = get_connection()
    if conn is None:
        raise RuntimeError(
            "No database connection set. Use set_connection() or "
            "connection_context() before using transaction()."
        )
    
    attempt = 0
    last_error = None
    
    while attempt <= max_retries:
        try:
            # Start transaction
            conn.rollback()  # Ensure clean state
            
            yield
            
            # Commit if we get here
            conn.commit()
            return
            
        except Exception as e:
            # Rollback on any error
            conn.rollback()
            
            # Check if this is a retryable error
            if _is_retryable_error(e):
                last_error = e
                attempt += 1
                
                if attempt <= max_retries:
                    # Wait before retry with exponential backoff
                    delay = retry_delay * (2 ** (attempt - 1))
                    time.sleep(delay)
                    continue
                else:
                    # Out of retries
                    raise TransactionRetryError(
                        f"Transaction failed after {max_retries} retries: {str(e)}"
                    ) from e
            else:
                # Non-retryable error, raise immediately
                raise


def with_transaction(func, max_retries=3):
    """
    Decorator to wrap a function in a transaction with automatic retry.
    
    Usage:
        @with_transaction
        def my_database_operation():
            query("UPDATE table SET value = value + 1")
            return query_value("SELECT SUM(value) FROM table")
        
        result = my_database_operation()
    
    Args:
        func: Function to wrap
        max_retries: Maximum number of retry attempts
    
    Returns:
        Wrapped function
    """
    def wrapper(*args, **kwargs):
        with transaction(max_retries=max_retries):
            return func(*args, **kwargs)
    
    return wrapper


@contextmanager  
def read_only_transaction():
    """
    Context manager for read-only transactions.
    
    This sets the transaction to read-only mode, which can enable
    optimizations and allow queries against read replicas.
    
    Usage:
        with read_only_transaction():
            result = query("SELECT * FROM large_table")
    """
    conn = get_connection()
    if conn is None:
        raise RuntimeError("No database connection set.")
    
    try:
        # Start read-only transaction
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
        
        yield
        
        # Commit read-only transaction
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise


@contextmanager
def savepoint(name="sp"):
    """
    Context manager for savepoints within a transaction.
    
    Usage:
        with transaction():
            query("INSERT INTO table VALUES (1)")
            
            try:
                with savepoint("sp1"):
                    query("INSERT INTO table VALUES (2)")
                    raise Exception("Something went wrong")
            except:
                pass  # Rolled back to savepoint
            
            # First insert is still there
            conn.commit()
    
    Args:
        name: Name for the savepoint (default: "sp")
    """
    conn = get_connection()
    if conn is None:
        raise RuntimeError("No database connection set.")
    
    try:
        # Create savepoint
        with conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {name}")
        
        yield
        
        # Release savepoint on success
        with conn.cursor() as cur:
            cur.execute(f"RELEASE SAVEPOINT {name}")
            
    except Exception as e:
        # Rollback to savepoint on error
        with conn.cursor() as cur:
            cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
        raise
