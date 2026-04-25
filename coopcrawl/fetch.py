from __future__ import annotations

import logging
import os
from pathlib import Path

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions

from coopcrawl.entry import Entry
from coopcrawl.errors import classify_status

log = logging.getLogger(__name__)


def _ensure_xpi(xpi_path: str, xpi_url: str) -> None:
    """Download the adblock XPI to xpi_path if it isn't already there."""
    p = Path(xpi_path)
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading adblock XPI from %s to %s", xpi_url, xpi_path)
    resp = requests.get(xpi_url, timeout=60)
    resp.raise_for_status()
    p.write_bytes(resp.content)


def build_driver(
    adblock_xpi_path: str | None,
    adblock_xpi_url: str,
    firefox_binary_path: str | None,
) -> webdriver.Firefox:
    opts = FirefoxOptions()
    opts.add_argument("--headless")
    opts.set_preference("privacy.trackingprotection.enabled", True)
    opts.set_preference("privacy.trackingprotection.pbmode.enabled", True)
    opts.set_preference("privacy.trackingprotection.socialtracking.enabled", True)
    if firefox_binary_path:
        opts.binary_location = firefox_binary_path

    driver = webdriver.Firefox(options=opts)

    if adblock_xpi_path is not None:
        try:
            _ensure_xpi(adblock_xpi_path, adblock_xpi_url)
            driver.install_addon(adblock_xpi_path, temporary=True)
        except Exception:
            log.warning("install_addon failed; clearing cache and retrying once", exc_info=True)
            try:
                if os.path.exists(adblock_xpi_path):
                    os.remove(adblock_xpi_path)
                _ensure_xpi(adblock_xpi_path, adblock_xpi_url)
                driver.install_addon(adblock_xpi_path, temporary=True)
            except Exception:
                driver.quit()
                raise

    return driver


def head_check(url: str, timeout: int) -> None:
    """Raise FourXXError / FiveXXError per spec §9 if status is not 2xx/3xx."""
    try:
        resp = requests.head(url, allow_redirects=True, timeout=timeout)
    except requests.Timeout as e:
        from coopcrawl.errors import FourXXError

        raise FourXXError(408, url, "HEAD timed out") from e
    cls = classify_status(resp.status_code)
    if cls is None:
        log.debug("HEAD %s -> %s (final url %s)", url, resp.status_code, resp.url)
        return
    raise cls(resp.status_code, url)


def fetch_via_selenium(driver: webdriver.Firefox, entry: Entry) -> str:
    """Drive the shared browser; extract innerText at the configured xpath."""
    driver.set_page_load_timeout(entry.timeout_secs)
    try:
        driver.get(entry.url)
    except TimeoutException:
        log.warning("Selenium page-load timeout on %s; extracting whatever loaded", entry.url)
    el = driver.find_element(By.XPATH, entry.xpath)
    text = el.get_attribute("innerText")
    return text or ""
