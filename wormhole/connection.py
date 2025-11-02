"""
Connection management for wormhole
"""

import threading

_connection_stack = threading.local()


def set_connection(conn):
    """
    Set the PostgreSQL connection for the current thread.
    
    Args:
        conn: A psycopg2 connection object (or compatible)
    """
    if not hasattr(_connection_stack, 'stack'):
        _connection_stack.stack = []
    _connection_stack.stack.append(conn)


def get_connection():
    """
    Get the current PostgreSQL connection for this thread.
    
    Returns:
        The active connection, or None if no connection is set.
    """
    if not hasattr(_connection_stack, 'stack') or not _connection_stack.stack:
        return None
    return _connection_stack.stack[-1]


def pop_connection():
    """
    Remove and return the most recent connection from the stack.
    
    Returns:
        The connection that was popped, or None if stack is empty.
    """
    if not hasattr(_connection_stack, 'stack') or not _connection_stack.stack:
        return None
    return _connection_stack.stack.pop()


class connection_context:
    """
    Context manager for temporarily setting a connection.
    
    Usage:
        with connection_context(conn):
            # Code that uses the connection
            result = some_remote_function()
    """
    
    def __init__(self, conn):
        self.conn = conn
    
    def __enter__(self):
        set_connection(self.conn)
        return self.conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pop_connection()
        return False
