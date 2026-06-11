"""Quick script to fix database connections in content.py"""

import re

file_path = r"C:\Users\natan\OneDrive\Documents\academic-drugie-podejscie\backend\app\api\content.py"

# Read file
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern to find functions that need fixing
# They start with "conn = db._get_conn()" and end with "db._put_conn(conn)" but lack try-finally

# Split by functions
lines = content.split('\n')

fixed_lines = []
i = 0
while i < len(lines):
    line = lines[i]

    # Check if this is a line with "conn = db._get_conn()"
    if 'conn = db._get_conn()' in line and 'try:' not in lines[i-1] if i > 0 else True:
        # Found a connection that needs try-finally
        indent = len(line) - len(line.lstrip())
        fixed_lines.append(line)
        fixed_lines.append(' ' * indent + 'try:')

        # Copy lines until we find db._put_conn(conn)
        i += 1
        while i < len(lines):
            if 'db._put_conn(conn)' in lines[i]:
                # Found the put_conn - this should be in finally
                # First, backtrack to remove it from where it is
                # and add it in finally block

                # Find where to insert finally (before the put_conn line)
                finally_indent = len(lines[i]) - len(lines[i].lstrip())

                # Don't add the put_conn line yet
                # Add finally block
                fixed_lines.append(' ' * indent + 'finally:')
                fixed_lines.append(' ' * (indent + 4) + 'db._put_conn(conn)')
                i += 1
                break
            else:
                # Indent this line by 4 more spaces (inside try block)
                if lines[i].strip():  # Only indent non-empty lines
                    fixed_lines.append('    ' + lines[i])
                else:
                    fixed_lines.append(lines[i])
                i += 1
    else:
        fixed_lines.append(line)
        i += 1

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(fixed_lines))

print("Fixed content.py database connections")
