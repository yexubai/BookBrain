import sqlite3
import os

# Corrected path to the database
db_path = r"d:\code\BookBrain\server\data\bookbrain.db"
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Chunks Table Samples ---")
cursor.execute("SELECT id, book_id, page_number, location_tag FROM chunks WHERE (page_number IS NOT NULL OR location_tag IS NOT NULL) LIMIT 20;")
rows = cursor.fetchall()
if not rows:
    print("NO DATA FOUND with page_number or location_tag!")
else:
    for row in rows:
        print(f"ID: {row[0]}, BookID: {row[1]}, Page: {row[2]}, Tag: {row[3]}")

print("\n--- Chunks Count ---")
cursor.execute("SELECT COUNT(*) FROM chunks")
print(f"Total Chunks: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM chunks WHERE page_number IS NOT NULL")
print(f"Chunks with Page Number: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM chunks WHERE location_tag IS NOT NULL")
print(f"Chunks with Location Tag: {cursor.fetchone()[0]}")

conn.close()
