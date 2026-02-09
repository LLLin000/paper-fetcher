"""Proxy authentication management for various university VPN systems."""

import json
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from .config import Config

logger = logging.getLogger(__name__)

TEST_URL = "https://www.nature.com"


class ProxyAuth:
    """Manages university proxy/VPN authentication."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.config.ensure_dirs()
        self._session: requests.Session | None = None
        self._driver: webdriver.Chrome | None = None
        self._proxy_type = self._detect_proxy_type()

    def _detect_proxy_type(self) -> str:
        """Detect proxy type from URL pattern."""
        proxy_base = self.config.proxy_base.lower()

        if "webvpn" in proxy_base:
            return "webvpn"
        elif "ezproxy" in proxy_base or "eproxy" in proxy_base:
            return "ezproxy"
        elif "vpn" in proxy_base:
            return "vpn"
        else:
            return "generic"

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            })
        return self._session

    def login(self, force: bool = False) -> bool:
        """Ensure we have a valid proxy session."""
        if not self.config.proxy_base:
            logger.info("No proxy configured - skipping authentication.")
            return False

        if not force and self._try_load_cookies():
            logger.info("Loaded saved cookies - session is valid.")
            return True

        logger.info("No valid session found. Opening browser for login...")
        return self._browser_login()

    def _try_load_cookies(self) -> bool:
        """Try to load cookies from file and validate them."""
        cookie_path = Path(self.config.cookie_path)
        if not cookie_path.exists():
            return False

        try:
            cookies = json.loads(cookie_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read cookies: %s", e)
            return False

        for cookie in cookies:
            self.session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/"),
            )

        return self._validate_session()

    def _validate_session(self) -> bool:
        """Check if the current session can access proxied content."""
        try:
            proxy_url = self.get_proxied_url(TEST_URL)
            resp = self.session.get(proxy_url, timeout=15, allow_redirects=True)

            # Check if we're redirected to login
            if "login" in resp.url.lower():
                logger.info("Session expired - redirected to login.")
                return False

            # Check for successful proxy access
            if resp.status_code == 200:
                return True

        except requests.RequestException as e:
            logger.warning("Session validation failed: %s", e)

        return False

    def _browser_login(self) -> bool:
        """Open Chrome for manual login."""
        options = Options()
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--remote-allow-origins=*")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        try:
            service = Service(ChromeDriverManager().install())
            self._driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            logger.error("Failed to start Chrome: %s", e)
            return False

        # Navigate to proxy login
        login_url = self.get_proxied_url(TEST_URL)
        self._driver.get(login_url)

        print("\n" + "=" * 60)
        print(f"  Please log in to your university {self._proxy_type.upper()}")
        print("  The tool will detect when login is complete.")
        print("=" * 60 + "\n")

        max_wait = 600
        poll_interval = 3
        elapsed = 0
        last_url = ""

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                current_url = self._driver.current_url

                if current_url != last_url:
                    logger.info("Browser URL: %s", current_url)
                    last_url = current_url

                # Detect successful login
                if self._is_login_successful(current_url):
                    logger.info("Login detected! URL: %s", current_url)
                    self._save_browser_cookies()
                    print("\n  Login successful! Cookies saved.\n")
                    self._close_browser()
                    return True

            except Exception:
                logger.warning("Browser connection lost.")
                self._driver = None
                return False

        print("\n  Login timed out after 10 minutes.\n")
        self._close_browser()
        return False

    def _is_login_successful(self, url: str) -> bool:
        """Check if URL indicates successful login."""
        url_lower = url.lower()

        # WebVPN: URL contains webvpn domain and not login
        if self._proxy_type == "webvpn":
            return "webvpn" in url_lower and "login" not in url_lower

        # EZproxy: URL contains eproxy/ezproxy domain
        if self._proxy_type == "ezproxy":
            return ("eproxy" in url_lower or "ezproxy" in url_lower) and "login" not in url_lower

        # Generic: not on login page
        return "login" not in url_lower

    def _save_browser_cookies(self):
        """Save cookies from Selenium browser to file."""
        if not self._driver:
            return

        cookies = self._driver.get_cookies()
        cookie_path = Path(self.config.cookie_path)
        cookie_path.write_text(
            json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Saved %d cookies to %s", len(cookies), cookie_path)

        for cookie in cookies:
            self.session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/"),
            )

    def _close_browser(self):
        """Close the Selenium browser."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def get_proxied_url(self, url: str) -> str:
        """Convert a regular URL to a proxied URL."""
        if not self.config.proxy_base:
            return url

        # Already proxied
        if self._proxy_type in url.lower():
            return url

        # WebVPN format: https://webvpn.xxx.edu.cn/https://target.url
        if self._proxy_type == "webvpn":
            return f"{self.config.proxy_base.rstrip('/')}/{url}"

        # EZproxy format: http://proxy.edu/login?url=https://target.url
        return f"{self.config.proxy_base}{url}"

    def fetch(self, url: str, **kwargs) -> requests.Response:
        """Fetch a URL through the authenticated session."""
        proxied = self.get_proxied_url(url)
        kwargs.setdefault("timeout", 30)
        kwargs.setdefault("allow_redirects", True)
        return self.session.get(proxied, **kwargs)

    def close(self):
        """Clean up resources."""
        self._close_browser()
        if self._session:
            self._session.close()
            self._session = None
