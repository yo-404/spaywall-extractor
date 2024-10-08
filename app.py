import os
import time
import random
import logging
from typing import Optional, Tuple
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from fake_useragent import UserAgent

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

class ArchiveLinkExtractor:
    def __init__(self):
        self.setup_driver()

    def setup_driver(self):
        """Initialize the Chrome driver with appropriate settings."""
        ua = UserAgent()
        self.options = webdriver.ChromeOptions()
        self.options.add_argument(f'user-agent={ua.random}')
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-gpu')
        self.options.add_argument('--headless')
        # Add the following lines if using Render's environment variables for Chrome
        self.options.binary_location = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
        self.options.add_argument('--window-size=1920x1080')

    def add_random_delay(self, min_delay: float = 1, max_delay: float = 3) -> None:
        """Add a random delay to mimic human behavior."""
        time.sleep(random.uniform(min_delay, max_delay))

    def extract_link(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract the archived link from archive.is.
        Returns: Tuple[link, error_message]
        """
        driver = None
        try:
            # Initialize driver with executable path
            driver = webdriver.Chrome(
                executable_path=os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver"),
                options=self.options
            )
            driver.set_page_load_timeout(30)

            # Navigate to the URL
            logger.info(f"Navigating to URL: {url}")
            driver.get(url)

            # Add a small delay to let the page load
            self.add_random_delay()

            try:
                # Try to find the specific element using the xpath
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//*[@id="row0"]/div[2]/a[1]'))
                )
                href_value = element.get_attribute('href')
                logger.info(f"Found href value: {href_value}")
                return href_value, None

            except (NoSuchElementException, TimeoutException):
                # If xpath not found, return current URL
                current_url = driver.current_url
                logger.info(f"XPath not found, returning current URL: {current_url}")
                return current_url, None

        except Exception as e:
            error_msg = f"Error occurred: {str(e)}"
            logger.error(error_msg)
            return None, error_msg

        finally:
            if driver:
                driver.quit()

# Initialize extractor
link_extractor = ArchiveLinkExtractor()

@app.route('/extract-archive-link', methods=['POST'])
def extract_archive_link():
    """Handle archive link extraction requests."""
    try:
        data = request.get_json()
        url = data.get('url')

        if not url:
            return jsonify({"error": "No URL provided"}), 400

        result, error = link_extractor.extract_link(url)

        if error:
            return jsonify({"error": error}), 500

        return jsonify({
            "original_url": url,
            "extracted_link": result,
            "status": "success"
        })

    except Exception as e:
        logger.error(f"Request processing error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
