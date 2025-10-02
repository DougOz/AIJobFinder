import asyncio
from playwright.async_api import async_playwright
import re
import itertools
from pymongo import errors

# Import the working scrape_dice_job function from your separate file.
from build_dice_url import build_dice_url
from dice_job_scraper import scrape_dice_job

# Import MongoDB functions and constants
from mongodb_functions import connect_to_mongodb, COLLECTION_NAME

# --- MongoDB Data Management Functions ---

def load_existing_urls_from_mongo(collection):
    """Loads all existing job URLs from MongoDB to identify which jobs to skip/update."""
    try:
        # Query only for the 'url' field and return a set of unique URLs
        # Using distinct() is highly efficient for getting all unique values of a field
        urls = collection.distinct('url')
        print(f"Loaded {len(urls)} existing job URLs from MongoDB for check.")
        return set(urls)
    except Exception as e:
        print(f"Error loading existing URLs from MongoDB: {e}")
        return set()

def update_job_search_tag(collection, url, search_string):
    """Updates an existing job document by adding a new search_string to the 'searches' array."""
    try:
        # $addToSet ensures the search_string is only added if it's not already in the array
        result = collection.update_one(
            {'url': url},
            {'$addToSet': {'searches': search_string}}
        )
        return result.modified_count
    except Exception as e:
        print(f"Error updating job {url} search tag: {e}")
        return 0
        
def insert_new_job(collection, job_details, search_string):
    """Inserts a newly scraped job document into MongoDB with the initial search tag."""
    job_details['searches'] = [search_string]
    try:
        collection.insert_one(job_details)
        return True
    except errors.DuplicateKeyError:
        # If a duplicate is encountered during insertion, fall back to updating the search tag
        print(f"Duplicate key error for job {job_details.get('url')}. Updating search tag instead.")
        return update_job_search_tag(collection, job_details['url'], search_string)
    except Exception as e:
        print(f"Error inserting new job: {e}")
        return False

# --- Multi-Page Scraper using Playwright ---

async def get_total_pages(url):
    """Retrieves the total number of pages from the search results using aria-label."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            pagination_locator = page.locator('section[aria-label^="Page 1 of"]')
            await pagination_locator.wait_for(state='visible')
            
            page_info_text = await pagination_locator.get_attribute('aria-label')
            
            match = re.search(r'Page 1 of (\d+)', page_info_text)
            total_pages = int(match.group(1)) if match else 1
            
            print(f"Total search result pages found: {total_pages}")
            return total_pages
        except Exception as e:
            print(f"Could not determine total pages, defaulting to 1. Error: {e}")
            return 1
        finally:
            await browser.close()

async def get_unique_job_links(base_url, total_pages, delay_seconds=1):
    """
    Loops through each page, retrieves unique job links, and adds a delay.
    """
    all_job_links = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        for i in range(1, total_pages + 1):
            page_url = base_url if i == 1 else f"{base_url}&page={i}"
            print(f"Fetching links from page {i}/{total_pages}...")
            
            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_selector('a[data-testid="job-search-job-detail-link"]')
                
                links = await page.locator('a[data-testid="job-search-job-detail-link"]').all()
                for link in links:
                    href = await link.get_attribute('href')
                    if href and '/job-detail/' in href:
                        all_job_links.add(href)
                
                #print(f"Waiting for {delay_seconds} seconds before next page...")
                await asyncio.sleep(delay_seconds)
                
            except Exception as e:
                print(f"Error fetching page {i}. Skipping. Error: {e}")
                continue
        
        await browser.close()
    
    return list(all_job_links)

# --- Data Management and Orchestration ---

async def main_scraper_orchestrator(search_url):
    """
    Main function to orchestrate the entire scraping and MongoDB saving process.
    """
    # 1. Database Connection Setup
    db = connect_to_mongodb()
    if db is None:
        return
        
    job_collection = db[COLLECTION_NAME]

    # Extract the search string from the URL
    search_string = search_url.split('?')[1] if '?' in search_url else 'N/A'
    print(f"\n=======================================================")
    print(f"Starting job scraping pipeline for search: {search_string}")
    print(f"=======================================================")
    
    # 2. Get total pages and all job links
    total_pages = await get_total_pages(search_url)
    all_job_links = await get_unique_job_links(search_url, total_pages, delay_seconds=2)
    
    # 3. Load existing URLs from MongoDB to identify which links to scrape
    existing_urls = load_existing_urls_from_mongo(job_collection)
    
    links_to_scrape = []
    links_to_update = []

    for link in all_job_links:
        if link in existing_urls:
            links_to_update.append(link)
        else:
            links_to_scrape.append(link)
    
    # 4. Update existing jobs with the new search string
    print(f"Updating {len(links_to_update)} existing jobs with new search tag...")
    for link in links_to_update:
        update_job_search_tag(job_collection, link, search_string)

    # 5. Scrape details for new links and insert them
    print(f"Found {len(links_to_scrape)} new job links to scrape and insert.")
    
    scraped_count = 0
    for i, link in enumerate(links_to_scrape):
        job_details = scrape_dice_job(link)
        
        if job_details:
            # Insert or update job details in MongoDB immediately after scraping
            if insert_new_job(job_collection, job_details, search_string):
                scraped_count += 1
        
        if(scraped_count %50 == 0) :        
            print(f"-> Scraped and Saved {i+1}/{len(links_to_scrape)} new jobs.")
        
        # Wait 1 second between scraping requests
        await asyncio.sleep(1)

    print(f"Scraping pipeline finished for search: {search_string}")
    print(f"Total new jobs inserted: {scraped_count}")

async def run_multiple_searches(search_urls):
    """
    Main function to run the scraper for a list of search URLs.
    """
    for url in search_urls:
        await main_scraper_orchestrator(url)
        print("\n--- Moving to next search ---\n")
        
if __name__ == '__main__':

    locations = [
        None,
        "New York, NY",
        "San Francisco, CA",
        "Seattle, WA",
        "Dallas, TX",
        "Chicago, IL",
        "Denver, CO"
    ]
    workplace_types = [
        None,
        "remote"
    ]
    search_strings = [
        "software engineer",
        "software developer"
    ]

    search_queries = []
    for loc, work_type, search_str in itertools.product(locations, workplace_types, search_strings):
        url = build_dice_url(
            search_text=search_str,
            location=loc,
            workplace_type=work_type
        )
        search_queries.append(url)
    
    # The output filename constant is no longer needed here as data goes to MongoDB
    
    asyncio.run(run_multiple_searches(search_queries))
