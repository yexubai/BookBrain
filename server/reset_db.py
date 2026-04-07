"""Utility script to reset the BookBrain database and vector store."""

import os
from pathlib import Path
import shutil

# Root directory of the BookBrain project
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

def reset():
    print("--- BookBrain Database Reset Tool ---")
    print(f"Target Directory: {DATA_DIR}")
    
    # Files to delete
    targets = [
        DATA_DIR / "bookbrain.db",
        DATA_DIR / "bookbrain.db-shm",
        DATA_DIR / "bookbrain.db-wal",
        DATA_DIR / "faiss_index.bin",
        DATA_DIR / "faiss_ids.json",
    ]
    
    # Directories to clear (optional, maybe keep covers?)
    # shutil.rmtree(DATA_DIR / "covers", ignore_errors=True)
    # os.makedirs(DATA_DIR / "covers", exist_ok=True)

    any_deleted = False
    for target in targets:
        if target.exists():
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                print(f"Deleted: {target.name}")
                any_deleted = True
            except Exception as e:
                print(f"Error deleting {target.name}: {e}")

    if not any_deleted:
        print("No existing database files found.")
    else:
        print("\nDatabase reset successfully.")
    
    print("\nYou can now restart the BookBrain server and start a fresh ingest.")

if __name__ == "__main__":
    confirm = input("Are you sure you want to delete all database records? (y/N): ")
    if confirm.lower() == 'y':
        reset()
    else:
        print("Reset cancelled.")
