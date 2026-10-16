# PromptVerse V2 — Flask + SQLite

## Features
- Flask + SQLite persistent prompt database
- Admin-only prompt publishing
- Newest-first ordering
- URL/local image uploads
- Smart search across title, prompt, category, model and tags
- Multiple tags
- Views, likes, saves, copies
- Database-backed user likes/saves
- My Library: saved, liked, recently viewed
- Smart trending score with recency decay
- Automatic 4.5 second trending rotation
- Manual Featured/Trending controls
- NEW and HOT badges
- Related prompts
- Shareable `/prompt/<id>` URLs
- Fullscreen image preview
- Image download
- Admin analytics metrics
- Admin prompt management
- Admin category management
- User enable/disable
- Duplicate prompt detection
- Activity logs
- Forgot password demo flow
- Mobile bottom navigation
- Responsive dark UI

## Run

Windows PowerShell:

    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    python app.py

Open:

    http://127.0.0.1:5000

## Default admin

Email:
    admin@promptverse.local

Password:
    Admin@12345

Admin:
    http://127.0.0.1:5000/admin/login

For production, set SECRET_KEY, ADMIN_EMAIL and ADMIN_PASSWORD as environment variables and configure real email delivery for password resets.
