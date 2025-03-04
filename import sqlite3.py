import sqlite3

# Connect to your database
conn = sqlite3.connect('masterData.sqlite3')
cursor = conn.cursor()

# Get all table names
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

# Print schema for each table
for table in tables:
    table_name = table[0]
    print(f"\nTable: {table_name}")
    cursor.execute(f"PRAGMA table_info('{table_name}');")
    columns = cursor.fetchall()
    for col in columns:
        print(f"- {col[1]} ({col[2]}) {'NOT NULL' if col[3] else ''} {'PRIMARY KEY' if col[5] else ''}")
    # Check foreign keys
    cursor.execute(f"PRAGMA foreign_key_list('{table_name}');")
    fks = cursor.fetchall()
    for fk in fks:
        print(f"  Foreign Key: {fk[3]} -> {fk[2]}.{fk[4]}")

conn.close()