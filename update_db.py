import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE products ADD COLUMN image TEXT")
    print("Image column added")
except:
    print("Image column already exists")

conn.commit()
conn.close()
