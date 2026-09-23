"""Many pages, politely: a site's map, read from its sitemaps.

``map_site`` lists a site's addresses from its sitemaps, and from the links on
its start page when it has none. Every request goes through robots.txt and the
address guard, is held to the byte bound, and waits its site's delay. Fetching
needs the ``fetch`` extra.
"""

from sluicer.crawl.sitemaps import SiteMap, SitemapRead, SiteUrl, map_site
from sluicer.crawl.urls import normalise, site_of
from sluicer.crawl.web import Web

__all__ = [
    "SiteMap",
    "SiteUrl",
    "SitemapRead",
    "Web",
    "map_site",
    "normalise",
    "site_of",
]
