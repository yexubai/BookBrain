import sqlite3
import os

db_path = r"d:\code\BookBrain\server\data\bookbrain.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Recent Books ---")
cursor.execute("SELECT id, title, file_path, category FROM books ORDER BY id DESC LIMIT 50;")
for row in cursor.fetchall():
    print(f"ID: {row[0]}, Title: {row[1]}, Path: {row[2]}, Category: {row[3]}")

print("\n--- Summary Count ---")
cursor.execute("SELECT COUNT(*) FROM books")
print(f"Total Books in DB: {cursor.fetchone()[0]}")

conn.close()
