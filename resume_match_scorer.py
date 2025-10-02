# -*- coding: utf-8 -*-
import os
import json
from pymongo import errors
# Use a free, local embedding model via sentence-transformers
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from PyPDF2 import PdfReader

# Import MongoDB functions and constants
from mongodb_functions import connect_to_mongodb, COLLECTION_NAME

# Constants
MAX_CHARS = 16384
DESCRIPTION_SNIPPET_LENGTH = 1000 # Max characters to take from the description for embedding
BOILERPLATE_SKIP_CHARS = 200 # Skips this many characters from the start if description is long
CHECKPOINT_INTERVAL = 10 # Control the logging frequency every X jobs processed

# --- SCORING PARAMETERS ---
MODEL_NAME = 'all-mpnet-base-v2' # More powerful local embedding model

# Fields for the separated scores, used for both Python dict and MongoDB keys
SEMANTIC_SCORE_FIELD = 'semantic_score_v2'
SKILLS_SCORE_FIELD = 'skills_intersection_score'
MATCHED_SKILLS_COUNT_FIELD = 'matched_skills_count'
# ------------------------------


def extract_text_from_pdf(pdf_path):
    """
    Extracts text content from all pages of a PDF file.
    """
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            # Ensure text extraction is not None before concatenating
            extracted = page.extract_text()
            if extracted:
                text += extracted
        return text.strip()
    except Exception as e:
        print(f"Error reading PDF file {pdf_path}: {e}")
        return ""

def _update_job_scores_in_mongo(collection, job):
    """
    Saves the calculated scores for a single job back to the MongoDB document.
    It uses the job's 'url' field to locate and update the document.
    """
    url = job.get('url')
    if not url:
        print("Error: Cannot save score for job without a URL.")
        return

    try:
        # Use $set to update only the score fields
        result = collection.update_one(
            {'url': url},
            {'$set': {
                SEMANTIC_SCORE_FIELD: job.get(SEMANTIC_SCORE_FIELD),
                SKILLS_SCORE_FIELD: job.get(SKILLS_SCORE_FIELD),
                MATCHED_SKILLS_COUNT_FIELD: job.get(MATCHED_SKILLS_COUNT_FIELD),
            }}
        )
        if result.modified_count == 0 and result.matched_count > 0:
            # This happens if the scores were already the same, which is fine
            pass
        elif result.matched_count == 0:
            print(f"Warning: No document found to update for URL: {url}")
            
    except Exception as e:
        print(f"Error saving scores to MongoDB for job {url}: {e}")

def get_job_embedding_input(job):
    """
    Constructs the targeted text input for the semantic embedding model.
    It applies a simple heuristic to skip potential boilerplate at the start of the description.
    """
    job_title = job.get('title', '')
    job_skills = ", ".join(job.get('skills', []))
    job_description = job.get('description', '')
    
    start_index = 0
    # Apply the heuristic: skip the first BOILERPLATE_SKIP_CHARS if the description is long
    if len(job_description) > DESCRIPTION_SNIPPET_LENGTH + BOILERPLATE_SKIP_CHARS:
        start_index = BOILERPLATE_SKIP_CHARS

    # Take the relevant snippet
    job_description_snippet = job_description[start_index : start_index + DESCRIPTION_SNIPPET_LENGTH]

    # Combine high-signal text for embedding
    return f"Job Title: {job_title}. Key Skills: {job_skills}. Context: {job_description_snippet}"


def calculate_semantic_similarity(resume_vector, job_text_for_embedding, embedder, max_chars=MAX_CHARS):
    """
    Calculates the cosine similarity (semantic score) between the resume vector 
    and the targeted job text.
    """
    if not job_text_for_embedding or job_text_for_embedding == 'N/A':
        return 0.0

    # The input text is already targeted and should be within MAX_CHARS, but we truncate defensively
    if len(job_text_for_embedding) > max_chars:
        job_text_for_embedding = job_text_for_embedding[:max_chars]

    # Generate vector for the job description using the 'all-mpnet-base-v2' model
    job_description_vector = embedder.encode(job_text_for_embedding, convert_to_numpy=True)

    # Cosine similarity requires the input to be in a 2D array format
    score = cosine_similarity([resume_vector], [job_description_vector])[0][0]
    return float(score)

def calculate_skills_intersection_score(resume_text, job_skills):
    """
    Calculates the skills ratio score and returns the score and the raw count of matches.
    Score = (Matched Skills) / (Total Unique Job Skills)
    """
    if not job_skills or not resume_text:
        return 0.0, 0 # Return score and count

    # Convert resume text to lowercase for case-insensitive matching
    resume_text_lower = resume_text.lower()
    
    match_count = 0
    # Use a set for unique job skills to avoid double counting
    unique_job_skills = set(job_skills)
    
    for skill in unique_job_skills:
        skill_lower = skill.lower().strip()
        # Simple check: if the skill phrase is found in the resume text
        if skill_lower and skill_lower in resume_text_lower:
            match_count += 1
            
    # Score is the ratio of matched skills to total required unique skills
    score = match_count / len(unique_job_skills)
    
    # Return both the ratio score and the raw count
    return score, match_count

