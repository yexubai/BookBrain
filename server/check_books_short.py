import sqlite3
import os

db_path = r"d:\code\BookBrain\server\data\bookbrain.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- All Books In DB ---")
cursor.execute("SELECT id, title, category FROM books;")
for row in cursor.fetchall():
    print(f"ID: {row[0]} | Cat: {row[2]} | Title: {row[1][:40]}")

conn.close()
