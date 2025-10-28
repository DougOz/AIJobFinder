import re
from bson.objectid import ObjectId
from mongodb_functions import connect_to_mongodb
from typing import List, Tuple

DEFAULT_PROFILE_NAME = 'Doug'

def normalize_text(text):
    """
    Converts text to lowercase and collapses all whitespace into single spaces.
    This helps in matching text regardless of line breaks or extra spaces.
    """
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip().lower()

def find_robust_span(normalized_description: str, normalized_highlight: str) -> Tuple[int, int] | None:
    """
    Attempts to find a robust match for the highlight text within the description.
    It first tries an exact match. If that fails, it uses the start and end
    phrases of the highlight to find an approximate span.
    """
    # 1. Try for an exact match first.
    start_index = normalized_description.find(normalized_highlight)
    if start_index != -1:
        print("  - Found exact match.")
        end_index = start_index + len(normalized_highlight)
        return start_index, end_index

    # 2. If exact match fails, try a more robust anchor-based search.
    words = normalized_highlight.split(' ')
    if len(words) > 10: # Use first/last 5 words for longer highlights
        start_anchor = ' '.join(words[:5])
        end_anchor = ' '.join(words[-5:])
        
        start_pos = normalized_description.find(start_anchor)
        if start_pos != -1:
            # Search for the end anchor *after* the start anchor is found
            end_pos = normalized_description.find(end_anchor, start_pos + len(start_anchor))
            if end_pos != -1:
                print("  - Found approximate match using start/end anchors.")
                return start_pos, end_pos + len(end_anchor)

    # No match found
    return None



def process_and_segment_descriptions():
    """
    Finds rated jobs, extracts their important highlights, and segments the
    corresponding job description in the 'dice_jobs' collection.
    """
    client, db = connect_to_mongodb()
    if db is None:
        print("Failed to connect to MongoDB. Aborting.")
        return

    try:
        ratings_collection = db.job_ratings
        jobs_collection = db.dice_jobs
        print("Connected to MongoDB collections.")

        # 1. Find all jobs that have been rated and have highlights
        query = {
            "profile_name": DEFAULT_PROFILE_NAME,
            "overall_score": {"$gt": 0},
            "highlights": {"$exists": True, "$ne": []}
        }
        rated_jobs_cursor = ratings_collection.find(query)
        
        processed_count = 0
        for rating_doc in rated_jobs_cursor:
            job_id = rating_doc['job_id']
            print(f"\n--- Processing Job ID: {job_id} ---")

            # 2. Get the full job document
            job_doc = jobs_collection.find_one({"_id": ObjectId(job_id)})
            if not job_doc or 'description' not in job_doc:
                print(f"WARNING: Job document or description not found for {job_id}. Skipping.")
                continue

            full_description = job_doc['description']
            
            # 3. Separate highlights by type
            very_important_highlights = [h['text'] for h in rating_doc.get('highlights', []) if h['type'] == 'very_important']
            important_highlights = [h['text'] for h in rating_doc.get('highlights', []) if h['type'] == 'important']

            # --- GUARANTEE NO DATA LOSS & NORMALIZE NEWLINES ---
            # The text from highlights is always preserved. Newlines within a highlight are replaced with spaces
            # to create a continuous block of text that is more suitable for NLP models.
            processed_vi_highlights = [re.sub(r'\s+', ' ', h).strip() for h in very_important_highlights]
            processed_i_highlights = [re.sub(r'\s+', ' ', h).strip() for h in important_highlights]
            very_important_text_content = "\n\n".join(processed_vi_highlights)
            important_text_content = "\n\n".join(processed_i_highlights)

            # 4. Find spans in the description to *remove* them and create 'other_text'.
            normalized_description = normalize_text(full_description)
            spans_to_remove = []
            
            all_highlights_to_find = very_important_highlights + important_highlights
            for text_block in all_highlights_to_find:
                normalized_block = normalize_text(text_block)
                if not normalized_block: continue
                
                span = find_robust_span(normalized_description, normalized_block)
                if span:
                    spans_to_remove.append(span)
                else:
                    print(f"  - WARNING: Could not find span for highlight block starting with: '{normalized_block[:50]}...'")

            # 5. Reconstruct 'other_text' by removing the found spans.
            other_text = ""
            if not spans_to_remove:
                # If no highlights were found in the description, the whole description is 'other'.
                other_text = full_description
            else:
                # Sort spans to process them in order.
                spans_to_remove.sort()
                last_index = 0
                for start, end in spans_to_remove:
                    if start > last_index:
                        other_text += full_description[last_index:start]
                    last_index = max(last_index, end)
                
                if last_index < len(full_description):
                    other_text += full_description[last_index:]

            # 6. Update the document in dice_jobs
            update_data = {
                "$set": {
                    "very_important_text": very_important_text_content,
                    "important_text": important_text_content,
                    "other_text": other_text.strip()
                }
            }
            jobs_collection.update_one({"_id": ObjectId(job_id)}, update_data)
            print(f"Successfully segmented and updated job {job_id}.")
            processed_count += 1

        print(f"\n--- Processing Complete ---")
        print(f"Total jobs processed and updated: {processed_count}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if client:
            client.close()
            print("MongoDB connection closed.")

if __name__ == '__main__':
    process_and_segment_descriptions()