
# PromptVerse V3 — Flask + MongoDB Atlas

This version uses MongoDB instead of SQLite.

## 1. Install

PowerShell:

    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt

## 2. MongoDB Atlas

Create a MongoDB Atlas cluster, create a database user, and allow your IP address in Network Access.

Set the connection string in PowerShell:

    $env:MONGO_URI="mongodb+srv://USERNAME:PASSWORD@YOUR-CLUSTER.mongodb.net/?retryWrites=true&w=majority"

Optional:

    $env:MONGO_DB="promptverse"
    $env:SECRET_KEY="replace-with-a-long-random-secret"
    $env:ADMIN_EMAIL="admin@example.com"
    $env:ADMIN_PASSWORD="ChangeThisStrongPassword123!"

Important: if your MongoDB password contains characters such as @, :, /, ?, #, or %, URL-encode the password in the connection string.

## 3. Run

    python app.py

Open:

    http://127.0.0.1:5000

Admin:

    http://127.0.0.1:5000/admin/login

## What is stored in MongoDB

Collections:
- users
- prompts
- likes
- saves
- views
- copy_events
- activity_logs
- categories
- password_resets

New prompts are inserted with the current UTC timestamp and therefore appear first under Newest.

Likes and saves are linked to the logged-in user's MongoDB ObjectId, so every user's library remains separate.

## Image storage

Admin can provide an image URL or upload a local image. Uploaded files are stored in static/uploads. For production, use object storage such as S3/Cloudinary instead of local disk.

## Password reset

The included reset flow is a development/demo flow that displays a reset link on screen. For production, connect an email provider and send the token by email.

## Security

Never commit MongoDB credentials to GitHub. Use environment variables. Change the default admin credentials before production.
