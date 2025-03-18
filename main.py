import os
import logging
import re
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import pytz

import feedparser
import requests
import markdown2
import html2text
from newspaper import Article, fulltext
from bs4 import BeautifulSoup  # For improved HTML pre-processing

from dotenv import load_dotenv

from fastapi import FastAPI, Request, Form, HTTPException, File, UploadFile, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()  # Load environment variables

# --- Global Configuration & Feed Variables ---
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
if not PIXABAY_API_KEY:
    raise Exception("PIXABAY_API_KEY is not set in the environment.")

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
            "url": "https://nitter.space"
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

PREDEFINED_CATEGORIES = ["SciTech", "Cooking", "Vlogs"]
PROJECTS_ROOT = "/Users/krishna/Desktop/YouTube/YouTube"
DEFAULT_THUMBNAIL = "/static/default-thumbnail.jpg"
DAILY_REPORT_DIR = os.getenv("DAILY_REPORT_DIR", '/Volumes/nfsdata/youtube/daily report')

# Indian Standard Time
IST = pytz.timezone("Asia/Kolkata")

# --- FastAPI App & Templates ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- Database Setup ---
def get_db_connection():
    return psycopg2.connect(
        dbname="trading_app",
        user="krishna",
        password="1122",
        host="192.168.0.114",
        port="5432"
    )

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # New schema with a content column.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS "YouTube-articles" (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        link TEXT UNIQUE NOT NULL,
        description TEXT,
        thumbnail TEXT,
        published TEXT,
        published_datetime TIMESTAMP,
        category TEXT,
        content TEXT
    );
    """)
    conn.commit()
    cur.close()
    conn.close()

# --- HTML to Markdown Conversion Helper ---
def convert_html_to_markdown(html_content: str) -> str:
    """
    Convert HTML content to Markdown.

    Pre-process the HTML to insert additional newline spacing for paragraphs
    and replace <br> tags with newlines. Then use html2text to convert the cleaned HTML
    to Markdown text. Finally, post-process the Markdown to collapse excessive newlines.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        # Insert newlines before and after <p> tags for proper paragraph spacing
        for p in soup.find_all('p'):
            p.insert_before("\n\n")
            p.append("\n\n")
        # Replace <br> tags with newline characters
        for br in soup.find_all('br'):
            br.replace_with("\n")
        cleaned_html = str(soup)
        
        converter = html2text.HTML2Text()
        converter.ignore_images = False
        converter.ignore_links = False
        converter.bypass_tables = False
        converter.body_width = 0  # Disable wrapping so newlines are preserved
        
        markdown_text = converter.handle(cleaned_html)
        # Remove trailing spaces on each line for cleaner output
        markdown_text = "\n".join(line.rstrip() for line in markdown_text.splitlines())
        # Collapse multiple newlines (3 or more) into exactly 2 newlines for paragraph separation
        markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)
        return markdown_text.strip()
    except Exception as e:
        logging.exception("Error converting HTML to Markdown: %s", e)
        # Fallback to the original HTML if conversion fails
        return html_content

# --- Scheduled Database Updates for Feeds ---
def format_datetime(dt_string):
    try:
        dt = date_parser.parse(dt_string)
        dt = dt.astimezone(IST)
        now = datetime.now(IST)
        yesterday = now - timedelta(days=1)
        if dt.date() == now.date():
            return dt.strftime("Today at %I:%M %p")
        elif dt.date() == yesterday.date():
            return dt.strftime("Yesterday at %I:%M %p")
        else:
            return dt.strftime("%b %d, %Y - %I:%M %p")
    except Exception:
        return "No Date"

