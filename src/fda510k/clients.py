"""Thin clients for public FDA reference APIs."""

from typing import cast

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class OpenFdaClient:
    """Read 510(k) records from the public openFDA API."""

    base_url = "https://api.fda.gov/device/510k.json"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def lookup(self, k_number: str) -> dict[str, object]:
        response = httpx.get(self.base_url, params={"search": f'k_number:"{k_number}"'}, timeout=20)
        response.raise_for_status()
        return cast(dict[str, object], response.json())
