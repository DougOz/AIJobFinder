import os
import json
import random
import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from bson.objectid import ObjectId
# --- NEW: Import libraries for web scraping ---
import requests
from bs4 import BeautifulSoup

# Import the custom connection utility
from mongodb_functions import connect_to_mongodb, DATABASE_NAME

app = Flask(__name__)
CORS(app) # Enable CORS for frontend communication

# --- MongoDB Setup ---
MONGO_CLIENT, db = connect_to_mongodb()

if db is not None:
    jobs_collection = db.dice_jobs
    ratings_collection = db.job_ratings
    skills_collection = db.skills_proficiency
    title_ratings_collection = db.title_ratings
    print(f"Using database: {DATABASE_NAME}")
else:
    jobs_collection = None
    ratings_collection = None
    skills_collection = None
    title_ratings_collection = None
    print("FATAL: Server is running but database collections are not accessible.")


DEFAULT_PROFILE_NAME = 'Doug'


@app.route('/api/jobs', methods=['GET'])
def get_job_list():
    """
    Returns a list of all available job IDs (as a JSON array of strings).
    """
    if jobs_collection is None:
        return jsonify({"error": "Database 'dice_jobs' collection is unavailable."}), 500
    try:
        job_ids = [str(job['_id']) for job in jobs_collection.find({"is_active": True}, {'_id': 1})]
        random.shuffle(job_ids)
        if not job_ids:
            print(f"MongoDB '{jobs_collection.name}' collection is empty.")
            return jsonify([])
        return jsonify(job_ids)
    except Exception as e:
        print(f"Error fetching job list: {e}")
        return jsonify({"error": f"Internal server error when listing jobs: {e}"}), 500


@app.route('/api/job/<job_id>', methods=['GET'])
def get_job_data(job_id):
    """
    Fetches job details, job-specific ratings, and global skill proficiencies.
    """
    if jobs_collection is None or ratings_collection is None or skills_collection is None:
        return jsonify({"error": "One or more database collections are unavailable."}), 500
    try:
        job_details = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job_details:
            return jsonify({"error": "Job not found."}), 404

        job_details['_id'] = str(job_details['_id'])
        job_details['job_id'] = job_details.pop('_id')
        job_id_str = job_details['job_id']

        existing_rating = ratings_collection.find_one({
            "job_id": job_id_str,
            "profile_name": DEFAULT_PROFILE_NAME
        })

        job_skills = job_details.get('skills', [])
        skill_proficiencies = []
        for skill_name in job_skills:
            proficiency_doc = skills_collection.find_one({
                "profile_name": DEFAULT_PROFILE_NAME,
                "skill_name": skill_name
            })
            user_rating = proficiency_doc.get('user_rating', 0) if proficiency_doc else 0
            skill_proficiencies.append({
                "skill_name": skill_name,
                "user_rating": user_rating
            })

        response_data = {
            "job_details": job_details,
            "skill_proficiencies": skill_proficiencies,
            "user_overall_score": existing_rating.get('overall_score') if existing_rating else None,
            "user_notes": existing_rating.get('notes') if existing_rating else None,
            "existing_highlights": existing_rating.get('highlights', []) if existing_rating else [],
            "review_later": existing_rating.get('review_later', False) if existing_rating else False,
            "source": f"MongoDB - {DATABASE_NAME}"
        }
        return jsonify(response_data)
    except Exception as e:
        print(f"Error fetching job data for {job_id}: {e}")
        return jsonify({"error": f"Internal server error when fetching job data: {e}"}), 500


