import asyncio
from playwright.async_api import async_playwright
import json
import os
import re
import itertools

# Import the working scrape_dice_job function from your separate file.
from build_dice_url import build_dice_url
from dice_scraper import scrape_dice_job

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

def save_data_to_json(data, filename):
    """Saves a list of dictionaries to a JSON file."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f"Successfully saved {len(data)} job listings to {filename}.")

def load_existing_data(filename):
    """Loads existing data from a JSON file if it exists."""
    if os.path.exists(filename):
        print(f"Loading existing data from {filename}...")
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

async def main_scraper_orchestrator(search_url, filename, batch_size=25):
    """
    Main function to orchestrate the entire scraping and data saving process
    with a checkpointing feature.
    """
    # Extract the search string from the URL
    search_string = search_url.split('?')[1] if '?' in search_url else 'N/A'
    print(f"Starting job scraping pipeline for search: {search_string}")
    
    # 1. Get total pages and all job links
    total_pages = await get_total_pages(search_url)
    all_job_links = await get_unique_job_links(search_url, total_pages, delay_seconds=2)
    
    # 2. Load existing data and identify which links to scrape
    existing_jobs = load_existing_data(filename)
    existing_urls = {job.get('url') for job in existing_jobs}
    
    links_to_scrape = [link for link in all_job_links if link not in existing_urls]
    links_to_update = [link for link in all_job_links if link in existing_urls]

    # Map existing URLs to their job dictionaries for easy lookup
    existing_jobs_by_url = {job['url']: job for job in existing_jobs}

    # 3. Update existing jobs with the new search string
    print(f"Updating {len(links_to_update)} existing jobs with new search...")
    for link in links_to_update:
        job = existing_jobs_by_url[link]
        if 'searches' not in job:
            job['searches'] = []
        if search_string not in job['searches']:
            job['searches'].append(search_string)

    # 4. Scrape details for new links
    print(f"Found {len(links_to_scrape)} new job links to scrape.")
    scraped_jobs = []
    for i, link in enumerate(links_to_scrape):
        job_details = scrape_dice_job(link)
        if job_details:
            # Populate the searches field for new jobs
            job_details['searches'] = [search_string]
            scraped_jobs.append(job_details)
        
        #print(f"Waiting for 1 second before scraping next job...")
        await asyncio.sleep(1)

        # Checkpoint: Save to JSON file every `batch_size` jobs
        if (i + 1) % batch_size == 0 or (i + 1) == len(links_to_scrape):
            print(f"Checkpoint: Saving {len(scraped_jobs)} new jobs to disk...")
            
            # Combine new and updated data and save
            updated_jobs = list(existing_jobs_by_url.values()) + scraped_jobs
            save_data_to_json(updated_jobs, filename)
            
            # Reset the scraped_jobs list and update the existing_jobs_by_url
            scraped_jobs = []
            existing_jobs_by_url = {job['url']: job for job in updated_jobs}

    # Final save to ensure all updates are written
    updated_jobs = list(existing_jobs_by_url.values()) + scraped_jobs
    save_data_to_json(updated_jobs, filename)
    print(f"Scraping pipeline finished for search: {search_string}")

async def run_multiple_searches(search_urls, filename):
    """
    Main function to run the scraper for a list of search URLs.
    """
    for url in search_urls:
        await main_scraper_orchestrator(url, filename)
        print("\n--- Moving to next search ---\n")
        
if __name__ == '__main__':

    locations = [
        None,
        "New York, NY"
    ]
    workplace_types = [
        None,
        "remote"
    ]
    search_strings = [
        "software engineer",
        "software developer"
    ]
    locations = [
        None,
        "New York, NY"
        "San Francisco, CA",
        "Seattle, WA",
        "Dallas, TX",
        "Chicago, IL",
        "Denver, CO"
        ]

    search_queries = []
    for loc, work_type, search_str in itertools.product(locations, workplace_types, search_strings):
        url = build_dice_url(
            search_text=search_str,
            location=loc,
            workplace_type=work_type
        )
        search_queries.append(url)
    output_filename = "dice_job_data.json"
    
    asyncio.run(run_multiple_searches(search_queries, output_filename))