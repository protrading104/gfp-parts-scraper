"""Google Sheets writer with upsert logic. Setup instructions: see README.md."""
import logging
import os

import gspread
from google.oauth2.service_account import Credentials

log = logging.getLogger("scraper")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SPREADSHEET_NAME = "GFP_Parts_Scrape"
SHEET_NAME = "Parts"
COLUMNS = ["path", "year", "model", "assembly", "ref", "oem", "description", "scraped_at"]


def _unique_key(row: dict) -> str:
    return f"{row['oem']}|{row['ref']}|{row['path']}"


def _get_client(sa_path: str) -> gspread.Client:
    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _open_or_create(client: gspread.Client, spreadsheet_id: str | None) -> gspread.Spreadsheet:
    if spreadsheet_id:
        return client.open_by_key(spreadsheet_id)
    try:
        return client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        log.info(f"Creating spreadsheet '{SPREADSHEET_NAME}'...")
        sp = client.create(SPREADSHEET_NAME)
        sp.share(None, perm_type="anyone", role="reader")
        return sp


def _get_or_create_sheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=SHEET_NAME, rows=10000, cols=len(COLUMNS))
        ws.append_row(COLUMNS, value_input_option="RAW")
        log.info(f"Created sheet '{SHEET_NAME}' with headers")
    return ws


def write_to_sheets(rows: list[dict], scraped_at: str) -> tuple[int, int]:
    """Upsert rows into Google Sheets. Returns (added, updated) or (-1, -1) if disabled."""
    sa_path = os.getenv("GOOGLE_SA_PATH", "")
    if not sa_path:
        log.info("GOOGLE_SA_PATH not set — skipping Google Sheets write")
        return -1, -1
    if not os.path.exists(sa_path):
        log.error(f"Service account file not found: {sa_path}")
        return -1, -1

    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "")

    try:
        client = _get_client(sa_path)
        sp = _open_or_create(client, spreadsheet_id or None)
        ws = _get_or_create_sheet(sp)

        log.info(f"Spreadsheet URL: {sp.url}")

        existing_rows = ws.get_all_records()
        existing: dict[str, dict] = {_unique_key(r): r for r in existing_rows}

        key_to_row: dict[str, int] = {
            _unique_key(r): i + 2 for i, r in enumerate(existing_rows)
        }

        new_to_append: list[dict] = []
        updated_rows: list[tuple[int, dict]] = []
        added = updated = 0

        for row in rows:
            row_with_ts = {**row, "scraped_at": scraped_at}
            k = _unique_key(row_with_ts)
            if k not in existing:
                new_to_append.append(row_with_ts)
                added += 1
            else:
                # Compare without scraped_at (timestamp always changes)
                existing_data = {c: existing[k].get(c, "") for c in COLUMNS if c != "scraped_at"}
                new_data = {c: row_with_ts.get(c, "") for c in COLUMNS if c != "scraped_at"}
                if existing_data != new_data:
                    updated_rows.append((key_to_row[k], row_with_ts))
                    updated += 1

        if new_to_append:
            values = [[r.get(c, "") for c in COLUMNS] for r in new_to_append]
            ws.append_rows(values, value_input_option="RAW")
            log.info(f"Sheets: appended {added} new rows")

        for row_idx, row_data in updated_rows:
            ws.update(
                f"A{row_idx}:{chr(64 + len(COLUMNS))}{row_idx}",
                [[row_data.get(c, "") for c in COLUMNS]],
                value_input_option="RAW",
            )
        if updated:
            log.info(f"Sheets: updated {updated} rows")

        log.info(f"Sheets total rows (excl. header): {len(existing_rows) + added}")
        return added, updated

    except Exception as e:
        log.error(f"Google Sheets write failed: {e}")
        return -1, -1
