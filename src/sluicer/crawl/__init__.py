"""Many pages, politely: a site's map, a crawl of its links, a list read in turn.

``map_site`` lists a site's addresses from its sitemaps, ``crawl`` follows its
links breadth first, and ``extract_many`` reads a list of addresses;
``sitemap_pages`` reads what the sitemaps list, and ``shopify_products`` a
Shopify shop's products from its ``/products.json``. Every page
goes through the fetch ladder -- robots.txt, the address guard, the byte bound
-- and every site is asked one request at a time, its delay between. Fetching
needs the ``fetch`` extra.
"""

from sluicer.crawl.pages import (
    Crawl,
    Page,
    PageError,
    Retry,
    StateMismatch,
    crawl,
    extract_many,
)
from sluicer.crawl.sitemaps import SiteMap, SitemapRead, SiteUrl, map_site
from sluicer.crawl.templates import shopify_products, sitemap_pages
from sluicer.crawl.urls import normalise, site_of
from sluicer.crawl.web import Web

__all__ = [
    "Crawl",
    "Page",
    "PageError",
    "Retry",
    "SiteMap",
    "SiteUrl",
    "SitemapRead",
    "StateMismatch",
    "Web",
    "crawl",
    "extract_many",
    "map_site",
    "normalise",
    "shopify_products",
    "site_of",
    "sitemap_pages",
]
