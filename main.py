from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import undetected_chromedriver as uc
import random
import time
import uvicorn
from typing import Optional, List
import atexit
import signal
import sys
from threading import Lock
import queue
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class URLRequest(BaseModel):
    url: str

class ArticleResponse(BaseModel):
    content: str
    status: str
    error: Optional[str] = None

class DriverPool:
    def __init__(self, max_drivers=3):
        self.max_drivers = max_drivers
        self.available_drivers = queue.Queue()
        self.all_drivers = []
        self.lock = Lock()
        self.init_drivers()

    def init_drivers(self):
        """Initialize a pool of drivers"""
        for _ in range(self.max_drivers):
            try:
                driver = self.create_new_driver()
                self.available_drivers.put(driver)
                self.all_drivers.append(driver)
            except Exception as e:
                logger.error(f"Failed to initialize driver: {e}")

    def create_new_driver(self):
        """Create a new driver instance"""
        options = uc.ChromeOptions()
        
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }
        
        options.add_argument('--headless')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--start-maximized')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        ]
        options.add_argument(f'user-agent={random.choice(user_agents)}')
        
        driver = uc.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def get_driver(self):
        """Get an available driver from the pool"""
        try:
            driver = self.available_drivers.get(timeout=30)
            return driver
        except queue.Empty:
            logger.warning("No available drivers in pool")
            return None

    def return_driver(self, driver):
        """Return a driver to the pool"""
        if driver:
            try:
                driver.delete_all_cookies()
                self.available_drivers.put(driver)
            except Exception as e:
                logger.error(f"Error returning driver to pool: {e}")
                self.replace_driver(driver)

    def replace_driver(self, old_driver):
        """Replace a faulty driver with a new one"""
        with self.lock:
            try:
                if old_driver in self.all_drivers:
                    self.all_drivers.remove(old_driver)
                    try:
                        old_driver.quit()
                    except Exception:
                        pass
                
                new_driver = self.create_new_driver()
                self.all_drivers.append(new_driver)
                self.available_drivers.put(new_driver)
            except Exception as e:
                logger.error(f"Error replacing driver: {e}")

    def cleanup(self):
        """Cleanup all drivers"""
        with self.lock:
            for driver in self.all_drivers:
                try:
                    driver.quit()
                except Exception:
                    pass
            self.all_drivers.clear()
            while not self.available_drivers.empty():
                try:
                    self.available_drivers.get_nowait()
                except queue.Empty:
                    break

# Initialize the driver pool
driver_pool = DriverPool(max_drivers=3)

def random_typing(element, text):
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.1, 0.3))

def scroll_with_random_speed(driver):
    try:
        total_height = driver.execute_script("return document.body.scrollHeight")
        current_position = 0
        
        while current_position < total_height:
            scroll_step = random.randint(50, 300)
            scroll_delay = random.uniform(0.1, 0.8)
            speed_change = random.randint(1, 10)
            
            next_position = min(current_position + scroll_step, total_height)
            
            scroll_script = f"""
            window.scrollTo({{
                top: {next_position},
                behavior: 'smooth'
            }});
            """
            driver.execute_script(scroll_script)
            
            current_position = next_position
            
            if speed_change == 1:
                time.sleep(random.uniform(1.0, 2.5))
            else:
                time.sleep(scroll_delay)
            
            if random.random() < 0.15:
                scroll_up = random.randint(100, 500)
                current_position = max(0, current_position - scroll_up)
                driver.execute_script(f"window.scrollTo({{top: {current_position}, behavior: 'smooth'}})")
                time.sleep(random.uniform(0.5, 1.0))
        
        driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
        time.sleep(1)
        
    except Exception as e:
        logger.error(f"Error during scrolling: {e}")

async def scrape_spaywall(url_to_check: str) -> dict:
    driver = driver_pool.get_driver()
    if not driver:
        return {"status": "error", "error": "No available drivers", "content": ""}
    
    try:
        driver.get("https://www.spaywall.com/")
        
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="search_input"]'))
        )
        random_typing(search_input, url_to_check)
        
        submit_button = driver.find_element(By.XPATH, '//*[@id="submit_news"]')
        submit_button.click()
        
        time.sleep(5)
        
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            scroll_with_random_speed(driver)
            time.sleep(3)
            
        except TimeoutException:
            return {"status": "error", "error": "Timeout waiting for page load", "content": ""}
        
        main_content = driver.find_element(By.TAG_NAME, "body").text
        
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        iframe_content = ""
        
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                iframe_body = driver.find_element(By.TAG_NAME, "body")
                iframe_content += "\n" + iframe_body.get_attribute('innerText')
                driver.switch_to.default_content()
            except Exception:
                if driver:
                    driver.switch_to.default_content()
                continue
        
        full_content = f"{main_content}\n{iframe_content}".strip()
        return {"status": "success", "content": full_content, "error": None}
        
    except Exception as e:
        logger.error(f"Error during scraping: {e}")
        return {"status": "error", "error": str(e), "content": ""}
        
    finally:
        if driver:
            driver_pool.return_driver(driver)

@app.post("/scrape", response_model=ArticleResponse)
async def scrape_article(request: URLRequest):
    try:
        result = await scrape_spaywall(request.url)
        return ArticleResponse(
            content=result["content"],
            status=result["status"],
            error=result["error"]
        )
    except Exception as e:
        logger.error(f"Error in scrape endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_drivers": len(driver_pool.all_drivers),
        "available_drivers": driver_pool.available_drivers.qsize()
    }

def cleanup():
    """Cleanup function to properly close any remaining driver instances"""
    logger.info("Cleaning up drivers...")
    driver_pool.cleanup()

# Register cleanup handlers
atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda x, y: cleanup() or sys.exit(0))
signal.signal(signal.SIGTERM, lambda x, y: cleanup() or sys.exit(0))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
