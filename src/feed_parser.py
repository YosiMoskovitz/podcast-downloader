
import requests
import xml.etree.ElementTree as ET
from dateutil import parser as dateparser
import logging

class PodcastFeedParser:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_latest_episodes(self, rss_url: str, max_episodes: int = 5):
        """Fetch RSS, parse with ElementTree, sort by parsed date, return latest N episodes (with audio)."""
        try:
            self.logger.info(f"Parsing feed: {rss_url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(rss_url, headers=headers, timeout=30)
            resp.raise_for_status()
            xml = resp.content.decode("utf-8", errors="replace")
            root = ET.fromstring(xml)
            channel = root.find("channel")
            items = channel.findall("item") if channel is not None else []
            eps = []
            for item in items:
                title = item.findtext("title", default="(no title)")
                pubdate = item.findtext("pubDate") or item.findtext("published") or item.findtext("date")
                parsed = None
                if pubdate:
                    try:
                        parsed = dateparser.parse(pubdate)
                    except Exception:
                        parsed = None
                # Find audio URL (enclosure)
                audio_url = None
                for enc in item.findall("enclosure"):
                    url = enc.attrib.get("url")
                    if url:
                        audio_url = url
                        break
                eps.append({
                    "title": title,
                    "published": pubdate,
                    "parsed": parsed,
                    "audio_url": audio_url
                })
            # Only keep those with valid date and audio_url
            eps = [e for e in eps if e["parsed"] and e["audio_url"]]
            eps.sort(key=lambda x: x["parsed"], reverse=True)
            return eps[:max_episodes]
        except Exception as e:
            self.logger.error(f"Error getting latest episodes from {rss_url}: {e}")
            return []
