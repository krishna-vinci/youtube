import feedparser
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import os
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
from fastapi import Form
from fastapi.responses import RedirectResponse
import os
from fastapi import Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime
import markdown2
import os
from datetime import datetime

import markdown2
from fastapi import FastAPI, Request, Form, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import requests, os
from starlette.concurrency import run_in_threadpool
import logging

# Caching packages from fastapi-cache
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

import os
from datetime import datetime, timedelta

import feedparser
import requests
from dateutil import parser as date_parser
from fastapi import FastAPI, Request, Form, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from newspaper import Article
import markdown2
import os
from datetime import datetime
from fastapi import Form, HTTPException
from newspaper import Article
import html2text
import os
from dotenv import load_dotenv

load_dotenv()  # This will load variables from a .env file into the environment

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
if not PIXABAY_API_KEY:
    raise Exception("PIXABAY_API_KEY is not set in the environment.")



app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Initialize caching on startup (In production, consider using Redis or another backend)
@app.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")

DEFAULT_THUMBNAIL = "/static/default-thumbnail.jpg"

# RSS Feed URLs & Feed Categories
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


def format_datetime(dt_string):
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

# ------------------ Feeds Endpoints ------------------
@app.get("/feeds", response_class=HTMLResponse)
async def feeds(request: Request):
    categories = []
    for category_name, feeds in FEED_CATEGORIES.items():
        all_feed_items = []
        for feed in feeds:
            items = parse_rss_feed(feed["url"])
            all_feed_items.extend(items)
        categories.append({"category": category_name, "feed_items": all_feed_items})
    # Pass predefined_categories for use in the modal
    return templates.TemplateResponse("feeds.html", {
        "request": request,
        "categories": categories,
        "predefined_categories": PREDEFINED_CATEGORIES
    })

@app.get("/article-full-text")
async def article_full_text(url: str):
    try:
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
    if source == "twitter":
        # Skip RSS feed processing if using Twitter
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


# ------------------ Projects Endpoints ------------------

# Predefined categories and projects
PREDEFINED_CATEGORIES = ["SciTech", "Cooking", "Vlogs"]
PROJECTS_ROOT = "/Users/krishna/Desktop/YouTube/YouTube"



# ------------------ New Endpoint for Project Names ------------------
@app.get("/api/project_names", response_class=JSONResponse)
async def project_names(category: str):
    """
    Return a list of existing project names within the given category.
    """
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
    """
    Lists all categories (subfolders in PROJECTS_ROOT) and their projects,
    displaying only the project title and a preview (file listing).
    """
    projects_info = []
    if os.path.isdir(PROJECTS_ROOT):
        for category in os.listdir(PROJECTS_ROOT):
            cat_path = os.path.join(PROJECTS_ROOT, category)
            if os.path.isdir(cat_path):
                project_list = []
                for proj in os.listdir(cat_path):
                    proj_path = os.path.join(cat_path, proj)
                    if os.path.isdir(proj_path):
                        # Optionally, you can preview the MD file snippet if needed.
                        # For now, we only list the project name.
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
    """
    Creates a new project folder under the specified category, and initializes a .md file.
    """
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
    """
    Displays the project detail page, showing:
    - The project title.
    - A listing of files in the project folder.
    - (Optionally) an embedded MeTube iframe.
    - A button to launch Pixabay search (to download images/videos directly into this project).
    """
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

import os
from datetime import datetime
from fastapi import Form, HTTPException
from newspaper import Article
import html2text

@app.post("/api/add_to_project")
async def add_article_to_project(
    category: str = Form(...),
    project: str = Form(...),
    title: str = Form(...),
    link: str = Form(...),
    published: str = Form(...),
    description: str = Form(...)
):
    """
    Append an article's details + extracted Newspaper3k content (with images) 
    to the project's Markdown file.
    """
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

    # 1) Fetch the article HTML (including images) via Newspaper3k
    try:
        art = Article(link, keep_article_html=True)
        art.download()
        art.parse()
        # This gives us the article HTML
        content_html = art.article_html.strip() if art.article_html else ""
    except Exception as e:
        content_html = ""
        error_str = f"(Error extracting article HTML: {str(e)})"

    # 2) Convert HTML to Markdown (preserving images)
    if content_html:
        # Initialize html2text converter
        converter = html2text.HTML2Text()
        converter.ignore_images = False   # we want images
        converter.ignore_links = False    # preserve links
        converter.bypass_tables = False   # keep table structure if present
        converter.body_width = 0          # disable forced line wrapping

        try:
            full_markdown = converter.handle(content_html)
        except Exception as e:
            full_markdown = f"(Error converting HTML to Markdown: {str(e)})"
    else:
        # Fallback: if no HTML was extracted, fallback to Newspaper's plain text
        fallback_text = art.text.strip() if 'art' in locals() and art.text else ""
        if fallback_text:
            full_markdown = fallback_text
        else:
            full_markdown = error_str if 'error_str' in locals() else "(No article content found)"

    # 3) Prepare the Markdown snippet with images
    snippet = (
        f"\n## Article: {title}\n\n"
        f"**Link:** [{link}]({link})  \n"
        f"**Published:** {published}  \n"
        f"**Description:** {description}\n\n"
        f"### Content\n\n"
        f"{full_markdown}\n\n"
        f"---\n"
    )

    # 4) Append the snippet to the project's markdown file
    try:
        with open(md_file_path, "a", encoding="utf-8") as f:
            f.write(snippet)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error appending to Markdown file: {str(e)}")

    return {"status": "success", "message": "Article added to project with images"}




###pixsbay#############

# Cached helper function for Pixabay search (caches for 24 hours)
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
    page: int = 1  # Pagination parameter
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

# Helper function to write file content (offloaded to a thread)
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
    
    # Download file off-thread
    try:
        resp = await run_in_threadpool(requests.get, download_url, timeout=10)
        await run_in_threadpool(resp.raise_for_status)
        content = resp.content
        await run_in_threadpool(write_file, local_path, content)
    except Exception as e:
        logging.exception("Error downloading file")
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

    # If this is an HTMX request, return minimal HTML to update the UI
    if request.headers.get("HX-Request"):
        # Return a small snippet, for instance:
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
        # Fallback: if not HTMX, redirect to the pixabay page
        return RedirectResponse(
            url=f"/pixabay?category={category}&project={project}&downloaded={filename}",
            status_code=303
        )
