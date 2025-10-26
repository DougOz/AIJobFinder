"""
A command-line utility to interactively rate unrated job titles
from the MongoDB database.

This script:
1. Connects to MongoDB.
2. Finds all job titles in the 'dice_jobs' collection.
3. Filters out titles that already have a rating in 'title_ratings'.
4. Groups the remaining unrated titles, counts their frequency, and sorts them.
5. Presents each title to the user for rating.
6. Saves the new ratings back to the 'title_ratings' collection.
"""

import sys
from pymongo import MongoClient
from mongodb_functions import connect_to_mongodb, DATABASE_NAME

# --- CONFIGURATION ---
DICE_JOBS_COLLECTION = "dice_jobs"
TITLE_RATINGS_COLLECTION = "title_ratings"
# --- END CONFIGURATION ---

def get_unrated_titles(db):
    """
    Finds all job titles in the jobs collection that do not have a rating
    in the title_ratings collection, groups them, counts them, and sorts
    by frequency.
    """
    print("Finding unrated job titles...")

    # 1. Get all titles that are already rated (case-insensitive)
    rated_titles_cursor = db[TITLE_RATINGS_COLLECTION].find({}, {"title": 1})
    rated_titles = {doc['title'].lower() for doc in rated_titles_cursor if 'title' in doc}
    print(f"Found {len(rated_titles)} existing rated titles.")

    # 2. Use an aggregation pipeline to find, group, and count unrated titles
    print("Running aggregation pipeline on 'dice_jobs' collection...")
    pipeline = [
        {
            # Stage 1: Project title to lowercase if it exists and is a string
            "$project": {
                "lower_title": {
                    "$cond": {
                        "if": {"$isNumber": "$title"},
                        "then": None, # Exclude if title is a number
                        "else": {"$toLower": "$title"}
                    }
                }
            }
        },
        {
            # Stage 2: Filter out documents where title is null or empty
            "$match": {
                "lower_title": {"$nin": [None, ""]}
            }
        },
        {
            # Stage 3: Filter out titles that are already in our rated set
            "$match": {
                "lower_title": {"$nin": list(rated_titles)}
            }
        },
        {
            # Stage 4: Group by the lowercase title and count occurrences
            "$group": {
                "_id": "$lower_title",
                "count": {"$sum": 1}
            }
        },
        {
            # Stage 5: Filter for titles that appear more than once
            "$match": {
                "count": {"$gt": 0}
            }
        },
        {
            # Stage 6: Sort by count in descending order
            "$sort": {
                "count": -1
            }
        }
    ]

    unrated_titles_cursor = db[DICE_JOBS_COLLECTION].aggregate(pipeline)
    return list(unrated_titles_cursor)

def main():
    """
    Main function to run the title rating interface.
    """
    client, db = connect_to_mongodb()
    if db is None:
        print("FATAL: Could not connect to MongoDB. Exiting.", file=sys.stderr)
        sys.exit(1)

    try:
        # --- Add limit functionality ---
        default_limit = 5000
        limit = default_limit
        if '--limit' in sys.argv:
            try:
                limit_index = sys.argv.index('--limit') + 1
                limit = int(sys.argv[limit_index])
                print(f"User specified limit: will rate up to {limit} titles.")
            except (ValueError, IndexError):
                print(f"Warning: Invalid or missing value for --limit. Defaulting to {default_limit}.")
                limit = default_limit
        else:
            print(f"No limit specified. Defaulting to top {default_limit} titles.")
        # --- End limit functionality ---

        unrated_titles = get_unrated_titles(db)
        total_to_rate = len(unrated_titles)
        
        # Apply the limit to the list of titles to rate
        titles_to_rate = unrated_titles[:limit]
        total_to_rate = len(titles_to_rate)
        
        if total_to_rate == 0:
            print("\nExcellent! All job titles have been rated.")
            return

        print(f"\nFound {total_to_rate} unique unrated job titles.")
        print(f"\nFound {len(unrated_titles)} unique unrated titles. Starting session for the top {total_to_rate}.")
        print("--- Starting Rating Session ---")
        print("Enter a rating (1-3), 's' to skip, or 'q' to quit.")

        ratings_col = db[TITLE_RATINGS_COLLECTION]

        for i, doc in enumerate(titles_to_rate):
            title = doc['_id']
            count = doc['count']
            
            while True: # Loop for input validation
                prompt = f"\n({i+1}/{total_to_rate}) Rate title: '{title}' (appears {count} times)\n> "
                user_input = input(prompt).lower().strip()

                if user_input == 'q':
                    print("Quitting session. Goodbye!")
                    return
                elif user_input == 's':
                    print("  > Skipped.")
                    break # Go to the next title
                
                try:
                    rating = int(user_input)
                    if 1 <= rating <= 3:
                        # Save to MongoDB
                        ratings_col.update_one(
                            {'title': title}, # Filter by lowercase title
                            {'$set': {'rating': rating}}, # Set the rating
                            upsert=True # Insert if it doesn't exist
                        )
                        print(f"  > Saved rating '{rating}' for '{title}'.")
                        break # Go to the next title
                    else:
                        print("  > Invalid input. Please enter a number between 1 and 3.")
                except ValueError:
                    print("  > Invalid input. Please enter a number, 's', or 'q'.")

        print("\n--- All unrated titles have been processed. ---")

    finally:
        if client:
            client.close()
            print("\nMongoDB connection closed.")


if __name__ == "__main__":
    main()