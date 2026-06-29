# JRP Scores Backup

Backup archive and update script for PDF scores from the Josquin Research Project.

This repository stores downloaded score PDFs, organized by composer/work prefix, together with a small Python scraper that refreshes the archive from current JRP metadata.

## Contents

- `scores/` - archived score PDFs, grouped by composer code
- `script/JRP_scraper.py` - downloader/update script
- `works_cache.json` - cached JRP work metadata
- `missing_or_failed.txt` - paths that failed during the most recent run
- `pdf_scraper.log` / `script/*.log` - scraper logs

The current archive contains about 2,780 PDF files across 23 composer-code folders.
