-- Wormhole for PostgreSQL
-- Server-side infrastructure for safe Python code execution
--
-- This must be run by a database superuser

-- Ensure plpython3u is available
CREATE EXTENSION IF NOT EXISTS plpython3u;

-- Configuration: which Python modules are allowed
CREATE TABLE IF NOT EXISTS wormhole_allowed_modules (
    module_name text PRIMARY KEY,
    allowed boolean DEFAULT true,
    notes text
);

-- Default safe modules
INSERT INTO wormhole_allowed_modules (module_name, allowed, notes) VALUES
    ('json', true, 'JSON encoding/decoding'),
    ('datetime', true, 'Date and time operations'),
    ('math', true, 'Mathematical functions'),
    ('re', true, 'Regular expressions'),
    ('decimal', true, 'Decimal arithmetic'),
    ('collections', true, 'Container datatypes'),
    ('itertools', true, 'Iterator functions'),
    ('functools', true, 'Higher-order functions'),
    ('operator', true, 'Standard operators as functions'),
    ('string', true, 'String operations'),
    ('hashlib', true, 'Secure hashes'),
    ('uuid', true, 'UUID generation'),
    -- Explicitly blocked dangerous modules
    ('os', false, 'Operating system access - DANGEROUS'),
    ('sys', false, 'System access - DANGEROUS'),
    ('subprocess', false, 'Process spawning - DANGEROUS'),
    ('socket', false, 'Network access - DANGEROUS'),
    ('urllib', false, 'Network access - DANGEROUS'),
    ('requests', false, 'Network access - DANGEROUS'),
    ('http', false, 'Network access - DANGEROUS'),
    ('ftplib', false, 'Network access - DANGEROUS'),
    ('pickle', false, 'Arbitrary code execution - DANGEROUS'),
    ('marshal', false, 'Arbitrary code execution - DANGEROUS'),
    ('__builtin__', false, 'Access to builtins - DANGEROUS'),
    ('builtins', false, 'Access to builtins - DANGEROUS'),
    ('importlib', false, 'Dynamic imports - DANGEROUS'),
    ('ctypes', false, 'C library access - DANGEROUS'),
    ('multiprocessing', false, 'Process spawning - DANGEROUS'),
    ('threading', false, 'Threading - potentially dangerous')
ON CONFLICT (module_name) DO NOTHING;

-- Cache for installed functions
CREATE TABLE IF NOT EXISTS wormhole_functions (
    func_id text PRIMARY KEY,
    func_name text NOT NULL,
    func_code text NOT NULL,
    func_signature jsonb NOT NULL, -- {args: [{name, type}], returns: type}
    source_hash text NOT NULL, -- SHA256 of func_code for cache validation
    created_by name NOT NULL DEFAULT current_user,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_executed timestamptz,
    execution_count bigint DEFAULT 0
);

CREATE INDEX IF NOT EXISTS wormhole_functions_name_idx ON wormhole_functions(func_name);
CREATE INDEX IF NOT EXISTS wormhole_functions_created_by_idx ON wormhole_functions(created_by);

-- Helper function: Check if a module is allowed
CREATE OR REPLACE FUNCTION wormhole_is_module_allowed(module_name text)
RETURNS boolean AS $$
    SELECT COALESCE(
        (SELECT allowed FROM wormhole_allowed_modules WHERE wormhole_allowed_modules.module_name = $1),
        false -- Default to not allowed if not in table
    );
$$ LANGUAGE SQL STABLE;

-- Server-side query function that wormhole functions call
-- This is the only way wormhole functions can access the database
CREATE OR REPLACE FUNCTION wormhole_query(sql text, args jsonb DEFAULT '[]'::jsonb)
RETURNS jsonb AS $$
import json

# Parse arguments
if args:
    arg_list = json.loads(args)
else:
    arg_list = []

# Execute query via SPI
try:
    plan = plpy.prepare(sql, ["text"] * len(arg_list))
    result = plpy.execute(plan, arg_list)
    
    # Convert result to JSON-serializable format
    rows = []
    for row in result:
        rows.append(dict(row))
    
    return json.dumps({
        "rows": rows,
        "status": result.status(),
        "nrows": result.nrows()
    })
except Exception as e:
    plpy.error(f"Query execution failed: {str(e)}")
$$ LANGUAGE plpython3u;

-- Main function: Install/cache a wormhole function
CREATE OR REPLACE FUNCTION wormhole_install(
    func_name text,
    func_code text,
    func_signature jsonb
)
RETURNS text AS $$
import ast
import hashlib
import json
import re

# Generate function ID from hash of code
source_hash = hashlib.sha256(func_code.encode('utf-8')).hexdigest()
func_id = f"{func_name}_{source_hash[:16]}"

# Check if already cached
check_query = plpy.prepare(
    "SELECT func_id FROM wormhole_functions WHERE func_id = $1",
    ["text"]
)
existing = plpy.execute(check_query, [func_id])
if existing:
    return json.dumps({"func_id": func_id, "cached": True})

# Parse the Python code into AST
try:
    tree = ast.parse(func_code)
