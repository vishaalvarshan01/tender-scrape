# Scrapy settings for the puducherry_tenders project.
#
# Only the settings that matter for this scraper are listed here. For the full
# list of available settings see:
#     https://docs.scrapy.org/en/latest/topics/settings.html

BOT_NAME = "puducherry_tenders"

SPIDER_MODULES = ["puducherry_tenders.spiders"]
NEWSPIDER_MODULE = "puducherry_tenders.spiders"

# Identify the crawler with a browser-like User-Agent. The Puducherry NIC portal
# serves its public tender pages over plain HTTP(S); a realistic UA avoids being
# treated as an unknown bot.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Obey robots.txt rules (the portal currently publishes no robots.txt, so this
# is effectively "allow all" but stays polite if that changes).
ROBOTSTXT_OBEY = True

# Be polite: one request at a time with a small delay between requests.
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1

# Retry transient failures (the portal can be flaky under load).
RETRY_ENABLED = True
RETRY_TIMES = 3

# Encode exported feeds as UTF-8 so tender text with non-ASCII characters
# (currency symbols, regional names) is preserved.
FEED_EXPORT_ENCODING = "utf-8"
