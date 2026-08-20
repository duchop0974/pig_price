import sqlite3

conn = sqlite3.connect("data/gia_heo_hoi.db")

print("PIG_TYPES SCHEMA:")
for row in conn.execute("PRAGMA table_info(pig_types)"):
    print(row)

print("\nPIG_TYPES DATA:")
for row in conn.execute("SELECT * FROM pig_types LIMIT 10"):
    print(row)

conn.close()