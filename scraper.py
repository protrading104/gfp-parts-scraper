"""
Scraper: genuinefactoryparts.com → CSV
Path: MTD Merged Data Staging - Troy-Bilt - 11-Push Walk-Behind Mowers - 2024/2025 Models
Output: output/parts.csv  columns: path, year, model, assembly, ref, oem, description
Logs:   logs/scrape_YYYYMMDD.log
"""
import asyncio
import csv
import json
import logging
import os
import random
from datetime import datetime

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from sheets import write_to_sheets

load_dotenv()


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    log_file = f"logs/scrape_{datetime.now().strftime('%Y%m%d')}.log"
    fmt = "%(asctime)s  %(levelname)-7s  %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    return logging.getLogger("scraper"), log_file

URL = "https://www.genuinefactoryparts.com/en_US/ari-partstream.html"
YEARS = ["2024 Models", "2025 Models"]
BRAND = "MTD Merged Data Staging"
PRODUCT_LINE = "Troy-Bilt"
CATEGORY = "11-Push Walk-Behind Mowers"
PATH_PREFIX = f"{BRAND} - {PRODUCT_LINE} - {CATEGORY}"


async def sleep(ms):
    await asyncio.sleep(ms / 1000 + random.uniform(0, 0.3))

async def get_ari_text(frame):
    return await frame.evaluate("document.getElementById('ari_assemblies')?.innerText?.trim() || ''")

async def wait_ari_change(frame, prev, timeout=15000):
    try:
        await frame.wait_for_function(
            f"() => (document.getElementById('ari_assemblies')?.innerText?.trim()||'') !== {json.dumps(prev[:100])}",
            timeout=timeout)
    except:
        pass
    await asyncio.sleep(1.0)

async def get_last_col(frame):
    return await frame.evaluate("""
        () => {
            const cols = document.querySelectorAll('.ari-hierarchy-item');
            const last = cols[cols.length - 1];
            if (!last) return [];
            return [...last.querySelectorAll('li.ari-hlvlItem')].map(e => e.innerText.trim());
        }
    """)

async def click_last_col(frame, text):
    return await frame.evaluate(f"""
        () => {{
            const cols = document.querySelectorAll('.ari-hierarchy-item');
            const last = cols[cols.length - 1];
            if (!last) return false;
            for (const li of last.querySelectorAll('li.ari-hlvlItem'))
                if (li.innerText.trim() === {json.dumps(text)}) {{ li.click(); return true; }}
            return false;
        }}
    """)

async def click_any_lvl_item(frame, text):
    return await frame.evaluate(f"""
        () => {{
            for (const li of document.querySelectorAll('li.ari-hlvlItem'))
                if (li.innerText.trim() === {json.dumps(text)}) {{ li.click(); return true; }}
            return false;
        }}
    """)

async def click_dot_item(frame, title):
    return await frame.evaluate(f"""
        () => {{
            for (const el of document.querySelectorAll('#ari_assemblies .item'))
                if (el.getAttribute('title') === {json.dumps(title)}) {{ el.click(); return true; }}
            return false;
        }}
    """)

async def click_assembly_tile(frame, title):
    return await frame.evaluate(f"""
        () => {{
            const sel = '.ari-assembly-select .item';
            for (const el of document.querySelectorAll(sel))
                if (el.getAttribute('title') === {json.dumps(title)}) {{ el.click(); return true; }}
            return false;
        }}
    """)

async def get_assembly_tiles(frame):
    return await frame.evaluate("""
        () => [...document.querySelectorAll('.ari-assembly-select .item')]
              .map(e => e.getAttribute('title')).filter(Boolean)
    """)

async def wait_details_panel(frame, timeout=15000):
    try:
        await frame.wait_for_function(
            "() => document.getElementById('ariDetailsPanel')?.style?.display !== 'none' && "
            "      document.getElementById('ariDetailsPanel')?.style?.display !== '' && "
            "      document.querySelectorAll('li.ariPartInfo').length > 0",
            timeout=timeout)
    except:
        pass
    await asyncio.sleep(0.8)

