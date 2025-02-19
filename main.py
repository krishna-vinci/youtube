import feedparser
from datetime import datetime, timedelta
from dateutil import parser as date_parser

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

DEFAULT_THUMBNAIL = "/static/default-thumbnail.jpg"

# Define RSS feed URLs for different trend sources with multiple channels
RSS_FEED_URLS = {
    "reddit": [
        {
            "name": "r/Indiaspeaks",
            "url": "http://192.168.0.122:3333/?action=display&bridge=RedditBridge&context=single&r=IndiaSpeaks&f=&score=50&d=hot&search=&frontend=https%3A%2F%2Fold.reddit.com&format=Atom"
        },
        {
            "name": "worldnews",
            "url": "http://192.168.0.122:3333/?action=display&bridge=RedditBridge&context=single&r=selfhosted&f=&score=&d=top&search=&frontend=https%3A%2F%2Fold.reddit.com&format=Atom"
        },
    ],
    "youtube": [
        {
            "name": "Prof K Nageshwar",
            "url": "http://192.168.0.122:3333/?action=display&bridge=YoutubeBridge&context=By+channel+id&c=UCm40kSg56qfys19NtzgXAAg&duration_min=2&duration_max=&format=Atom"
        },
        {
            "name": "Prasadtech",
            "url": "http://192.168.0.122:3333/?action=display&bridge=YoutubeBridge&context=By+channel+id&c=UCb-xXZ7ltTvrh9C6DgB9H-Q&duration_min=2&duration_max=&format=Atom"
        },
    ],
    "twitter": [
        {
            "name": "Twitter Feed",
            "url": "http://192.168.0.122:3333/?action=display&bridge=TwitterBridge&context=search&search=keyword&format=Atom"
        }
    ]
}


def format_datetime(dt_string):
    """Convert RSS datetime to a friendly format (Today, Yesterday, or full date)."""
    try:
        dt = date_parser.parse(dt_string)
        now = datetime.now(dt.tzinfo)
        yesterday = now - timedelta(days=1)
        if dt.date() == now.date():
            return dt.strftime("Today at %I:%M %p")
        elif dt.date() == yesterday.date():
            return dt.strftime("Yesterday at %I:%M %p")
        else:
            return dt.strftime("%b %d, %Y - %I:%M %p")
    except Exception:
        return "No Date"


def parse_rss_feed(rss_url: str):
    """Fetch and parse the RSS feed from the given URL."""
    feed = feedparser.parse(rss_url)
    items = []

    for entry in feed.entries:
        title = entry.title if hasattr(entry, "title") else "Untitled"
        link = entry.link if hasattr(entry, "link") else "#"
        description = getattr(entry, "summary", "No description available.")

        # Attempt to extract a thumbnail
        thumbnail_url = None
        if "media_thumbnail" in entry:
            thumbnail_url = entry.media_thumbnail[0].get("url")
        elif "media_content" in entry:
            thumbnail_url = entry.media_content[0].get("url")
        # Fallback: extract from <img> tag in description
        if not thumbnail_url and "<img" in description:
            start = description.find("<img")
            src_start = description.find('src="', start) + 5
            src_end = description.find('"', src_start)
            if src_start > 4 and src_end > src_start:
                thumbnail_url = description[src_start:src_end]

        if not thumbnail_url:
            thumbnail_url = DEFAULT_THUMBNAIL

        raw_published = getattr(entry, "published", "No date")
        published = format_datetime(raw_published)

        items.append({
            "title": title,
            "link": link,
            "description": description,
            "thumbnail": thumbnail_url,
            "published": published
        })
    return items


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/trends", response_class=HTMLResponse)
async def trends(request: Request, source: str = "reddit"):
    # Get the list of feeds for the provided source; fallback to Reddit if source not found
    feeds = RSS_FEED_URLS.get(source, RSS_FEED_URLS["reddit"])
    channels = []
    for feed in feeds:
        items = parse_rss_feed(feed["url"])
        channels.append({"name": feed["name"], "feed_items": items})
    return templates.TemplateResponse("trends.html", {"request": request, "source": source, "channels": channels})



@app.get("/feeds", response_class=HTMLResponse)
async def feeds(request: Request):
    # Placeholder for the Feeds page
    return templates.TemplateResponse("feeds.html", {"request": request})


@app.get("/projects", response_class=HTMLResponse)
async def projects(request: Request):
    # Placeholder for the Projects page
    return templates.TemplateResponse("projects.html", {"request": request})