def parse_and_store_rss_feed(rss_url: str, category: str):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(rss_url, headers=headers, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        conn = get_db_connection()
        cur = conn.cursor()
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
            raw_published = getattr(entry, "published", None)
            try:
                pub_dt = date_parser.parse(raw_published) if raw_published else None
            except Exception:
                pub_dt = None
            published_formatted = format_datetime(raw_published) if raw_published else "No date"
            
            # Check by title to skip duplicates (adjust if needed)
            cur.execute('SELECT id FROM "YouTube-articles" WHERE title = %s', (title,))
            if cur.fetchone() is not None:
                continue

            # Extract full article content using Newspaper3k and convert HTML to Markdown
            try:
                art = Article(link, keep_article_html=True)
                art.download()
                art.parse()
                if art.article_html:
                    article_md = convert_html_to_markdown(art.article_html)
                else:
                    article_md = art.text.strip()
            except Exception as e:
                logging.exception("Error extracting content for link %s: %s", link, e)
                article_md = None

            cur.execute(
                'INSERT INTO "YouTube-articles" (title, link, description, thumbnail, published, published_datetime, category, content) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (title, link, description, thumbnail_url, published_formatted, pub_dt, category, article_md)
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.exception("Error parsing/storing feed for URL %s: %s", rss_url, e)


def fetch_all_feeds_db():
    for category, feeds in FEED_CATEGORIES.items():
        for feed in feeds:
            parse_and_store_rss_feed(feed["url"], category)
    logging.info("Feed update (DB) completed at %s", datetime.now())

def get_articles_for_category_db(category: str, days: int = 2):
    threshold = datetime.now(IST) - timedelta(days=days)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'SELECT title, link, description, thumbnail, published, published_datetime, category, content FROM "YouTube-articles" WHERE category = %s AND published_datetime >= %s ORDER BY published_datetime DESC',
        (category, threshold)
    )
    rows = cur.fetchall()
    articles = []
    for row in rows:
        articles.append({
            "title": row[0],
            "link": row[1],
            "description": row[2],
            "thumbnail": row[3],
            "published": row[4],
            "published_datetime": row[5],
            "category": row[6],
            "content": row[7]
        })
    cur.close()
    conn.close()
    return articles

# --- Daily Report Endpoint Using Append Logic ---
@app.get("/daily-report-md", response_class=JSONResponse)
async def daily_report_md(timeframe: str = Query("last24", description="Options: last24, yesterday, week")):
    now = datetime.now(IST)
    if timeframe == "last24":
        start_time = now - timedelta(hours=24)
        end_time = now
        report_label = "24hrs"
    elif timeframe == "yesterday":
        yesterday_date = now.date() - timedelta(days=1)
        start_time = datetime.combine(yesterday_date, datetime.min.time()).astimezone(IST)
        end_time = datetime.combine(yesterday_date, datetime.max.time()).astimezone(IST)
        report_label = "yesterday"
    elif timeframe == "week":
        start_time = now - timedelta(days=7)
        end_time = now
        report_label = "week"
    else:
        return JSONResponse({"error": "Invalid timeframe option."}, status_code=400)
    
    # File name: daily_report_{label}_{YYYYMMDD}.md
    file_date = now.strftime('%Y%m%d')
    filename = f"daily_report_{report_label}_{file_date}.md"
    os.makedirs(DAILY_REPORT_DIR, exist_ok=True)
    file_path = os.path.join(DAILY_REPORT_DIR, filename)
    
    # Create the file with header if it doesn't exist
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# Daily Report ({report_label.capitalize()})\nGenerated on: {now.strftime('%b %d, %Y %I:%M %p')}\n\n")
    
    # Read current file content to avoid duplicates
    with open(file_path, "r", encoding="utf-8") as f:
        existing_content = f.read()
    
    conn = get_db_connection()
    cur = conn.cursor()
    report_appended = False
    for category in FEED_CATEGORIES.keys():
        cur.execute(
            'SELECT title, link, published, content, description FROM "YouTube-articles" WHERE category = %s AND published_datetime >= %s AND published_datetime <= %s ORDER BY published_datetime DESC',
            (category, start_time, end_time)
        )
        rows = cur.fetchall()
        if rows:
            category_header = f"\n## {category}\n"
            if category_header not in existing_content:
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(category_header)
                existing_content += category_header
            for row in rows:
                title, link, published, content, description = row
                # Skip if this link is already in the file
                if link in existing_content:
                    continue
                # Convert content from HTML to Markdown if needed
                if content and "<" in content:
                    try:
                        converted_content = convert_html_to_markdown(content)
                    except Exception as e:
                        converted_content = f"(Error converting content: {str(e)})"
                else:
                    converted_content = content if content else "(No content)"
                snippet = (
                    f"\n## Article: {title}\n\n"
                    f"**Link:** [{link}]({link})\n"
                    f"**Published:** {published}\n"
                    f"**Description:** {description}\n\n"
                    f"### Content\n\n"
                    f"{converted_content}\n\n"
                    f"---\n"
                )
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(snippet)
                existing_content += snippet
                report_appended = True
    cur.close()
    conn.close()
    
    message = "Report updated" if report_appended else "No new articles to append"
    return JSONResponse({"status": "success", "message": message, "file": filename})

# --- App Startup & Scheduler ---
scheduler = BackgroundScheduler()
@app.on_event("startup")
async def startup_event():
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
    init_db()
    # Immediately populate the database.
    fetch_all_feeds_db()
    # Schedule feed updates every 5 minutes.
    scheduler.add_job(fetch_all_feeds_db, 'interval', minutes=5)
    scheduler.start()

# --- Existing Feed Parsing for Trends (On-the-fly) ---
def parse_rss_feed(rss_url: str):
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

# --- Feeds Endpoints ---
@app.get("/feeds", response_class=HTMLResponse)
async def feeds(request: Request):
    categories_list = []
    for category in FEED_CATEGORIES.keys():
        articles = get_articles_for_category_db(category, days=2)
        categories_list.append({"category": category, "feed_items": articles})
    return templates.TemplateResponse("feeds.html", {
        "request": request,
        "categories": categories_list,
        "predefined_categories": PREDEFINED_CATEGORIES
    })

import markdown2

@app.get("/article-full-text")
async def article_full_text(url: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT content FROM "YouTube-articles" WHERE link = %s', (url,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            # row[0] is the stored Markdown
            rendered_html = markdown2.markdown(row[0])
            return JSONResponse({"content": rendered_html})
        else:
            # fallback to raw HTML from Newspaper3k if not in DB
            a = Article(url, keep_article_html=True)
            a.download()
            a.parse()
            content_html = a.article_html.strip() if a.article_html else ""
            if not content_html:
                content_html = "<p>" + a.text.replace("\n", "</p><p>") + "</p>"
            return JSONResponse({"content": content_html})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/article-full-html")
async def article_full_html(url: str):
    try:
        a = Article(url, keep_article_html=True)
        a.download()
        a.parse()
        content_html = a.article_html.strip() if a.article_html else ""
        if not content_html:
            content_html = "<p>" + a.text.replace("\n", "</p><p>") + "</p>"
        return JSONResponse({"html": content_html})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/feeds/column", response_class=HTMLResponse)
async def feeds_column(request: Request):
    categories_list = []
    for category in FEED_CATEGORIES.keys():
        articles = get_articles_for_category_db(category, days=2)
        categories_list.append({"category": category, "feed_items": articles})
    return templates.TemplateResponse("feeds-split.html", {"request": request, "categories": categories_list})

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/trends", response_class=HTMLResponse)
async def trends(request: Request, source: str = "reddit"):
    if source == "twitter":
        channels = []
    else:
        feeds = RSS_FEED_URLS.get(source, RSS_FEED_URLS["reddit"])
        channels = []
        for feed in feeds:
            items = parse_rss_feed(feed["url"])
            channels.append({"name": feed["name"], "feed_items": items})
    context = {"request": request, "source": source, "channels": channels}
    if source == "twitter":
        context["nitter_url"] = "https://nitter.net/"
    return templates.TemplateResponse("trends.html", context)

# --- Projects Endpoints ---
@app.get("/api/project_names", response_class=JSONResponse)
async def project_names(category: str):
    category_folder = os.path.join(PROJECTS_ROOT, category)
    projects = []
    if os.path.isdir(category_folder):
        for proj in os.listdir(category_folder):
            proj_path = os.path.join(category_folder, proj)
            if os.path.isdir(proj_path):
                projects.append(proj)
    return JSONResponse({"projects": projects})

@app.get("/projects", response_class=HTMLResponse)
async def projects_view(request: Request):
    projects_info = []
    if os.path.isdir(PROJECTS_ROOT):
        for category in os.listdir(PROJECTS_ROOT):
            cat_path = os.path.join(PROJECTS_ROOT, category)
            if os.path.isdir(cat_path):
                project_list = []
                for proj in os.listdir(cat_path):
                    proj_path = os.path.join(cat_path, proj)
                    if os.path.isdir(proj_path):
                        project_list.append({"project": proj})
                projects_info.append({"category": category, "projects": project_list})
    return templates.TemplateResponse("projects.html", {
        "request": request,
        "projects_info": projects_info,
        "predefined_categories": PREDEFINED_CATEGORIES
    })

@app.post("/projects/create")
async def create_project_endpoint(
    request: Request,
    category: str = Form(...),
    project_title: str = Form(...)
):
    category_folder = os.path.join(PROJECTS_ROOT, category)
    project_folder = os.path.join(category_folder, project_title)
    try:
        os.makedirs(project_folder, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating project folder: {str(e)}")
    
    md_file_path = os.path.join(project_folder, f"{project_title}.md")
    if not os.path.exists(md_file_path):
        try:
            with open(md_file_path, "w", encoding="utf-8") as f:
                f.write(f"# {project_title}\n\nCreated on: {datetime.now()}\n")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating Markdown file: {str(e)}")
    
    return RedirectResponse(f"/projects/{category}/{project_title}", status_code=303)

@app.get("/projects/{category}/{project}", response_class=HTMLResponse)
async def view_project_detail(request: Request, category: str, project: str):
    project_path = os.path.join(PROJECTS_ROOT, category, project)
    if not os.path.isdir(project_path):
        return HTMLResponse("Project not found", status_code=404)
    
    files_in_project = []
    for item in os.listdir(project_path):
        item_path = os.path.join(project_path, item)
        if os.path.isfile(item_path):
            files_in_project.append(item)
    
    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "category": category,
        "project": project,
        "files_in_project": files_in_project,
        "metube_url": "http://192.168.0.114:8081"
    })

@app.get("/projects/{category}/{project}/content", response_class=HTMLResponse)
async def project_content(category: str, project: str):
    project_path = os.path.join(PROJECTS_ROOT, category, project)
    md_path = os.path.join(project_path, f"{project}.md")
    if not os.path.exists(md_path):
        return HTMLResponse("Project not found", status_code=404)
    with open(md_path, "r", encoding="utf-8") as f:
        content_md = f.read()
    content_html = markdown2.markdown(content_md)
    return content_html

@app.post("/projects/{category}/{project}/upload-file")
async def upload_file(category: str, project: str, file: UploadFile = File(...)):
    project_path = os.path.join(PROJECTS_ROOT, category, project)
    if not os.path.isdir(project_path):
        raise HTTPException(status_code=404, detail="Project folder not found")
    file_path = os.path.join(project_path, file.filename)
    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    return {"status": "success", "filename": file.filename}

@app.post("/api/add_to_project")
async def add_article_to_project(
    category: str = Form(...),
    project: str = Form(...),
    title: str = Form(...),
    link: str = Form(...),
    published: str = Form(...),
    description: str = Form(...)
):
    project_folder = os.path.join(PROJECTS_ROOT, category, project)
    if not os.path.isdir(project_folder):
        raise HTTPException(status_code=404, detail="Project folder not found")

    md_file_path = os.path.join(project_folder, f"{project}.md")
    if not os.path.exists(md_file_path):
        try:
            with open(md_file_path, "w", encoding="utf-8") as f:
                f.write(f"# {project}\n\nCreated on: {datetime.now()}\n")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating Markdown file: {str(e)}")

    try:
        art = Article(link, keep_article_html=True)
        art.download()
        art.parse()
        content_html = art.article_html.strip() if art.article_html else ""
    except Exception as e:
        content_html = ""
        error_str = f"(Error extracting article HTML: {str(e)})"

    if content_html:
        full_markdown = convert_html_to_markdown(content_html)
    else:
        fallback_text = art.text.strip() if 'art' in locals() and art.text else ""
        full_markdown = fallback_text if fallback_text else error_str if 'error_str' in locals() else "(No article content found)"

    snippet = (
        f"\n## Article: {title}\n\n"
        f"**Link:** [{link}]({link})\n"
        f"**Published:** {published}\n"
        f"**Description:** {description}\n\n"
        f"### Content\n\n"
        f"{full_markdown}\n\n"
        f"---\n"
    )

    try:
        with open(md_file_path, "a", encoding="utf-8") as f:
            f.write(snippet)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error appending to Markdown file: {str(e)}")

    return {"status": "success", "message": "Article added to project with images"}

# --- Pixabay Endpoints ---
@cache(expire=86400)
async def get_pixabay_results(q: str, media_type: str, page: int):
    if media_type == "image":
        url = "https://pixabay.com/api/"
        params = {
            "key": PIXABAY_API_KEY,
            "q": q,
            "image_type": "photo",
            "per_page": 12,
            "page": page,
            "safesearch": "true"
        }
    else:
        url = "https://pixabay.com/api/videos/"
        params = {
            "key": PIXABAY_API_KEY,
            "q": q,
            "per_page": 12,
            "page": page,
            "safesearch": "true"
        }
    resp = await run_in_threadpool(requests.get, url, params=params, timeout=10)
    await run_in_threadpool(resp.raise_for_status)
    data = await run_in_threadpool(resp.json)
    return data.get("hits", [])

@app.get("/pixabay", response_class=HTMLResponse)
async def pixabay_search(
    request: Request,
    category: str,
    project: str,
    q: str = "",
    media_type: str = "image",
    page: int = 1
):
    results = []
    error_msg = ""
    if q.strip():
        try:
            results = await get_pixabay_results(q, media_type, page)
        except Exception as e:
            logging.exception("Error searching Pixabay")
            error_msg = f"Error searching Pixabay: {str(e)}"
    
    return templates.TemplateResponse("pixabay.html", {
        "request": request,
        "category": category,
        "project": project,
        "q": q,
        "media_type": media_type,
        "page": page,
        "results": results,
        "error_msg": error_msg
    })

def write_file(path, content):
    with open(path, "wb") as f:
        f.write(content)

@app.post("/pixabay/download")
async def pixabay_download(
    request: Request,
    category: str = Form(...),
    project: str = Form(...),
    download_url: str = Form(...),
    filename: str = Form(...)
):
    project_folder = os.path.join(PROJECTS_ROOT, category, project)
    if not os.path.isdir(project_folder):
        raise HTTPException(status_code=404, detail="Project folder not found")
    
    local_path = os.path.join(project_folder, filename)
    try:
        resp = await run_in_threadpool(requests.get, url=download_url, timeout=10)
        await run_in_threadpool(resp.raise_for_status)
        content = resp.content
        await run_in_threadpool(write_file, local_path, content)
    except Exception as e:
        logging.exception("Error downloading file")
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

    if request.headers.get("HX-Request"):
        return HTMLResponse(
            f"""
            <div class="alert alert-success shadow-lg mb-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current flex-shrink-0 h-6 w-6" 
                   fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                      d="M9 12l2 2 4-4" />
              </svg>
              <span>Saved <strong>{filename}</strong> to <strong>{category}/{project}</strong>.</span>
            </div>
            """,
            status_code=200
        )
    else:
        return RedirectResponse(
            url=f"/pixabay?category={category}&project={project}&downloaded={filename}",
            status_code=303
        )