async def parse_parts(frame, path, year, model, assembly):
    return await frame.evaluate(f"""
        () => {{
            const rows = document.querySelectorAll('li.ariPartInfo');
            const parts = [];
            for (const row of rows) {{
                const ref = row.querySelector('.ariPLTag')?.innerText?.replace('Ref:', '')?.trim() || '';
                const oem = row.querySelector('.ariPartNumber')?.innerText?.trim() || '';
                const desc = row.querySelector('.ariPLDesc')?.innerText?.trim() || '';
                if (oem) parts.push({{ ref, oem, desc }});
            }}
            return parts;
        }}
    """)


async def init_page(page):
    await page.goto(URL, wait_until="networkidle", timeout=60000)
    await asyncio.sleep(3)
    try:
        b = await page.query_selector("#onetrust-accept-btn-handler")
        if b and await b.is_visible():
            await b.click()
            await asyncio.sleep(1.5)
    except:
        pass
    frame = next((f for f in page.frames if "ari-iframe" in f.url), None)
    if not frame:
        return None
    await frame.evaluate("document.getElementById('onetrust-consent-sdk')?.remove()")
    await asyncio.sleep(0.5)
    return frame

async def navigate_to_year(frame, year_label):
    prev = await get_ari_text(frame)
    await frame.evaluate("document.querySelector('.brandLogoBox')?.click()")
    await wait_ari_change(frame, prev)
    prev = await get_ari_text(frame)
    await click_dot_item(frame, PRODUCT_LINE)
    await wait_ari_change(frame, prev)
    prev = await get_ari_text(frame)
    await click_last_col(frame, CATEGORY)
    await wait_ari_change(frame, prev)
    prev = await get_ari_text(frame)
    ok = await click_last_col(frame, year_label)
    if not ok:
        ok = await click_any_lvl_item(frame, year_label)
    if not ok:
        return False
    await wait_ari_change(frame, prev)
    return True

async def navigate_to_model(frame, year_label, model):
    if not await navigate_to_year(frame, year_label):
        return False
    ok = await click_last_col(frame, model)
    if not ok:
        return False
    # Wait until either assembly tiles or sub-category items load
    try:
        await frame.wait_for_function(
            "() => document.querySelectorAll('.ari-assembly-select .item').length > 0 ||"
            "      document.querySelectorAll('.ari-hierarchy-item').length > 3",
            timeout=15000)
    except:
        pass
    await asyncio.sleep(1.0)
    return True

async def collect_tiles_for_model(context, year_label, model):
    """
    Returns list of (nav_steps: list[str], tiles: list[str]).
    Navigates the full hierarchy under the model, following every branch,
    using fresh pages for backtracking when needed.
    nav_steps = hierarchy items clicked after the model (e.g. [] or ['Engine','5C65M0 163cc Engine']).
    """

    async def explore_path(nav_steps):
        page = await context.new_page()
        frame = await init_page(page)
        if not frame:
            await page.close()
            return []
        if not await navigate_to_model(frame, year_label, model):
            await page.close()
            return []

        for step in nav_steps:
            prev = await get_ari_text(frame)
            ok = await click_last_col(frame, step)
            if not ok:
                await page.close()
                return []
            await wait_ari_change(frame, prev)

        tiles = await get_assembly_tiles(frame)
        if tiles:
            await page.close()
            return [(nav_steps, tiles)]

        last_col = await get_last_col(frame)
        await page.close()

        if not last_col:
            return []

        results = []
        for item in last_col:
            sub = await explore_path(nav_steps + [item])
            results.extend(sub)
        return results

    return await explore_path([])


FIELDNAMES = ["path", "year", "model", "assembly", "ref", "oem", "description"]
OUT_PATH = "output/parts.csv"

def unique_key(row):
    return f"{row['oem']}|{row['ref']}|{row['path']}"

def load_existing():
    if not os.path.exists(OUT_PATH):
        return {}
    with open(OUT_PATH, newline="", encoding="utf-8-sig") as f:
        return {unique_key(r): r for r in csv.DictReader(f)}

def upsert_and_save(new_rows, existing):
    added = updated = 0
    for row in new_rows:
        k = unique_key(row)
        if k not in existing:
            existing[k] = row
            added += 1
        elif existing[k] != row:
            existing[k] = row
            updated += 1
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(existing.values())
    return added, updated


