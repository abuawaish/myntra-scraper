from flask import Flask, send_file, render_template, request, redirect, url_for, jsonify
import pandas as pd
import time
import platform
import threading
from io import BytesIO
from typing import List, Dict, Any, Optional
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, ElementClickInterceptedException, WebDriverException
)
from selenium.webdriver.common.keys import Keys

app = Flask(__name__)

# Global scraping status
scraping_status: Dict[str, Any] = {
    'progress': 0,
    'message': '',
    'is_complete': False,
    'data': None
}

def reset_scraping_status() -> None:
    """Resets the global scraping progress tracker."""
    global scraping_status
    scraping_status = {
        'progress': 0,
        'message': '',
        'is_complete': False,
        'data': None
    }

def configure_driver() -> webdriver.Chrome:
    """Configures and returns a headless Chrome WebDriver."""
    options = Options()
    options.headless = True  # Enable headless mode
    options.add_argument("--disable-gpu")  # Necessary for headless mode on Windows
    options.add_argument("--no-sandbox")  # Bypass OS security model
    options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource issues
    options.add_argument("--remote-debugging-port=9222")  # Required for Android

    # Android Compatibility
    if "android" in platform.system().lower():
        options.add_argument("--user-agent=Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.88 Mobile Safari/537.36")

    # Initialize WebDriver with headless options
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def save_to_csv(data):
    csv_buffer = BytesIO()
    df = pd.DataFrame(data)
    df.to_csv(csv_buffer, index=False) #type: ignore
    csv_buffer.seek(0)
    return csv_buffer


@app.route('/download_csv')
def download_csv():
    """Route for downloading CSV file"""
    if not scraping_status['data']:
        return redirect(url_for('index'))

    csv_buffer = save_to_csv(scraping_status['data'])
    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name='myntra_products.csv'
    )

def get_product_urls(driver: webdriver.Chrome, keyword: str, max_pages: int = 3) -> List[str]:
    """Fetches product URLs from Myntra search results."""
    urls: List[str] = []
    next_button: Optional[WebElement] = None

    try:
        search_box = WebDriverWait(driver, 10).until(
            ec.presence_of_element_located((By.CLASS_NAME, 'desktop-query'))
        )
        search_bar = search_box.find_element(By.CLASS_NAME, 'desktop-searchBar')
        search_bar.clear()
        search_bar.send_keys(keyword)
        search_bar.send_keys(Keys.RETURN)
        time.sleep(3)  # Allow search results to load

        for page in range(max_pages):
            scraping_status['message'] = f"📄 Scraping page {page + 1} of {max_pages}"
            scraping_status['progress'] = int((page / max_pages) * 50)

            product_elements = WebDriverWait(driver, 10).until(
                ec.presence_of_all_elements_located((By.XPATH, '//li[contains(@class, "product-base")]'))
            )

            for element in product_elements:
                try:
                    product_url = element.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    if product_url and product_url not in urls:
                        urls.append(product_url)
                except NoSuchElementException:
                    continue

            try:
                next_button = WebDriverWait(driver, 5).until(
                    ec.element_to_be_clickable((By.CLASS_NAME, 'pagination-next'))
                )
                driver.execute_script("arguments[0].scrollIntoView();", next_button)
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3)  # Allow next page to load
            except (TimeoutException, NoSuchElementException):
                scraping_status['message'] = "✅ Reached last page of results"
                break
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3)

    except Exception as e:
        scraping_status['message'] = f"❌ Error in URL collection: {str(e)}"
        return []

    return urls

def scrape_product_details(keyword: str, limit: int = 10, max_pages: int = 3) -> None:
    """Scrapes product details from Myntra."""
    driver: WebDriver | None = None
    reset_scraping_status()
    site_url = "https://www.myntra.com/"
    data: Dict[str, List[Any]] = {"Brand": [], "Product": [], "Rating": [], "Total Ratings": [], "Price (₹)": [], "Discount": []}

    try:
        driver = configure_driver()
        driver.get(site_url)
        time.sleep(2)

        product_urls = get_product_urls(driver, keyword, max_pages)
        if not product_urls:
            scraping_status['message'] = "⚠️ No products found for this search"
            scraping_status['is_complete'] = True
            return

        scraping_status['message'] = f"🔍 Found {len(product_urls)} products, extracting details..."

        for i, url in enumerate(product_urls[:limit]):
            try:
                driver.get(url)
                time.sleep(2)

                scraping_status['progress'] = 50 + int((i / min(limit, len(product_urls))) * 50)
                scraping_status['message'] = f"🔄 Processing product {i + 1} of {min(limit, len(product_urls))}"

                def safe_find(xpath: str) -> str:
                    """Safely finds an element's text, returning 'N/A' if not found."""
                    try:
                        return driver.find_element(By.XPATH, xpath).text.strip()
                    except NoSuchElementException:
                        return "N/A"

                data["Brand"].append(safe_find('//h1[contains(@class, "pdp-title")]'))
                data["Product"].append(safe_find('//h1[contains(@class, "pdp-name")]'))
                data["Rating"].append(safe_find('//div[contains(@class, "index-overallRating")]').split('\n')[0])
                data["Total Ratings"].append(safe_find('//div[contains(@class, "index-ratingsCount")]'))
                data["Price (₹)"].append(safe_find('//span[contains(@class, "pdp-price")]/strong').replace('₹', '').replace(',', ''))
                data["Discount"].append(safe_find('//span[contains(@class, "pdp-discount")]'))

            except Exception as e:
                print(f"Error scraping product {i}: {e}")
                continue

        scraping_status['data'] = pd.DataFrame(data).to_dict('records')
        scraping_status['message'] = "✅ Scraping completed successfully!"
        scraping_status['is_complete'] = True

    except WebDriverException as e:
        scraping_status['message'] = f"❌ WebDriver error: {str(e)}"
    except Exception as e:
        scraping_status['message'] = f"❌ Unexpected error: {str(e)}"
    finally:
        driver.quit()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        keyword = request.form['keyword'].strip()
        limit = int(request.form.get('limit', 10))
        max_pages = int(request.form.get('max_pages', 3))

        thread = threading.Thread(target=scrape_product_details, args=(keyword, limit, max_pages))
        thread.start()

        return redirect(url_for('progress'))
    return render_template('index.html')

@app.route('/progress')
def progress():
    return render_template('progress.html')

@app.route('/get_progress')
def get_progress():
    return jsonify(scraping_status)

@app.route('/results')
def results():
    if not scraping_status['is_complete'] or not scraping_status['data']:
        return redirect(url_for('index'))
    data = scraping_status['data']
    return render_template('results.html', products=data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
