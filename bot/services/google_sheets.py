import csv
import io

import aiohttp


async def fetch_csv_rows(url: str) -> list[dict]:
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            text = await response.text()

    reader = csv.DictReader(io.StringIO(text))
    rows = []

    for row in reader:
        normalized_row = {}
        for key, value in row.items():
            normalized_key = (key or "").strip()
            normalized_row[normalized_key] = (value or "").strip()
        rows.append(normalized_row)

    return rows