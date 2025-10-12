import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from bson.objectid import ObjectId
# Import the custom connection utility
from mongodb_functions import connect_to_mongodb, DATABASE_NAME 

app = Flask(__name__)
CORS(app) # Enable CORS for frontend communication

# --- MongoDB Setup ---
# Connect to the database using the imported function
MONGO_CLIENT, db = connect_to_mongodb()

# Define the collections based on the user's schema
if db is not None:
    # 1. Job Details Collection 
    jobs_collection = db.dice_jobs
    # 2. Ratings Collection (for job-specific feedback)
    ratings_collection = db.job_ratings
    # 3. Skills Proficiency Collection (NEW: for global skill ratings)
    skills_collection = db.skills_proficiency 
    print(f"Using database: {DATABASE_NAME}")
else:
    # If connection fails, set collections to None to handle errors gracefully in API routes
    jobs_collection = None 
    ratings_collection = None
    skills_collection = None
    print("FATAL: Server is running but database collections are not accessible.")


# The profile name used to tie ratings to a specific user.
DEFAULT_PROFILE_NAME = 'Doug' 


# --- FIX: Changed route from '/api/jobs/list' to '/api/jobs' to match the frontend fetch ---
@app.route('/api/jobs', methods=['GET'])
def get_job_list():
    """
    Returns a list of all available job IDs (as a JSON array of strings) 
    from the MongoDB 'dice_jobs' collection.
    """
    if jobs_collection is None:
        return jsonify({"error": "Database 'dice_jobs' collection is unavailable."}), 500
    
    try:
        # Fetch only the _id field from the dice_jobs collection
        job_ids = [str(job['_id']) for job in jobs_collection.find({}, {'_id': 1})]
        
        if not job_ids:
            print(f"MongoDB '{jobs_collection.name}' collection is empty.")
            # Return empty array if no jobs are found
            return jsonify([]) 

        # --- FIX: Return the array of IDs directly, not wrapped in an object ---
        return jsonify(job_ids)
    except Exception as e:
        print(f"Error fetching job list: {e}")
        return jsonify({"error": f"Internal server error when listing jobs: {e}"}), 500


@app.route('/api/job/<job_id>', methods=['GET'])
def get_job_data(job_id):
    """
    Fetches job details from 'dice_jobs', job-specific rating from 'job_ratings', 
    and global skill proficiencies from 'skills_proficiency'.
    """
    if jobs_collection is None or ratings_collection is None or skills_collection is None:
        return jsonify({"error": "One or more database collections are unavailable."}), 500

    try:
        # 1. Fetch Job Details from 'dice_jobs' collection
        job_details = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job_details:
            return jsonify({"error": "Job not found."}), 404

        # Prepare job details
        job_details['_id'] = str(job_details['_id'])
        job_details['job_id'] = job_details.pop('_id') 
        job_id_str = job_details['job_id']

        # 2. Fetch Existing Job-Specific Rating from 'job_ratings' collection
        existing_rating = ratings_collection.find_one({
            "job_id": job_id_str,
            "profile_name": DEFAULT_PROFILE_NAME
        })

        # 3. Fetch Global Skill Proficiencies from 'skills_proficiency'
        job_skills = job_details.get('skills', [])
        skill_proficiencies = []
        for skill_name in job_skills:
            # Query the dedicated skills_proficiency collection for this profile's rating
            proficiency_doc = skills_collection.find_one({
                "profile_name": DEFAULT_PROFILE_NAME,
                "skill_name": skill_name
            })
            
            # Default rating to 0 if the skill has not been rated yet
            user_rating = proficiency_doc.get('user_rating', 0) if proficiency_doc else 0
            
            skill_proficiencies.append({
                "skill_name": skill_name,
                "user_rating": user_rating
            })


        # 4. Compile Response
        response_data = {
            "job_details": job_details,
            "skill_proficiencies": skill_proficiencies,
            "user_overall_score": existing_rating.get('overall_score') if existing_rating else None,
            "user_notes": existing_rating.get('notes') if existing_rating else None,
            "existing_highlights": existing_rating.get('highlights', []) if existing_rating else [],
            "source": f"MongoDB - {DATABASE_NAME}"
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"Error fetching job data for {job_id}: {e}")
        return jsonify({"error": f"Internal server error when fetching job data: {e}"}), 500


@app.route('/api/rate', methods=['POST'])
def save_rating():
    """
    Saves job-specific data to 'job_ratings' and updates global skill proficiencies 
    to 'skills_proficiency'.
    """
    if ratings_collection is None or skills_collection is None:
        return jsonify({"error": "One or more database collections are unavailable."}), 500
    
    try:
        data = request.json
        job_id = data.get('job_id')
        
        if not job_id:
            return jsonify({"error": "Missing job_id."}), 400
        
        timestamp = data.get('timestamp') or f"Submitted at {os.times().system}"

        # --- 1. Save Job-Specific Rating to 'job_ratings' ---
        # Note: 'rated_skills' is REMOVED from this document
        job_rating_data = {
            "job_id": job_id,
            "profile_name": DEFAULT_PROFILE_NAME,
            "overall_score": data.get('overall_score'), 
            "notes": data.get('notes'),
            "highlights": data.get('highlights'),
            "rated_timestamp": timestamp
        }

        # Query uses composite key (job_id, profile_name)
        ratings_collection.update_one(
            {
                "job_id": job_id, 
                "profile_name": DEFAULT_PROFILE_NAME
            },
            {"$set": job_rating_data},
            upsert=True 
        )
        
        # --- 2. Save/Update Global Skill Proficiencies to 'skills_proficiency' ---
        rated_skills = data.get('rated_skills', [])
        
        if rated_skills:
            for skill in rated_skills:
                skill_name = skill.get('skill_name')
                user_rating = skill.get('user_rating')
                
                if skill_name and user_rating is not None:
                    # Query uses composite key (profile_name, skill_name) for global consistency
                    skills_collection.update_one(
                        {
                            "profile_name": DEFAULT_PROFILE_NAME, 
                            "skill_name": skill_name
                        },
                        {"$set": {
                            "user_rating": user_rating,
                            "last_updated": timestamp
                        }},
                        upsert=True
                    )
        
        return jsonify({"message": f"Rating for job {job_id} saved, and {len(rated_skills)} skills updated globally."}), 200

    except Exception as e:
        print(f"Error saving rating: {e}")
        return jsonify({"error": f"Internal server error during rating save: {e}"}), 500


if __name__ == '__main__':
    # Initial setup check and final client closing
    try:
        # Check if the jobs collection exists and is empty
        # Note: count_documents({}) is preferred over estimated_document_count() for accuracy
        if db is not None and jobs_collection is not None and jobs_collection.count_documents({}) == 0:
            print(f"WARNING: The '{jobs_collection.name}' collection in '{DATABASE_NAME}' is empty. Please populate it with job documents.")
        
        port = int(os.environ.get("PORT", 5000))
        app.run(host='0.0.0.0', port=port, debug=True)
    finally:
        # Ensure the client connection is closed when the server shuts down
        if MONGO_CLIENT:
            MONGO_CLIENT.close()
            print("MongoDB client connection closed.")
