"""Download a small public openFDA 510(k) reference sample."""

import json
from pathlib import Path

import httpx

output = Path("data/openfda_510k_sample.json")
output.parent.mkdir(exist_ok=True)
response = httpx.get("https://api.fda.gov/device/510k.json", params={"limit": 100}, timeout=30)
response.raise_for_status()
output.write_text(json.dumps(response.json(), indent=2))
print(output)
