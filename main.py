import feedparser
from datetime import datetime, timedelta
from dateutil import parser as date_parser

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import feedparser
import requests
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from newspaper import Article  # from newspaper3k
from newspaper import fulltext
from newspaper import Article

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
            "url": "https://nitter.space/elonmusk/rss"
        }
    ]
}


FEED_CATEGORIES = {
    "Technology": [
        {
            "name": "TechCrunch",
            "url": "https://techcrunch.com/feed/"
        }
    ],
    "Science": [
        {
            "name": "New Scientist",
            "url": "https://feeds.newscientist.com/science-news"
        }
    ],
    "Hindu Sci and Tech": [
        {
            "name": "The Hindu Sci & Tech",
            "url": "https://www.thehindu.com/sci-tech/technology/?service=rss"
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
    import requests
    # Use a common browser User-Agent
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(rss_url, headers=headers, timeout=10)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    items = []
    for entry in feed.entries:
        title = getattr(entry, "title", "Untitled")
        link = getattr(entry, "link", "#")
        description = getattr(entry, "summary", "No description available.")
        thumbnail_url = None
        if "media_thumbnail" in entry:
            thumbnail_url = entry.media_thumbnail[0].get("url")
        elif "media_content" in entry:
            thumbnail_url = entry.media_content[0].get("url")
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


@app.get("/feeds", response_class=HTMLResponse)
async def feeds(request: Request):
    """
    Display categories of RSS feeds. 
    Each category has one or more feeds. 
    """
    categories = []
    for category_name, feeds in FEED_CATEGORIES.items():
        all_feed_items = []
        for feed in feeds:
            items = parse_rss_feed(feed["url"])
            all_feed_items.extend(items)
        categories.append({"category": category_name, "feed_items": all_feed_items})
    return templates.TemplateResponse("feeds.html", {"request": request, "categories": categories})

@app.get("/article-full-text")
async def article_full_text(url: str):
    """
    Fetch and return the article's body HTML with preserved semantic formatting,
    using Newspaper3k's keep_article_html=True option.
    """
    try:
        a = Article(url, keep_article_html=True)
        a.download()
        a.parse()
        # Try to get the extracted article body HTML.
        content_html = a.article_html.strip() if a.article_html else ""
        if not content_html:
            # Fallback: wrap plain text in <p> tags if extraction fails.
            content_html = "<p>" + a.text.replace("\n", "</p><p>") + "</p>"
        return JSONResponse({"content": content_html})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)



from newspaper import Article


@app.get("/article-full-html")
async def article_full_html(url: str):
    """
    Fetch and return the article's body HTML with preserved semantic formatting.
    This uses Newspaper3k's keep_article_html=True option.
    """
    try:
        # Instantiate Article with keep_article_html=True to retain just the article's body HTML.
        a = Article(url, keep_article_html=True)
        a.download()
        a.parse()
        # Try to get the extracted HTML of the article body.
        content_html = a.article_html.strip() if a.article_html else ""
        if not content_html:
            # Fallback: wrap the plain text in <p> tags, converting line breaks to paragraphs.
            content_html = "<p>" + a.text.replace("\n", "</p><p>") + "</p>"
        return JSONResponse({"html": content_html})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/feeds/column", response_class=HTMLResponse)
async def feeds_column(request: Request):
    """
    Render the split view: left side is a list of articles, right side displays the full content.
    """
    categories = []
    for category_name, feeds in FEED_CATEGORIES.items():
        all_feed_items = []
        for feed_info in feeds:
            items = parse_rss_feed(feed_info["url"])
            all_feed_items.extend(items)
        categories.append({"category": category_name, "feed_items": all_feed_items})
    
    return templates.TemplateResponse("feeds-split.html", {"request": request, "categories": categories})



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
    context = {"request": request, "source": source, "channels": channels}
    if source == "twitter":
        # Add the nitter URL for embedding via iframe (update this URL as needed)
        context["nitter_url"] = "https://nitter.space/"
        #context["nitter_url"] = "http://192.168.0.122:8080/"

    return templates.TemplateResponse("trends.html", context)


# Define feed categories with one feed each
FEED_CATEGORIES = {
    "Technology": [
        {
            "name": "TechCrunch",
            "url": "https://techcrunch.com/feed/"
        }
    ],
    "Science": [
        {
            "name": "New Scientist",
            "url": "https://feeds.newscientist.com/science-news"
        }
    ],
    "Hindu Sci and Tech": [
        {
            "name": "The Hindu Sci & Tech",
            "url": "https://www.thehindu.com/sci-tech/technology/?service=rss"
        }
    ]
}


@app.get("/projects", response_class=HTMLResponse)
async def projects(request: Request):
    # Placeholder for the Projects page
    return templates.TemplateResponse("projects.html", {"request": request})