except SyntaxError as e:
    plpy.error(f"Syntax error in function code: {str(e)}")

# Safety analysis: Find all imports
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            imports.add(alias.name.split('.')[0])
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            imports.add(node.module.split('.')[0])

# Check all imports against whitelist
for module in imports:
    check_module = plpy.prepare(
        "SELECT wormhole_is_module_allowed($1) as allowed",
        ["text"]
    )
    result = plpy.execute(check_module, [module])
    if not result[0]["allowed"]:
        plpy.error(f"Module '{module}' is not allowed in wormhole functions")

# Safety analysis: Check for dangerous operations
dangerous_names = {
    'eval', 'exec', 'compile', '__import__',
    'open', 'file', 'input', 'raw_input',
    'globals', 'locals', 'vars', 'dir',
    'getattr', 'setattr', 'delattr', 'hasattr'
}

for node in ast.walk(tree):
    if isinstance(node, ast.Name) and node.id in dangerous_names:
        plpy.error(f"Dangerous operation '{node.id}' is not allowed in wormhole functions")
    
    # Check for dunder access which could be dangerous
    if isinstance(node, ast.Attribute) and (
        node.attr.startswith('__') and node.attr.endswith('__')
    ):
        if node.attr not in ['__init__', '__str__', '__repr__']:  # Allow some safe dunders
            plpy.error(f"Access to '{node.attr}' is not allowed")

# Verify the function only calls wormhole_query for database access
# (not plpy.execute or other direct database access)
for node in ast.walk(tree):
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == 'plpy':
            plpy.error("Direct use of 'plpy' module is not allowed. Use wormhole_query() instead.")

# Store in cache
insert_query = plpy.prepare(
    """
    INSERT INTO wormhole_functions (func_id, func_name, func_code, func_signature, source_hash)
    VALUES ($1, $2, $3, $4, $5)
    """,
    ["text", "text", "text", "jsonb", "text"]
)
plpy.execute(insert_query, [func_id, func_name, func_code, func_signature, source_hash])

return json.dumps({"func_id": func_id, "cached": False})
$$ LANGUAGE plpython3u SECURITY DEFINER;

-- Main function: Execute a cached wormhole function
CREATE OR REPLACE FUNCTION wormhole_execute(
    func_id text,
    args jsonb DEFAULT '{}'::jsonb
)
RETURNS jsonb AS $$
import json

# Look up the function
lookup_query = plpy.prepare(
    """
    UPDATE wormhole_functions 
    SET last_executed = now(), execution_count = execution_count + 1
    WHERE func_id = $1
    RETURNING func_name, func_code, func_signature
    """,
    ["text"]
)
result = plpy.execute(lookup_query, [func_id])

if not result:
    plpy.error(f"Function '{func_id}' not found in wormhole cache")

func_code = result[0]["func_code"]
func_signature = json.loads(result[0]["func_signature"])

# Parse arguments
call_args = json.loads(args) if args else {}

# Create a restricted execution environment
# Only allow access to wormhole_query
restricted_globals = {
    '__builtins__': {
        'True': True,
        'False': False,
        'None': None,
        'str': str,
        'int': int,
        'float': float,
        'bool': bool,
        'list': list,
        'dict': dict,
        'tuple': tuple,
        'set': set,
        'len': len,
        'range': range,
        'enumerate': enumerate,
        'zip': zip,
        'map': map,
        'filter': filter,
        'sorted': sorted,
        'sum': sum,
        'min': max,
        'max': min,
        'abs': abs,
        'round': round,
        'isinstance': isinstance,
        'type': type,
        'print': plpy.notice,  # Redirect print to plpy.notice
    },
    'json': __import__('json'),
    'wormhole_query': lambda sql, *query_args: json.loads(
        plpy.execute(
            plpy.prepare("SELECT wormhole_query($1, $2) as result", ["text", "jsonb"]),
            [sql, json.dumps(list(query_args))]
        )[0]["result"]
    )
}

# Execute the function code
try:
    exec(func_code, restricted_globals)
    # The function should now be defined in restricted_globals
    func_name = result[0]["func_name"]
    if func_name not in restricted_globals:
        plpy.error(f"Function '{func_name}' not found after execution")
    
    # Call the function with provided arguments
    user_function = restricted_globals[func_name]
    result = user_function(**call_args)
    
    return json.dumps({"result": result, "success": True})
    
except Exception as e:
    plpy.error(f"Function execution failed: {str(e)}")
$$ LANGUAGE plpython3u SECURITY DEFINER;

-- Grant execute permissions to public (users can execute but not modify)
GRANT EXECUTE ON FUNCTION wormhole_install(text, text, jsonb) TO PUBLIC;
GRANT EXECUTE ON FUNCTION wormhole_execute(text, jsonb) TO PUBLIC;
GRANT SELECT ON wormhole_allowed_modules TO PUBLIC;
GRANT SELECT ON wormhole_functions TO PUBLIC;

-- Only superuser can modify the allowed modules list
REVOKE INSERT, UPDATE, DELETE ON wormhole_allowed_modules FROM PUBLIC;
