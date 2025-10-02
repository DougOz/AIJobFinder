import os
import csv
from collections import Counter 
from mongodb_functions import connect_to_mongodb, COLLECTION_NAME
from file_utilities import get_unique_filename # Import the utility function

# Define the base output filename globally
BASE_OUTPUT_CSV_FILE = "job_skills_analysis_9_column_mongo_agg.csv"

def aggregate_skill_counts(collection, match_filter):
    """
    Uses the MongoDB aggregation pipeline to group and count skills based on a match filter.
    Returns a list of (skill, count) tuples and the total count of documents matched.
    """
    
    # 1. Count the total jobs matching the filter first
    total_jobs = collection.count_documents(match_filter)

    # 2. Define the aggregation pipeline
    pipeline = [
        # Match documents based on the filter (e.g., remote or non-remote)
        {'$match': match_filter},
        # Ensure the document has a non-empty skills list before unwinding
        {'$match': {'skills': {'$exists': True, '$ne': []}}},
        # Deconstruct the skills array field from the input documents to output a document for each element
        {'$unwind': '$skills'},
        # Group all the documents by skill name and count them
        {'$group': {
            '_id': '$skills',
            'count': {'$sum': 1}
        }},
        # Sort by count in descending order
        {'$sort': {'count': -1}}
    ]

    try:
        # Execute the aggregation pipeline
        results = list(collection.aggregate(pipeline))
        
        # Convert results from MongoDB dictionary format to list of (skill, count) tuples
        skill_counts = [
            (doc['_id'], doc['count']) for doc in results
        ]
        
        return skill_counts, total_jobs
        
    except Exception as e:
        print(f"Error during MongoDB aggregation: {e}")
        return [], 0

def analyze_job_skills(collection):
    """
    Loads job data from the MongoDB collection using aggregation, counts skill occurrences, 
    and writes the results to a single 9-column CSV file with a unique filename.

    Args:
        collection (Collection): The MongoDB collection object containing job data.
    """

    # 1. Define match filters for aggregation
    all_filter = {} # Match all documents
    remote_filter = {'job_types': 'Remote'}
    non_remote_filter = {'job_types': {'$ne': 'Remote'}}

    # 2. Run aggregations to get counts and totals directly from MongoDB
    print("Running aggregation for All Jobs...")
    sorted_all_skills, total_all_jobs = aggregate_skill_counts(collection, all_filter)
    
    print("Running aggregation for Remote Jobs...")
    sorted_remote_skills, total_remote_jobs = aggregate_skill_counts(collection, remote_filter)
    
    print("Running aggregation for Non-Remote Jobs...")
    sorted_non_remote_skills, total_non_remote_jobs = aggregate_skill_counts(collection, non_remote_filter)


    if total_all_jobs == 0:
        print("No job data found in MongoDB collection.")
        return

    # Determine the unique output CSV filename using the utility function
    unique_output_filename = get_unique_filename(BASE_OUTPUT_CSV_FILE)

    # Write data to a CSV file
    with open(unique_output_filename, 'w', newline='', encoding='utf-8') as csvfile:
        csv_writer = csv.writer(csvfile)

        # Write the header row for all three sections, now including percentages
        csv_writer.writerow([
            "All Job Skills", "Count", "% All",
            "Remote Job Skills", "Count", "% Remote",
            "Non-Remote Job Skills", "Count", "% Non-Remote"
        ])
        
        # Determine the maximum number of rows to iterate over
        max_rows = max(len(sorted_all_skills), len(sorted_remote_skills), len(sorted_non_remote_skills))
        
        # Helper function to calculate percentage and handle division by zero
        def get_percentage(count, total):
            return f"{(count / total * 100):.1f}%" if total > 0 and isinstance(count, int) else "0.0%"
            
        for i in range(max_rows):
            # Safely get the skill and count for each list, or use empty strings if no more data
            
            # All Jobs Section
            all_skill, all_count, all_percent = "", "", ""
            if i < len(sorted_all_skills):
                all_skill, all_count = sorted_all_skills[i]
                all_percent = get_percentage(all_count, total_all_jobs)

            # Remote Jobs Section
            remote_skill, remote_count, remote_percent = "", "", ""
            if i < len(sorted_remote_skills):
                remote_skill, remote_count = sorted_remote_skills[i]
                remote_percent = get_percentage(remote_count, total_remote_jobs)
                
            # Non-Remote Jobs Section
            non_remote_skill, non_remote_count, non_remote_percent = "", "", ""
            if i < len(sorted_non_remote_skills):
                non_remote_skill, non_remote_count = sorted_non_remote_skills[i]
                non_remote_percent = get_percentage(non_remote_count, total_non_remote_jobs)
                
            # Write the combined row to the CSV
            csv_writer.writerow([
                all_skill, all_count, all_percent,
                remote_skill, remote_count, remote_percent,
                non_remote_skill, non_remote_count, non_remote_percent
            ])

    print(f"Successfully saved skill analysis to '{unique_output_filename}'.")

if __name__ == '__main__':
    # Connect to MongoDB
    client, db = connect_to_mongodb()
    
    if db is None:
        print("Connection failed. Cannot run job skills analysis.")
    else:
        # Get the collection object
        job_collection = db[COLLECTION_NAME]
        
        # Run the analysis using the collection
        analyze_job_skills(job_collection)
