
# PromptVerse V2 — Flask + SQLite

A responsive prompt-sharing platform built with Flask and SQLite.

## Features

- Flask + SQLite persistent prompt database
- Admin-only prompt publishing
- Newest-first prompt ordering
- URL and local image uploads
- Smart search across title, prompt, category, model, and tags
- Multiple tags
- Views, likes, saves, and copies
- Database-backed user likes and saves
- My Library: saved, liked, and recently viewed prompts
- Smart trending score with recency decay
- Automatic 4.5-second trending rotation
- Manual Featured and Trending controls
- NEW and HOT badges
- Related prompts
- Shareable `/prompt/<id>` URLs
- Fullscreen image preview
- Image download
- Admin analytics metrics
- Admin prompt management
- Admin category management
- User enable/disable controls
- Duplicate prompt detection
- Activity logs
- Forgot-password demo flow
- Mobile bottom navigation
- Responsive dark UI

## Requirements

- Python 3.10 or newer
- pip

## Installation

Open Windows PowerShell in the project folder.

### 1. Create a virtual environment

```powershell
python -m venv venv
```

### 2. Activate the virtual environment

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Run the application

```powershell
python app.py
```

Open the application:

http://127.0.0.1:5000

## Admin Login

Admin login page:

http://127.0.0.1:5000/admin/login

The default credentials below are for the demo only, if configured by the application:

- Email: `admin@promptverse.local`
- Password: `Admin@12345`

For production, configure a strong `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` through environment variables. Do not publish real passwords or secrets in the repository.

## Database

The application uses SQLite for persistent prompt and application data. Ensure the database directory is writable by the application.

## Security Notes

- Change demo admin credentials before deployment.
- Keep `.env` and other secret configuration files out of Git.
- Use secure password hashing and session settings.
- Configure real email delivery for password-reset functionality.
- Use HTTPS in production.

## GitHub

Repository: `https://github.com/azizumatiya/promptcopy`

## License

Add a license before distributing this project publicly.
