"""
Wormhole for PostgreSQL

A Python library for seamlessly executing code in PostgreSQL,
moving computation to the data with the same syntax for client
and server-side query execution.
"""

from .remote import remote
from .query import cursor, query, query_single, query_value, execute
from .transaction import with_transaction, transaction
from .connection import set_connection, get_connection

__version__ = "0.1.0"
__all__ = [
    "remote",
    "cursor",
    "query",
    "query_single", 
    "query_value",
    "execute",
    "with_transaction",
    "transaction",
    "set_connection",
    "get_connection",
]
