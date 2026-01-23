#!/usr/bin/env python3
"""
Simple static site generator for Small Things Retro blog.
Generates a static site from markdown posts in content/posts/.
"""

import os
import re
import shutil
import yaml
import markdown
from datetime import datetime
from pathlib import Path
from html import escape

# Configuration
SITE_TITLE = "Small Things Retro"
SITE_BYLINE = "Retro gaming and computing experiments by nand2mario."
POSTS_PER_PAGE = 10
BASE_PATH = "/neo"  # URL prefix for the site (e.g., "/neo" or "" for root)

# Giscus comments (get these values from https://giscus.app/)
GISCUS_REPO = "nand2mario/nand2mario.github.io"
GISCUS_REPO_ID = "R_kgDOMuaEeg"  # Fill in from giscus.app
GISCUS_CATEGORY = "General"
GISCUS_CATEGORY_ID = "DIC_kwDOMuaEes4C1UwO"  # Fill in from giscus.app

# Directories
ROOT_DIR = Path(__file__).parent.parent
CONTENT_DIR = ROOT_DIR / "content" / "posts"
OUTPUT_DIR = ROOT_DIR / "public" / "neo"
TEMPLATES_DIR = ROOT_DIR / "bin" / "templates"


def parse_frontmatter(content):
    """Parse YAML frontmatter from markdown content."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = yaml.safe_load(parts[1])
            body = parts[2].strip()
            return frontmatter, body
    return {}, content


def get_excerpt(html_content, max_chars=300):
    """Extract excerpt from HTML content."""
    # Remove HTML tags for excerpt
    text = re.sub(r'<[^>]+>', '', html_content)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(' ', 1)[0] + '...'
    return text


def collect_posts():
    """Collect all posts from content/posts directory."""
    posts = []

    for year_dir in CONTENT_DIR.iterdir():
        if not year_dir.is_dir():
            continue

        # Check if it's a year directory or a post directory
        if year_dir.name.isdigit():
            # Year-based organization
            for post_dir in year_dir.iterdir():
                if post_dir.is_dir():
                    index_file = post_dir / "index.md"
                    if index_file.exists():
                        posts.append({
                            'path': post_dir,
                            'index_file': index_file,
                            'year': year_dir.name,
                            'slug': post_dir.name,
                            'url': f"/posts/{year_dir.name}/{post_dir.name}/"
                        })
        else:
            # Legacy posts without year
            if year_dir.is_dir():
                index_file = year_dir / "index.md"
                if index_file.exists():
                    posts.append({
                        'path': year_dir,
                        'index_file': index_file,
                        'year': None,
                        'slug': year_dir.name,
                        'url': f"/posts/{year_dir.name}/"
                    })

    # Parse frontmatter for each post
    for post in posts:
        with open(post['index_file'], 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)
        post['title'] = frontmatter.get('title', post['slug'])
        post['date'] = frontmatter.get('date')
        post['draft'] = frontmatter.get('draft', False)
        post['author'] = frontmatter.get('author', 'nand2mario')
        post['body'] = body

        # Parse date (normalize to naive datetime for comparison)
        if isinstance(post['date'], str):
            # Handle ISO format with timezone
            date_str = post['date'].split('T')[0]
            post['date_obj'] = datetime.strptime(date_str, '%Y-%m-%d')
        elif isinstance(post['date'], datetime):
            # Convert to naive datetime if timezone-aware
            if post['date'].tzinfo is not None:
                post['date_obj'] = post['date'].replace(tzinfo=None)
            else:
                post['date_obj'] = post['date']
        else:
            post['date_obj'] = datetime.now()

        post['date_formatted'] = post['date_obj'].strftime('%B %d, %Y')

    # Sort by date (newest first)
    posts.sort(key=lambda x: x['date_obj'], reverse=True)

    return posts


def render_markdown(content, post_url=""):
    """Convert markdown to HTML."""
    # Handle image references with optional attributes like {width="800"}
    # Convert relative image paths to proper URLs
    def fix_image_path(match):
        alt = match.group(1)
        src = match.group(2)
        # Keep relative paths as-is (they'll be relative to the post directory)
        return f'![{alt}]({src})'

    content = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)\s*\{[^}]*\}', fix_image_path, content)

    # Convert markdown to HTML
    md = markdown.Markdown(extensions=['fenced_code', 'tables', 'toc'])
    html = md.convert(content)

    return html


def load_template(name):
    """Load a template file."""
    template_file = TEMPLATES_DIR / f"{name}.html"
    with open(template_file, 'r', encoding='utf-8') as f:
        return f.read()


def render_template(template, **kwargs):
    """Simple template rendering with {{variable}} syntax."""
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


def generate_post_page(post, prev_post=None, next_post=None):
    """Generate HTML page for a single post."""
    # Render markdown content
    html_content = render_markdown(post['body'], post['url'])

    # Load templates
    base_template = load_template('base')
    post_template = load_template('post')

    # Generate prev/next navigation
    prev_link = ""
    next_link = ""
    if prev_post:
        prev_link = f'<a href="{BASE_PATH}{prev_post["url"]}" class="prev-post">← {escape(prev_post["title"])}</a>'
    if next_post:
        next_link = f'<a href="{BASE_PATH}{next_post["url"]}" class="next-post">{escape(next_post["title"])} →</a>'

    # Render post content
    post_html = render_template(
        post_template,
        title=escape(post['title']),
        date=post['date_formatted'],
        author=post['author'],
        content=html_content,
        prev_link=prev_link,
        next_link=next_link,
        giscus_repo=GISCUS_REPO,
        giscus_repo_id=GISCUS_REPO_ID,
        giscus_category=GISCUS_CATEGORY,
        giscus_category_id=GISCUS_CATEGORY_ID
    )

    # Render full page
    page_html = render_template(
        base_template,
        title=f"{post['title']} - {SITE_TITLE}",
        site_title=SITE_TITLE,
        site_byline=SITE_BYLINE,
        base_path=BASE_PATH,
        content=post_html,
        nav_home="",
        nav_projects="",
        nav_guides=""
    )

    return page_html


def generate_home_page(posts, page_num, total_pages):
    """Generate a home page with post listing."""
    base_template = load_template('base')
    home_template = load_template('home')

    # Generate post list HTML
    post_list_html = ""
    for post in posts:
        html_content = render_markdown(post['body'], post['url'])
        excerpt = get_excerpt(html_content)
        post_url = f"{BASE_PATH}{post['url']}"
        post_list_html += f'''
        <article class="post-preview">
            <h2><a href="{post_url}">{escape(post['title'])}</a></h2>
            <div class="post-meta">{post['date_formatted']}</div>
            <p>{excerpt}</p>
            <a href="{post_url}" class="read-more">Read more →</a>
        </article>
        '''

    # Generate pagination HTML
    pagination_html = '<nav class="pagination">'
    if page_num > 1:
        prev_url = f"{BASE_PATH}/" if page_num == 2 else f"{BASE_PATH}/page/{page_num - 1}/"
        pagination_html += f'<a href="{prev_url}" class="prev">← Newer</a>'
    else:
        pagination_html += '<span class="prev disabled">← Newer</span>'

    pagination_html += f'<span class="page-info">Page {page_num} of {total_pages}</span>'

    if page_num < total_pages:
        pagination_html += f'<a href="{BASE_PATH}/page/{page_num + 1}/" class="next">Older →</a>'
    else:
        pagination_html += '<span class="next disabled">Older →</span>'
    pagination_html += '</nav>'

    # Render home content
    home_html = render_template(
        home_template,
        post_list=post_list_html,
        pagination=pagination_html
    )

    # Render full page
    page_html = render_template(
        base_template,
        title=SITE_TITLE if page_num == 1 else f"Page {page_num} - {SITE_TITLE}",
        site_title=SITE_TITLE,
        site_byline=SITE_BYLINE,
        base_path=BASE_PATH,
        content=home_html,
        nav_home='class="active"',
        nav_projects="",
        nav_guides=""
    )

    return page_html


def generate_static_page(title, content_html, active_nav):
    """Generate a static page (Projects, Guides, etc.)."""
    base_template = load_template('base')
    page_template = load_template('page')

    page_content = render_template(
        page_template,
        title=title,
        content=content_html
    )

    nav_attrs = {"nav_home": "", "nav_projects": "", "nav_guides": ""}
    nav_attrs[active_nav] = 'class="active"'
    nav_attrs["base_path"] = BASE_PATH

    page_html = render_template(
        base_template,
        title=f"{title} - {SITE_TITLE}",
        site_title=SITE_TITLE,
        site_byline=SITE_BYLINE,
        content=page_content,
        **nav_attrs
    )

    return page_html


def copy_post_assets(post, output_dir):
    """Copy images and other assets from post directory."""
    for file in post['path'].iterdir():
        if file.name != 'index.md' and file.is_file():
            shutil.copy2(file, output_dir / file.name)


def build_site():
    """Build the complete static site."""
    print(f"Building site from {CONTENT_DIR}")

    # Clean output directory
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # Collect all posts (including drafts)
    all_posts = collect_posts()
    published_posts = [p for p in all_posts if not p['draft']]
    draft_posts = [p for p in all_posts if p['draft']]
    print(f"Found {len(published_posts)} published posts, {len(draft_posts)} drafts")

    # Generate post pages (for all posts, including drafts)
    for post in all_posts:
        # Create output directory for post
        post_output_dir = OUTPUT_DIR / post['url'].strip('/')
        post_output_dir.mkdir(parents=True, exist_ok=True)

        # Find prev/next posts (only among published posts)
        prev_post = None
        next_post = None
        if not post['draft']:
            idx = published_posts.index(post)
            # Posts are sorted newest first, so "prev" is newer (idx-1) and "next" is older (idx+1)
            if idx > 0:
                prev_post = published_posts[idx - 1]
            if idx < len(published_posts) - 1:
                next_post = published_posts[idx + 1]

        # Generate and write post HTML
        post_html = generate_post_page(post, prev_post, next_post)
        with open(post_output_dir / 'index.html', 'w', encoding='utf-8') as f:
            f.write(post_html)

        # Copy assets
        copy_post_assets(post, post_output_dir)
        print(f"  Generated: {post['url']}")

    # Generate home pages with pagination (only published posts)
    total_pages = (len(published_posts) + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE
    total_pages = max(1, total_pages)

    for page_num in range(1, total_pages + 1):
        start_idx = (page_num - 1) * POSTS_PER_PAGE
        end_idx = start_idx + POSTS_PER_PAGE
        page_posts = published_posts[start_idx:end_idx]

        home_html = generate_home_page(page_posts, page_num, total_pages)

        if page_num == 1:
            # First page is at root
            with open(OUTPUT_DIR / 'index.html', 'w', encoding='utf-8') as f:
                f.write(home_html)
            print(f"  Generated: / (home)")
        else:
            # Other pages in /page/N/
            page_dir = OUTPUT_DIR / 'page' / str(page_num)
            page_dir.mkdir(parents=True, exist_ok=True)
            with open(page_dir / 'index.html', 'w', encoding='utf-8') as f:
                f.write(home_html)
            print(f"  Generated: /page/{page_num}/")

    # Generate static pages
    projects_html = generate_static_page(
        "Projects",
        "<p>Projects coming soon.</p>",
        "nav_projects"
    )
    projects_dir = OUTPUT_DIR / 'projects'
    projects_dir.mkdir(parents=True, exist_ok=True)
    with open(projects_dir / 'index.html', 'w', encoding='utf-8') as f:
        f.write(projects_html)
    print("  Generated: /projects/")

    guides_html = generate_static_page(
        "Guides",
        "<p>Guides coming soon.</p>",
        "nav_guides"
    )
    guides_dir = OUTPUT_DIR / 'guides'
    guides_dir.mkdir(parents=True, exist_ok=True)
    with open(guides_dir / 'index.html', 'w', encoding='utf-8') as f:
        f.write(guides_html)
    print("  Generated: /guides/")

    # Copy CSS
    css_dir = OUTPUT_DIR / 'css'
    css_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATES_DIR / 'style.css', css_dir / 'style.css')
    print("  Copied: /css/style.css")

    print(f"\nSite generated successfully in {OUTPUT_DIR}")


if __name__ == '__main__':
    build_site()