def score_jobs_against_resume(resume_file="DougOsborne_Resume.pdf", checkpoint_interval=CHECKPOINT_INTERVAL):
    """
    Main function to initialize the embedding model, load the resume,
    calculate separate similarity scores for jobs in the data file, and save results to MongoDB.
    """
    # --- Local Embedding Setup ---
    try:
        print(f"Initializing local embedding model ({MODEL_NAME})...")
        embedder = SentenceTransformer(MODEL_NAME)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"FATAL ERROR: Could not load SentenceTransformer model: {e}")
        print("Ensure you have installed the required library: pip install sentence-transformers")
        return # Stop execution if model fails to load

    # 1. Prepare Resume Data and Vector (Calculated only once)
    if not os.path.exists(resume_file):
        print(f"FATAL ERROR: Resume file '{resume_file}' not found.")
        return

    resume_text = extract_text_from_pdf(resume_file)
    if not resume_text:
        print("FATAL ERROR: Could not extract text from resume.")
        return

    if len(resume_text) > MAX_CHARS:
        resume_text = resume_text[:MAX_CHARS]
        print(f"Warning: Resume text truncated to {MAX_CHARS} characters.")

    print("\n--- Generating Resume Vector (One time) ---")
    resume_vector = embedder.encode(resume_text, convert_to_numpy=True)
    print("Resume vector generated. Ready to score jobs.")


    # 2. Connect to MongoDB and Load Jobs Data
    print("\n--- Connecting to MongoDB ---")
    db = connect_to_mongodb()
    if db is None:
        print("FATAL ERROR: Failed to connect to MongoDB. Exiting.")
        return
        
    job_collection = db[COLLECTION_NAME]
    
    print(f"\n--- Loading job data from MongoDB collection: {COLLECTION_NAME} ---")
    try:
        # Fetch all documents as a list. We iterate over this list.
        # We fetch all fields for scoring, but exclude the internal MongoDB '_id' for simplicity.
        jobs_data = list(job_collection.find({}, {'_id': 0})) 
        print(f"Loaded {len(jobs_data)} jobs.")
    except Exception as e:
        print(f"FATAL ERROR: An unexpected error occurred while loading job data from MongoDB: {e}")
        return

    if not jobs_data:
        print("No job data found to process. Exiting.")
        return

    # 3. Process Jobs
    print("\n--- Starting Job Matching and Scoring ---")
    jobs_calculated_in_this_run = 0 # Tracks total jobs scored in the current session
    total_semantic_score = 0.0 # Running sum for semantic score average
    total_skills_score = 0.0 # Running sum for skills score average

    for i, job in enumerate(jobs_data):
        job_index = i + 1
        
        # Get existing scores (for display/recalculation check)
        semantic_score = job.get(SEMANTIC_SCORE_FIELD, 0.0)
        skills_score = job.get(SKILLS_SCORE_FIELD, 0.0)
        
        # Check if scoring is needed (i.e., if new scores are missing or 0.0)
        # We also check for the existence of the score fields to handle cases where they might be explicitly 0.
        semantic_score_exists = SEMANTIC_SCORE_FIELD in job and semantic_score > 0.0
        skills_score_exists = SKILLS_SCORE_FIELD in job and skills_score > 0.0
        raw_count_exists = MATCHED_SKILLS_COUNT_FIELD in job
        
        needs_scoring = not (semantic_score_exists and skills_score_exists and raw_count_exists)
        
        job_title = job.get('title', 'Untitled')


        if needs_scoring:
            # --- CALCULATE SCORES ---
            job_skills = job.get('skills', [])
            job_embedding_input = get_job_embedding_input(job)
            match_count = 0 

            try:
                # 3a. Calculate Semantic Score
                if job_embedding_input.strip() and not semantic_score_exists:
                    semantic_score = calculate_semantic_similarity(resume_vector, job_embedding_input, embedder)
                #else:
                   # semantic_score = 0.0
                
                # 3b. Calculate Skills Intersection Score
                skills_score, match_count = calculate_skills_intersection_score(resume_text, job_skills)

                # Store the new fields in the job dictionary
                job[SEMANTIC_SCORE_FIELD] = round(semantic_score, 4)
                job[SKILLS_SCORE_FIELD] = round(skills_score, 4)
                job[MATCHED_SKILLS_COUNT_FIELD] = match_count
                
                # Immediately update the document in MongoDB
                _update_job_scores_in_mongo(job_collection, job)

                # Update running totals 
                total_semantic_score += semantic_score
                total_skills_score += skills_score
                jobs_calculated_in_this_run += 1
                
            except Exception as e:
                # Log error but continue
                print(f"Job {job_index} ({job_title}): Error during scoring: {e}. Skipping update for this job.")

        
        # --- Logging Output (Controlled by CHECKPOINT_INTERVAL) ---
        if job_index % checkpoint_interval == 0 or job_index == len(jobs_data):
            current_avg_semantic = total_semantic_score / jobs_calculated_in_this_run if jobs_calculated_in_this_run > 0 else 0.0
            current_avg_skills = total_skills_score / jobs_calculated_in_this_run if jobs_calculated_in_this_run > 0 else 0.0
            
            # Note: We display the semantic score field for consistency, even if it's the old 'resume_score' equivalent
            # For simplicity, we can use the job dict accessors
            print(
                f"Job {job_index:<4}/{len(jobs_data)} "
                f"| Title: {job_title:<50.50} "
                f"| Semantic: {job.get(SEMANTIC_SCORE_FIELD):.4f} "
                f"| Skills: {job.get(SKILLS_SCORE_FIELD):.4f} "
                f"| Matched Count: {job.get(MATCHED_SKILLS_COUNT_FIELD, 0):<3} "
                f"| Avg Sem: {current_avg_semantic:.4f} "
                f"| Avg Skill: {current_avg_skills:.4f} "
                f"| Status: {'SCORED' if needs_scoring else 'SKIPPED'}"
            )
        # --- End Logging Output ---
            
    # 5. Final Summary
    print(f"\n--- Summary ---")
    print(f"Total jobs loaded: {len(jobs_data)}")
    print(f"New scores calculated and saved to MongoDB: {jobs_calculated_in_this_run}")

if __name__ == '__main__':
    score_jobs_against_resume()
