#!/usr/bin/env python3
"""
Simple smoke test for the wormhole library

Tests basic functionality without requiring a database connection.
"""

import ast
import sys


def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    try:
        from wormhole import remote, query, cursor, set_connection, transaction
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_remote_decorator():
    """Test that the @remote decorator can be applied"""
    print("\nTesting @remote decorator...")
    try:
        from wormhole import remote
        
        @remote
        def test_function(x, y):
            return x + y
        
        # Check that we got a RemoteFunction instance
        from wormhole.remote import RemoteFunction
        assert isinstance(test_function, RemoteFunction)
        assert test_function.func_name == "test_function"
        
        print("✓ @remote decorator works")
        return True
    except Exception as e:
        print(f"✗ @remote decorator failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_function_source_extraction():
    """Test that function source can be extracted"""
    print("\nTesting source extraction...")
    try:
        from wormhole import remote
        
        @remote
        def sample_function(a, b):
            """A sample function"""
            result = a + b
            return result
        
        # Check that source was extracted
        assert sample_function.source is not None
        assert "def sample_function" in sample_function.source
        assert "a + b" in sample_function.source
        
        print("✓ Source extraction works")
        print(f"  Extracted {len(sample_function.source)} characters")
        return True
    except Exception as e:
        print(f"✗ Source extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_signature_extraction():
    """Test that function signatures can be extracted"""
    print("\nTesting signature extraction...")
    try:
        from wormhole import remote
        
        @remote
        def typed_function(x: int, y: str) -> dict:
            return {"x": x, "y": y}
        
        sig = typed_function.signature
        assert "args" in sig
        assert len(sig["args"]) == 2
        assert sig["args"][0]["name"] == "x"
        assert sig["args"][1]["name"] == "y"
        
        print("✓ Signature extraction works")
        print(f"  Signature: {sig}")
        return True
    except Exception as e:
        print(f"✗ Signature extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ast_parsing():
    """Test that we can parse function code into AST"""
    print("\nTesting AST parsing...")
    try:
        from wormhole import remote
        
        @remote
        def ast_test_function(n):
            import json
            data = {"count": n}
            return json.dumps(data)
        
        # Parse the source
        tree = ast.parse(ast_test_function.source)
        
        # Check that we found the import
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
        
        assert "json" in imports
        
        print("✓ AST parsing works")
        print(f"  Found imports: {imports}")
        return True
    except Exception as e:
        print(f"✗ AST parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_connection_management():
    """Test connection stack management"""
    print("\nTesting connection management...")
    try:
        from wormhole.connection import set_connection, get_connection, pop_connection
        
        # Initially no connection
        assert get_connection() is None
        
        # Set a mock connection
        mock_conn = "mock_connection"
        set_connection(mock_conn)
        assert get_connection() == mock_conn
        
        # Pop it
        popped = pop_connection()
        assert popped == mock_conn
        assert get_connection() is None
        
        print("✓ Connection management works")
        return True
    except Exception as e:
        print(f"✗ Connection management failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cursor_creation():
    """Test that WormholeCursor can be created"""
    print("\nTesting cursor creation...")
    try:
        from wormhole.query import WormholeCursor
        
        # Create a mock connection with a cursor method
        class MockCursor:
            def __init__(self):
                self.description = None
                self.rowcount = -1
            
            def execute(self, sql, params=None):
                pass
            
            def fetchall(self):
                return []
            
            def close(self):
                pass
        
        class MockConnection:
            def cursor(self):
                return MockCursor()
        
        mock_conn = MockConnection()
        cur = WormholeCursor(connection=mock_conn)
        assert isinstance(cur, WormholeCursor)
        
        # Test cursor attributes
        assert hasattr(cur, 'execute')
        assert hasattr(cur, 'fetchone')
        assert hasattr(cur, 'fetchall')
        assert hasattr(cur, 'fetchmany')
        assert hasattr(cur, 'description')
        assert hasattr(cur, 'rowcount')
        
        print("✓ Cursor creation works")
        print(f"  Cursor has all DB-API 2.0 methods")
        return True
    except Exception as e:
        print(f"✗ Cursor creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cursor_context_manager():
    """Test that cursor works as context manager"""
    print("\nTesting cursor context manager...")
    try:
        from wormhole.query import WormholeCursor
        
        # Create a mock connection
        class MockCursor:
            def __init__(self):
                self.description = None
                self.rowcount = -1
            
            def execute(self, sql, params=None):
                pass
            
            def fetchall(self):
                return []
            
            def close(self):
                pass
        
        class MockConnection:
            def cursor(self):
                return MockCursor()
        
        mock_conn = MockConnection()
        
        # Test context manager protocol
        cur = WormholeCursor(connection=mock_conn)
        with cur as c:
            assert c is cur
        
        print("✓ Cursor context manager works")
        return True
    except Exception as e:
        print(f"✗ Cursor context manager failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("="*60)
    print("WORMHOLE SMOKE TESTS")
    print("="*60)
    
    tests = [
        test_imports,
        test_remote_decorator,
        test_function_source_extraction,
        test_signature_extraction,
        test_ast_parsing,
        test_connection_management,
        test_cursor_creation,
        test_cursor_context_manager,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "="*60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("="*60)
    
    if all(results):
        print("\n✓ All smoke tests passed!")
        print("\nNext steps:")
        print("1. Install the SQL schema: psql -f schema.sql")
        print("2. Run the basic example: python example.py")
        print("3. Run the DB-API example: python example_dbapi.py")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
