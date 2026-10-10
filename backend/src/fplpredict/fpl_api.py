"""Thin client for the official Fantasy Premier League API."""
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import FPL_API


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (fpl-predict-points)"
    retry = Retry(total=5, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
    return s


class FplApi:
    def __init__(self) -> None:
        self.session = _session()

    def _get(self, path: str) -> dict | list:
        r = self.session.get(f"{FPL_API}/{path}", timeout=30)
        r.raise_for_status()
        return r.json()

    def bootstrap(self) -> dict:
        return self._get("bootstrap-static/")

    def fixtures(self) -> list[dict]:
        return self._get("fixtures/")

    def element_summary(self, element_id: int) -> dict:
        return self._get(f"element-summary/{element_id}/")

    def all_element_summaries(self, element_ids: list[int], workers: int = 8) -> dict[int, dict]:
        with ThreadPoolExecutor(workers) as pool:
            results = list(pool.map(self.element_summary, element_ids))
        return dict(zip(element_ids, results))
