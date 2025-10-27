from mongodb_functions import connect_to_mongodb

DEFAULT_PROFILE_NAME = 'Doug'

def fix_title_ratings():
    """
    One-time script to add 'profile_name: "Doug"' to all documents
    in the 'title_ratings' collection where the field is missing.
    """
    client, db = connect_to_mongodb()
    if db is None:
        print("Failed to connect to MongoDB. Aborting.")
        return

    try:
        title_ratings_collection = db.title_ratings
        print("Connected to 'title_ratings' collection.")

        # Filter for documents where 'profile_name' does not exist
        filter_query = {"profile_name": {"$exists": False}}

        # The update to apply: set profile_name to the default
        update_operation = {"$set": {"profile_name": DEFAULT_PROFILE_NAME}}

        print(f"Finding documents with missing 'profile_name' and setting it to '{DEFAULT_PROFILE_NAME}'...")

        # Perform the bulk update
        result = title_ratings_collection.update_many(filter_query, update_operation)

        print("\n--- Update Complete ---")
        print(f"Documents matched (missing 'profile_name'): {result.matched_count}")
        print(f"Documents modified: {result.modified_count}")
        print("-----------------------\n")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if client:
            client.close()
            print("MongoDB connection closed.")

if __name__ == '__main__':
    fix_title_ratings()