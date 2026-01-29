# GRP JSON Data Directory

This directory contains JSON files with taxpayer data from the Belarusian Ministry of Taxes and Duties (MNS) GRP API.

## ⚠️ Important Notes

**GRP API has rate limiting!** The API blocks too frequent requests (HTTP 429 errors).
- Data fetching uses controlled parallel processing (3 concurrent requests)
- Automatic retry logic is implemented for rate limit errors
- Significantly faster than sequential processing

## Performance

- **Parallel processing**: Up to 6 concurrent requests (balanced performance)
- **Pagination**: Memory-efficient processing in pages (default 1000 UNPs per page)
- **Rate limit handling**: Automatic retry with exponential backoff
- **Progress reporting**: Real-time progress updates during fetching
- **Compact storage**: Raw API data without field duplication saves ~50% disk space
- **~5x faster** than sequential processing (balanced performance)

## File Naming Convention

Files are named as: `grp_taxpayers_{timestamp}.json`

Where timestamp is in `YYYYMMDD_HHMMSS` format.

## JSON Structure

Each JSON file contains an array of taxpayer records with **raw API data** (no field duplication):

```json
[
  {
    "unp": 123456789,
    "vunp": "123456789",
    "vnaimp": "Название организации",
    "vnaimk": "Краткое название",
    "dreg": "2020-01-15",
    "nmns": "123",
    "vmns": "Инспекция МНС по району",
    "ckodsost": "1",
    "dlikv": "2020-01-15",
    "vpadres": "Адрес организации"
    // ... all other raw fields from GRP API
  }
]
```

**Note:** Data is stored in raw format to save space. Field parsing happens in the application layer.

## ⚠️ Troubleshooting

### Common Issues:

- **ConnectTimeout**: GRP API may be blocked outside Belarus. Use VPN.
- **429 Rate Limit**: Too many concurrent requests. System automatically handles retries.
- **Empty responses**: UNP may not exist in GRP database.
- **Parallel processing**: If rate limits are hit, consider reducing concurrency in code.

## Scripts Reference

### Main Scripts:
- `fetch-grp-to-json.py` - Load GRP data from database UNPs to JSON (with pagination)
- `fetch-grp-from-ngrn-list.py` - Load GRP data from ngrm_list.txt file to JSON (with pagination)
- `load_grp_json.py` - Load GRP data from JSON to database

### Utility Scripts:
- `check-unps.py` - Check database state and available UNPs

## Quick Start

1. **Check available data:**
   ```bash
   docker-compose exec egr-api python scripts/check-unps.py
   ```

2. **Load GRP data for companies (with pagination):**
   ```bash
   # From database UNPs
   docker-compose exec egr-api python scripts/fetch-grp-to-json.py

   # From ngrm_list.txt file
   docker-compose exec egr-api python scripts/fetch-grp-from-ngrn-list.py
   ```

3. **Load JSON into database:**
   ```bash
   docker-compose exec egr-api python scripts/load_grp_json.py --sync
   ```

## Pagination Details

- **Page size**: Configurable (1000-2000 UNPs per page)
- **Memory efficient**: Only current page loaded in memory at once
- **Progress tracking**: Shows page-by-page progress with success/error counts
- **Parallel processing**: Up to 6 concurrent requests per page
- **Rate limiting**: Automatic retry with exponential backoff
- **Resume capability**: Can restart from any page if interrupted

### From ngrm_list.txt Processing:
- **File reading**: Processes ngrm_list.txt line by line
- **Page calculation**: `(total_UNPs + page_size - 1) // page_size`
- **Batch processing**: Each page processed as independent unit
- **Error isolation**: Page errors don't stop entire process

## Troubleshooting Guide

### Problem: "ConnectTimeout" or connection errors

**Cause:** GRP API may be blocked outside Belarus
**Solution:**
- Use VPN with Belarusian IP
- Check if EGR API works (it should if you're in Belarus)
- Try from different network

### Problem: "429 Rate limit exceeded"

**Cause:** Too many requests to API
**Solution:**
- Wait 5-10 minutes
- System automatically handles retries with delays
- Reduce batch size in scripts

### Problem: Empty responses or "UNP not found"

**Cause:** UNP doesn't exist in GRP database
**Solution:**
- Try different UNP
- Some companies may not have taxpayer data
- Check available UNPs with `python scripts/check-unps.py`

### Problem: "No module named 'app'"

**Cause:** Running outside Docker environment
**Solution:**
- Use Docker: `docker-compose exec egr-api python scripts/...`
- Or set up virtual environment with proper PYTHONPATH

### Problem: All APIs work but GRP doesn't

**Cause:** GRP API specific issues
**Solution:**
- Check GRP API documentation for changes
- Try different UNP
- API may have temporary issues

```json
[
  {
    "unp": 123456789,
    "full_name": "Название организации",
    "short_name": "Краткое название",
    "registration_date": "2020-01-15",
    "inspectorate_code": "123",
    "inspectorate_name": "Инспекция МНС по району",
    "status_code": "1",
    "status_date": "2020-01-15",
    "address": "Адрес организации"
  }
]
```

## Usage

These JSON files are created by the `fetch-grp-to-json.py` script and can be loaded into the database using `load_grp_json.py`.