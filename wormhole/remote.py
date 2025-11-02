"""
The @remote decorator - marks functions for server-side execution
"""

import ast
import hashlib
import inspect
import json
import textwrap
from functools import wraps
from .connection import get_connection
from .query import query as _query_impl


class RemoteFunction:
    """
    Wrapper for a function that can be executed server-side.
    """
    
    def __init__(self, func):
        self.func = func
        self.func_name = func.__name__
        self.func_id = None  # Will be set after installation
        self._installed = False
        
        # Extract function source and metadata
        self.source = self._get_function_source()
        self.signature = self._extract_signature()
    
    def _get_function_source(self):
        """
        Extract the source code of the function.
        """
        try:
            source = inspect.getsource(self.func)
            # Remove the @remote decorator line(s)
            lines = source.split('\n')
            filtered_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped.startswith('@remote'):
                    filtered_lines.append(line)
            
            source = '\n'.join(filtered_lines)
            # Dedent to get clean source
            source = textwrap.dedent(source)
            return source
        except (OSError, TypeError):
            # If we can't get source (e.g., in REPL), we'll need the user to provide it
            raise RuntimeError(
                f"Cannot get source for function '{self.func_name}'. "
                "Remote functions must be defined in a file, not in REPL."
            )
    
    def _extract_signature(self):
        """
        Extract the function signature for validation.
        """
        sig = inspect.signature(self.func)
        
        args = []
        for param_name, param in sig.parameters.items():
            arg_info = {"name": param_name}
            
            # Try to get type annotation
            if param.annotation != inspect.Parameter.empty:
                arg_info["type"] = str(param.annotation)
            
            # Check for default value
            if param.default != inspect.Parameter.empty:
                arg_info["default"] = repr(param.default)
            
            args.append(arg_info)
        
        signature = {"args": args}
        
        # Get return type annotation if present
        if sig.return_annotation != inspect.Signature.empty:
            signature["returns"] = str(sig.return_annotation)
        
        return signature
    
    def _rewrite_query_calls(self):
        """
        Rewrite query() calls to wormhole_query() calls.
        
        This transforms the function to use the server-side query API.
        """
        tree = ast.parse(self.source)
        
        class QueryRewriter(ast.NodeTransformer):
            def visit_Call(self, node):
                # Recursively visit child nodes first
                self.generic_visit(node)
                
                # Check if this is a call to query()
                if isinstance(node.func, ast.Name) and node.func.id == 'query':
                    # Keep the call as-is; wormhole_query will be in the namespace
                    pass
                elif isinstance(node.func, ast.Name) and node.func.id == 'query_single':
                    # Transform query_single to use query and get first result
                    # This is a simplified approach
                    pass
                
                return node
        
        rewriter = QueryRewriter()
        new_tree = rewriter.visit(tree)
        
        # Convert back to source
        return ast.unparse(new_tree)
    
    def _install_on_server(self):
        """
        Install this function on the server by calling wormhole_install.
        """
        if self._installed:
            return
        
        conn = get_connection()
        if conn is None:
            raise RuntimeError(
                "No database connection. Use set_connection() before calling remote functions."
            )
        
        # Prepare the function code for server-side execution
        # Add imports that the function needs
        server_code = self.source
        
        # The server needs to import any modules used
        # For now, we'll include them at the top of the function
        # (The server-side safety check will validate these)
        
        with conn.cursor() as cur:
            cur.execute(
                "SELECT wormhole_install(%s, %s, %s)",
                (self.func_name, server_code, json.dumps(self.signature))
            )
            result = json.loads(cur.fetchone()[0])
            self.func_id = result["func_id"]
            self._installed = True
            
            if result.get("cached"):
                # Function was already in cache
                pass
    
    def __call__(self, *args, **kwargs):
        """
        Execute the function server-side.
        """
        # Install on first call
        if not self._installed:
            self._install_on_server()
        
        conn = get_connection()
        if conn is None:
            raise RuntimeError(
                "No database connection. Use set_connection() before calling remote functions."
            )
        
        # Convert positional args to kwargs based on signature
        sig = inspect.signature(self.func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        call_kwargs = dict(bound_args.arguments)
        
        # Execute on server
        with conn.cursor() as cur:
            cur.execute(
                "SELECT wormhole_execute(%s, %s)",
                (self.func_id, json.dumps(call_kwargs))
            )
            result = json.loads(cur.fetchone()[0])
            
            if not result.get("success"):
                raise RuntimeError(f"Server-side execution failed: {result}")
            
            return result.get("result")
    
    def __repr__(self):
        return f"<RemoteFunction {self.func_name}>"


def remote(func):
    """
    Decorator to mark a function for server-side execution.
    
    Usage:
        @remote
        def my_function(arg1, arg2):
            result = query("SELECT * FROM table WHERE id = $1", arg1)
            return result
    
    The decorated function will be automatically installed on the PostgreSQL
    server and executed there when called.
    """
    return RemoteFunction(func)
