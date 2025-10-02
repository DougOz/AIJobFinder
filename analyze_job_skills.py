import json
from collections import Counter
import csv

def analyze_job_skills(filename):
    """
    Loads job data from a JSON file, counts skill occurrences, and writes
    the results to a single 9-column CSV file, including counts and percentages.

    Args:
        filename (str): The path to the JSON file containing job data.
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            jobs = json.load(f)
    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{filename}'.")
        return

    all_skills_counter = Counter()
    remote_skills_counter = Counter()
    non_remote_skills_counter = Counter()

    # Get the total counts for each job category
    total_all_jobs = len(jobs)
    total_remote_jobs = 0
    total_non_remote_jobs = 0

    for job in jobs:
        if isinstance(job.get('skills'), list):
            # Update the counter for all jobs
            all_skills_counter.update(job['skills'])
        
        job_is_remote = 'Remote' in job.get('job_types', [])
        if job_is_remote:
            total_remote_jobs += 1
            if isinstance(job.get('skills'), list):
                remote_skills_counter.update(job['skills'])
        else:
            total_non_remote_jobs += 1
            if isinstance(job.get('skills'), list):
                non_remote_skills_counter.update(job['skills'])

    sorted_all_skills = all_skills_counter.most_common()
    sorted_remote_skills = remote_skills_counter.most_common()
    sorted_non_remote_skills = non_remote_skills_counter.most_common()
    
    # Define the output CSV filename
    output_csv_filename = "job_skills_analysis_9_column_092925.csv"

    # Write data to a CSV file
    with open(output_csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
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
            return f"{(count / total * 100):.1f}%" if total > 0 else "0.0%"
            
        for i in range(max_rows):
            # Safely get the skill and count for each list, or use empty strings if no more data
            all_skill = sorted_all_skills[i][0] if i < len(sorted_all_skills) else ""
            all_count = sorted_all_skills[i][1] if i < len(sorted_all_skills) else ""
            all_percent = get_percentage(all_count, total_all_jobs) if all_count else ""

            remote_skill = sorted_remote_skills[i][0] if i < len(sorted_remote_skills) else ""
            remote_count = sorted_remote_skills[i][1] if i < len(sorted_remote_skills) else ""
            remote_percent = get_percentage(remote_count, total_remote_jobs) if remote_count else ""
            
            non_remote_skill = sorted_non_remote_skills[i][0] if i < len(sorted_non_remote_skills) else ""
            non_remote_count = sorted_non_remote_skills[i][1] if i < len(sorted_non_remote_skills) else ""
            non_remote_percent = get_percentage(non_remote_count, total_non_remote_jobs) if non_remote_count else ""
            
            # Write the combined row to the CSV
            csv_writer.writerow([
                all_skill, all_count, all_percent,
                remote_skill, remote_count, remote_percent,
                non_remote_skill, non_remote_count, non_remote_percent
            ])

    print(f"Successfully saved skill analysis to '{output_csv_filename}'.")

if __name__ == '__main__':
    output_filename = "dice_job_data.json"
    analyze_job_skills(output_filename)