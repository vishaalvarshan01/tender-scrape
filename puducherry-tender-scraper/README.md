# Puducherry Tender Scraper

A self-contained [Scrapy](https://scrapy.org/) project that scrapes public tender
listings from the Puducherry e-Procurement portal
([pudutenders.gov.in](https://pudutenders.gov.in)) and exports them as structured
JSON.

The spider walks the portal in three stages:

1. **Organisations** &mdash; the "Tenders by Organisation" landing page.
2. **Tender listing** &mdash; the tenders published by each organisation.
3. **Tender detail** &mdash; each tender's detail page, from which ~60 fields are
   extracted (dates, fees, EMD, work description, TIA details, and more).

It uses plain HTTP requests only &mdash; **no browser/Playwright is required**.

## Requirements

- Python 3.9+
- The packages in [`requirements.txt`](./requirements.txt) (just Scrapy)

## Setup

```bash
# from the project root (the folder containing this README)
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

Run the spider and write the results to a JSON file with `-O` (overwrite) or
`-o` (append):

```bash
scrapy crawl puducherry_complete_tenders -O output/puducherry_tenders.json
```

> The `crawl` command must be run from the project root (the directory that
> contains `scrapy.cfg`).

Useful flags:

```bash
# Limit the run while testing (stop after 5 items)
scrapy crawl puducherry_complete_tenders -O output/sample.json -s CLOSESPIDER_ITEMCOUNT=5

# Increase or quieten logging
scrapy crawl puducherry_complete_tenders -O output/out.json -s LOG_LEVEL=DEBUG
```

## Output

Each record is a flat JSON object with a fixed schema. Example fields:

| Field | Description |
| ----- | ----------- |
| `state` | Always `"Puducherry"` |
| `organization_name` | Inviting organisation |
| `title` | Tender title |
| `tender_reference_number`, `tender_id` | Identifiers |
| `published_date`, `closing_date`, `bid_opening_date` | ISO 8601 timestamps |
| `tender_value`, `tender_fee`, `emd_amount` | Numeric financial fields |
| `work_description`, `location`, `pincode` | Work details |
| `tia_name`, `tia_address`, `pmt_instr_table` | Authority & payment info |

Fields that are not present on a given tender's page are returned as `null`.

## Project layout

```
puducherry-tender-scraper/
├── README.md
├── requirements.txt
├── scrapy.cfg
└── puducherry_tenders/
    ├── __init__.py
    ├── settings.py
    └── spiders/
        ├── __init__.py
        └── puducherry_complete.py   # spider name: puducherry_complete_tenders
```

## Notes

- Be courteous: the settings throttle to one request at a time with a 1-second
  delay. Please don't lower these against a government portal.
- The site occasionally changes its table layout; the spider matches fields by
  label text rather than fixed positions to stay resilient.
