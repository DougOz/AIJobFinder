import os
from pymongo import MongoClient
from collections import defaultdict
from mongodb_functions import connect_to_mongodb, DATABASE_NAME

DEFAULT_PROFILE_NAME = 'Doug'

def merge_duplicate_titles():
    """
    Merges duplicate title ratings in the title_ratings collection that are case-insensitive.
    It keeps the rating from the most recently updated document for each title.
    """
    mongo_client, db = connect_to_mongodb()
    if db is None:
        print("Could not connect to MongoDB. Aborting.")
        return

    title_ratings_collection = db.title_ratings
    print(f"Connected to database '{DATABASE_NAME}' and collection '{title_ratings_collection.name}'.")

    # Use an aggregation pipeline to group by lowercase title and find the latest document in each group.
    pipeline = [
        {
            "$match": {"profile_name": DEFAULT_PROFILE_NAME}
        },
        {
            "$sort": {"last_updated": -1} # Sort by date descending to get the latest first
        },
        {
            "$group": {
                "_id": {"$toLower": "$title"}, # Group by lowercase title
                "latest_doc_id": {"$first": "$_id"},
                "latest_rating": {"$first": "$rating"},
                "last_updated": {"$first": "$last_updated"},
                "all_doc_ids": {"$push": "$_id"} # Collect all original _ids in the group
            }
        }
    ]

    try:
        grouped_titles = list(title_ratings_collection.aggregate(pipeline))
        print(f"Found {len(grouped_titles)} unique titles to process.")

        for group in grouped_titles:
            lowercase_title = group['_id']
            ids_to_delete = [doc_id for doc_id in group['all_doc_ids'] if doc_id != group['latest_doc_id']]

            # Update the one document we are keeping to have a lowercase title
            title_ratings_collection.update_one(
                {"_id": group['latest_doc_id']},
                {"$set": {"title": lowercase_title}}
            )
            print(f"  - Kept and standardized '{lowercase_title}' (rating: {group['latest_rating']}).")

            # Delete the other, older/duplicate documents
            if ids_to_delete:
                result = title_ratings_collection.delete_many({"_id": {"$in": ids_to_delete}})
                print(f"    - Deleted {result.deleted_count} duplicate document(s).")

        print("\nMerge complete. All title ratings are now standardized to lowercase.")
    finally:
        if mongo_client:
            mongo_client.close()
            print("MongoDB connection closed.")

if __name__ == '__main__':
    merge_duplicate_titles()
