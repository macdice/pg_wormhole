"""
Query abstraction layer - DB-API 2.0 compatible
Works both client-side and server-side seamlessly
"""

import json
from .connection import get_connection

# This will be set to True when executing inside a wormhole function
_EXECUTION_CONTEXT = {"server_side": False}


def _is_server_side():
    """Check if we're executing inside the database server"""
    return _EXECUTION_CONTEXT["server_side"]


class WormholeCursor:
    """
    DB-API 2.0 compatible cursor that works both client-side and server-side.
    
    This allows existing psycopg2 code to work inside @remote functions with
    minimal changes.
    
    Usage:
        # Client-side (uses psycopg2)
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        results = cursor.fetchall()
        
        # Server-side (in @remote function, uses SPI)
        cursor = cursor()  # Gets a WormholeCursor
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        results = cursor.fetchall()  # Same API!
    """
    
    def __init__(self, connection=None):
        self.connection = connection
        self._real_cursor = None
        self._results = None
        self._rowcount = -1
        self._description = None
        self._current_index = 0
        
        # Initialize based on context
        if not _is_server_side():
            if connection is None:
                connection = get_connection()
            if connection is None:
                raise RuntimeError(
                    "No database connection set. Use set_connection() or "
                    "connection_context() before creating a cursor."
                )
            self._real_cursor = connection.cursor()
    
    def execute(self, sql, parameters=None):
        """
        Execute a SQL statement.
        
        Args:
            sql: SQL statement (use %s for placeholders, or $1, $2, etc.)
            parameters: Tuple or list of parameters
        
        Returns:
            self (for chaining)
        """
        if parameters is None:
            parameters = ()
        
        if _is_server_side():
            # Server-side execution via wormhole_query
            # Convert %s style to $1, $2 style
            converted_sql = sql
            param_list = list(parameters)
            
            # Replace %s with $1, $2, etc.
            param_num = 1
            while '%s' in converted_sql:
                converted_sql = converted_sql.replace('%s', f'${param_num}', 1)
                param_num += 1
            
            # Call wormhole_query (injected by server)
            result = wormhole_query(converted_sql, *param_list)  # noqa: F821
            
            # Store results
            self._results = result["rows"]
            self._rowcount = result.get("nrows", len(self._results))
            self._current_index = 0
            
            # Build description (like psycopg2)
            if self._results:
                first_row = self._results[0]
                self._description = [
                    (key, None, None, None, None, None, None)
                    for key in first_row.keys()
                ]
            else:
                self._description = None
        else:
            # Client-side execution via psycopg2
            # Convert $1, $2 style to %s style if needed
            converted_sql = sql
            param_list = list(parameters)
            
            # Replace $1, $2 with %s
            i = len(param_list)
            while i > 0:
                if f'${i}' in converted_sql:
                    converted_sql = converted_sql.replace(f'${i}', '%s')
                i -= 1
            
            self._real_cursor.execute(converted_sql, parameters)
            
            # Cache results as dict list for consistency with server-side
            if self._real_cursor.description:
                columns = [desc[0] for desc in self._real_cursor.description]
                self._results = [
                    dict(zip(columns, row))
                    for row in self._real_cursor.fetchall()
                ]
                self._description = self._real_cursor.description
            else:
                self._results = []
                self._description = None
            
            self._rowcount = self._real_cursor.rowcount
            self._current_index = 0
        
        return self
    
    def fetchone(self):
        """
        Fetch the next row.
        
        Returns:
            Tuple representing the row, or None if no more rows
        """
        if self._results is None or self._current_index >= len(self._results):
            return None
        
        row_dict = self._results[self._current_index]
        self._current_index += 1
        
        # Convert dict to tuple (DB-API standard)
        return tuple(row_dict.values())
    
    def fetchmany(self, size=None):
        """
        Fetch the next set of rows.
        
        Args:
            size: Number of rows to fetch (default: arraysize)
        
        Returns:
            List of tuples representing rows
        """
        if size is None:
            size = self.arraysize
        
        results = []
        for _ in range(size):
            row = self.fetchone()
            if row is None:
                break
            results.append(row)
        
        return results
    
    def fetchall(self):
        """
        Fetch all remaining rows.
        
        Returns:
            List of tuples representing rows
        """
        if self._results is None:
            return []
        
        results = []
        while self._current_index < len(self._results):
            row_dict = self._results[self._current_index]
            results.append(tuple(row_dict.values()))
            self._current_index += 1
        
        return results
    
    def fetchall_dict(self):
        """
        Fetch all remaining rows as dictionaries (wormhole extension).
        
        Returns:
            List of dictionaries representing rows
        """
        if self._results is None:
            return []
        
        return self._results[self._current_index:]
    
    def fetchone_dict(self):
        """
        Fetch the next row as a dictionary (wormhole extension).
        
        Returns:
            Dictionary representing the row, or None if no more rows
        """
        if self._results is None or self._current_index >= len(self._results):
            return None
        
        row_dict = self._results[self._current_index]
        self._current_index += 1
        return row_dict
    
    @property
    def description(self):
        """Column descriptions (DB-API standard)"""
        return self._description
    
    @property
    def rowcount(self):
        """Number of rows affected/returned (DB-API standard)"""
        return self._rowcount
    
    @property
    def arraysize(self):
        """Default number of rows for fetchmany() (DB-API standard)"""
        return 1
    
    def close(self):
        """Close the cursor"""
        if self._real_cursor:
            self._real_cursor.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def cursor(connection=None):
    """
    Create a DB-API 2.0 compatible cursor.
    
    Works both client-side and server-side.
    
    Usage:
        with cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (42,))
            for row in cur.fetchall():
                print(row)
    
    Args:
        connection: Database connection (optional, uses thread-local if not provided)
    
    Returns:
        WormholeCursor instance
    """
    return WormholeCursor(connection)


# Convenience functions for backwards compatibility and quick queries
def query(sql, *args):
    """
    Execute a SQL query and return all results as dicts.
    
    Args:
        sql: SQL query string (use $1, $2 or %s for parameters)
        *args: Query parameters
    
    Returns:
        List of dictionaries representing rows
    """
    with cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall_dict()


def query_single(sql, *args):
    """
    Execute a query and return the first row as a dictionary.
    
    Args:
        sql: SQL query string
        *args: Query parameters
    
    Returns:
        Dictionary representing the first row, or None if no results
    """
    with cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone_dict()


def query_value(sql, *args):
    """
    Execute a query and return the first column of the first row.
    
    Args:
        sql: SQL query string
        *args: Query parameters
    
    Returns:
        The value from the first column of the first row, or None
    """
    with cursor() as cur:
        cur.execute(sql, args)
        row = cur.fetchone()
        return row[0] if row else None


def execute(sql, *args):
    """
    Execute a SQL statement (INSERT, UPDATE, DELETE, etc.).
    
    Args:
        sql: SQL statement
        *args: Statement parameters
    
    Returns:
        Number of rows affected
    """
    with cursor() as cur:
        cur.execute(sql, args)
        return cur.rowcount