async def scrape():
    log, log_file = setup_logging()
    os.makedirs("output", exist_ok=True)

    start_ts = datetime.now()
    log.info("=" * 60)
    log.info(f"Run started: {start_ts.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Log file:    {log_file}")

    existing = load_existing()
    log.info(f"Existing records in CSV: {len(existing)}")

    results = []
    stats = {"models": 0, "assemblies": 0, "parts": 0, "errors": 0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )

        all_year_models = []
        for year_label in YEARS:
            page = await context.new_page()
            frame = await init_page(page)
            if not frame:
                log.error(f"Frame not found for {year_label}")
                stats["errors"] += 1
                await page.close()
                continue
            ok = await navigate_to_year(frame, year_label)
            if not ok:
                log.warning(f"'{year_label}' not found — skipping")
                stats["errors"] += 1
                await page.close()
                continue
            models = await get_last_col(frame)
            log.info(f"Year {year_label}: {len(models)} models — {models}")
            all_year_models.extend([(year_label, m) for m in models])
            await page.close()

        for year_label, model in all_year_models:
            year = year_label.replace(" Models", "")
            log.info(f"--- Model: {model} ({year_label})")
            stats["models"] += 1

            tile_groups = await collect_tiles_for_model(context, year_label, model)

            if not tile_groups:
                log.warning(f"No assembly tiles found for {model}")
                stats["errors"] += 1
                continue

            for nav_steps, tiles in tile_groups:
                log.info(f"  Assemblies ({len(tiles)}){' via ' + ' > '.join(nav_steps) if nav_steps else ''}: {tiles}")

                page = await context.new_page()
                frame = await init_page(page)
                if not frame:
                    log.error(f"Frame not found when scraping {model}")
                    stats["errors"] += 1
                    await page.close()
                    continue
                if not await navigate_to_model(frame, year_label, model):
                    log.error(f"Navigation failed for {model}")
                    stats["errors"] += 1
                    await page.close()
                    continue
                for step in nav_steps:
                    prev = await get_ari_text(frame)
                    await click_last_col(frame, step)
                    await wait_ari_change(frame, prev)

                if nav_steps and "Assembl" not in nav_steps[0]:
                    middle = " - ".join(nav_steps)
                else:
                    middle = f"Assemblies for {model}"

                stats["assemblies"] += len(tiles)
                for assembly_name in tiles:
                    await click_assembly_tile(frame, assembly_name)
                    await wait_details_panel(frame)
                    await sleep(1000 + random.randint(200, 500))

                    path = f"{PATH_PREFIX} - {year_label} - {model} - {middle} - {assembly_name}"
                    parts = await parse_parts(frame, path, year, model, assembly_name)
                    log.info(f"    {assembly_name}: {len(parts)} parts")
                    stats["parts"] += len(parts)

                    for pt in parts:
                        results.append({
                            "path": path,
                            "year": year,
                            "model": model,
                            "assembly": assembly_name,
                            "ref": pt["ref"],
                            "oem": pt["oem"],
                            "description": pt["desc"],
                        })

                await page.close()

        await browser.close()

    added, updated = upsert_and_save(results, existing)

    scraped_at = start_ts.strftime("%Y-%m-%dT%H:%M:%S")
    sh_added, sh_updated = write_to_sheets(results, scraped_at)

    duration = datetime.now() - start_ts
    mins, secs = divmod(int(duration.total_seconds()), 60)

    log.info("=" * 60)
    log.info(f"DONE  —  duration: {mins}m {secs}s")
    log.info(f"Models: {stats['models']}  Assemblies: {stats['assemblies']}  Parts scraped: {stats['parts']}")
    log.info(f"CSV:    {OUT_PATH}  |  added: {added}  updated: {updated}  total: {len(existing)}")
    if sh_added >= 0:
        log.info(f"Sheets: added: {sh_added}  updated: {sh_updated}")
    if stats["errors"]:
        log.warning(f"Errors: {stats['errors']} (see log above for details)")


if __name__ == "__main__":
    asyncio.run(scrape())