@app.route('/api/rate', methods=['POST'])
def save_rating():
    """
    Saves job-specific data and updates global skill proficiencies.
    """
    if ratings_collection is None or skills_collection is None:
        return jsonify({"error": "One or more database collections are unavailable."}), 500
    try:
        data = request.json
        job_id = data.get('job_id')
        if not job_id:
            return jsonify({"error": "Missing job_id."}), 400

        timestamp = data.get('timestamp') or datetime.datetime.utcnow().isoformat()

        job_rating_data = {
            "job_id": job_id,
            "profile_name": DEFAULT_PROFILE_NAME,
            "overall_score": data.get('overall_score'),
            "notes": data.get('notes'),
            "highlights": data.get('highlights'),
            "rated_timestamp": timestamp,
            "review_later": data.get('review_later', False)
        }
        ratings_collection.update_one(
            {"job_id": job_id, "profile_name": DEFAULT_PROFILE_NAME},
            {"$set": job_rating_data},
            upsert=True
        )

        rated_skills = data.get('rated_skills', [])
        if rated_skills:
            for skill in rated_skills:
                skill_name = skill.get('skill_name')
                user_rating = skill.get('user_rating')
                if skill_name and user_rating is not None:
                    skills_collection.update_one(
                        {"profile_name": DEFAULT_PROFILE_NAME, "skill_name": skill_name},
                        {"$set": {"user_rating": user_rating, "last_updated": timestamp}},
                        upsert=True
                    )

        return jsonify({"message": f"Rating for job {job_id} saved, and {len(rated_skills)} skills updated."}), 200
    except Exception as e:
        print(f"Error saving rating: {e}")
        return jsonify({"error": f"Internal server error during rating save: {e}"}), 500


@app.route('/api/titles/ratings', methods=['GET'])
def get_title_ratings():
    """
    Fetches all title ratings for the current profile.
    """
    if title_ratings_collection is None:
        return jsonify({"error": "Title ratings collection is unavailable."}), 500
    try:
        ratings_cursor = title_ratings_collection.find({"profile_name": DEFAULT_PROFILE_NAME})
        ratings_dict = {doc['title']: doc['rating'] for doc in ratings_cursor}
        return jsonify(ratings_dict)
    except Exception as e:
        print(f"Error fetching title ratings: {e}")
        return jsonify({"error": f"Internal server error: {e}"}), 500


@app.route('/api/titles/rate', methods=['POST'])
def save_title_rating():
    """
    Saves a rating for a specific job title.
    """
    if title_ratings_collection is None:
        return jsonify({"error": "Title ratings collection is unavailable."}), 500
    try:
        data = request.json
        title = data.get('title')
        rating = data.get('rating')
        if not title or rating is None:
            return jsonify({"error": "Missing 'title' or 'rating' in request."}), 400
        
        timestamp = datetime.datetime.utcnow().isoformat()
        title_ratings_collection.update_one(
            {"profile_name": DEFAULT_PROFILE_NAME, "title": title},
            {"$set": {"rating": rating, "last_updated": timestamp}},
            upsert=True
        )
        return jsonify({"message": f"Rating for title '{title}' saved."}), 200
    except Exception as e:
        print(f"Error saving title rating: {e}")
        return jsonify({"error": f"Internal server error: {e}"}), 500

# --- NEW: Endpoint to scrape a Dice.com job description ---
@app.route('/api/scrape-dice', methods=['POST'])
def scrape_dice_job():
    """
    Fetches a Dice.com job page and extracts the job description HTML.
    Expects JSON: {"url": "https://www.dice.com/job-detail/..."}
    """
    data = request.json
    url = data.get('url')

    if not url:
        return jsonify({"error": "Missing 'url' in request."}), 400

    try:
        # Set a user-agent to mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        
        # Check if the page was found
        if response.status_code == 404:
            return jsonify({"error": "Job listing not found on Dice.com (404 error)."}), 404
        
        response.raise_for_status() # Raise an exception for other bad status codes

        # Parse the HTML content
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the specific div for the job description
        job_description_div = soup.find('div', id='jobDescription')

        if not job_description_div:
            return jsonify({"error": "Could not find the job description section on the page."}), 404

        # Return the inner HTML of the div
        return jsonify({"html": str(job_description_div)})

    except requests.exceptions.RequestException as e:
        print(f"Error making request to Dice.com: {e}")
        return jsonify({"error": f"Could not connect to Dice.com: {e}"}), 500
    except Exception as e:
        print(f"Error scraping Dice job: {e}")
        return jsonify({"error": f"An unexpected error occurred during scraping: {e}"}), 500


if __name__ == '__main__':
    try:
        if db is not None and jobs_collection is not None and jobs_collection.count_documents({}) == 0:
            print(f"WARNING: The '{jobs_collection.name}' collection in '{DATABASE_NAME}' is empty.")
        
        port = int(os.environ.get("PORT", 5000))
        app.run(host='0.0.0.0', port=port, debug=True)
    finally:
        if MONGO_CLIENT:
            MONGO_CLIENT.close()
            print("MongoDB client connection closed.")
