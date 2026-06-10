import sqlite3
import os
import json
import uuid
import time
import datetime
import hashlib
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
import threading
from flask_sock import Sock
app = Flask(__name__, template_folder='.', static_folder='static', static_url_path='/static')
app.secret_key = 'why-r-u-watching-my-secret'
DB_PATH = 'database.db'
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.1-8b-instant"
flint_memory = []

# Hardcoded SMTP Credentials (edit these to configure your SMTP settings)
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_EMAIL os.getenv("SMTP_EMAIL")
SMTP_PASSWORD =  os.getenv("SMTP_PASSWORD") # e.g., 'your-app-password'


sock = Sock(app)
connected_clients = {}
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def save_avatar_from_base64(base64_str):
    import base64
    import re
    if base64_str.startswith("data:image/"):
        match = re.match(r'^data:image/(\w+);base64,(.+)$', base64_str)
        if match:
            ext = match.group(1)
            img_data = base64.b64decode(match.group(2))
            filename = f"custom_{uuid.uuid4().hex}.{ext}"
            filepath = os.path.join("static", "avatars", filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(img_data)
            return f"/static/avatars/{filename}"
    return base64_str

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            country TEXT NOT NULL,
            timezone TEXT NOT NULL,
            avatar TEXT NOT NULL,
            is_confirmed INTEGER DEFAULT 0,
            confirmation_token TEXT,
            last_seen INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS git_branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            current_commit_hash TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS git_commits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash TEXT UNIQUE NOT NULL,
            branch_name TEXT NOT NULL,
            parent_hash TEXT,
            parent2_hash TEXT,
            message TEXT NOT NULL,
            author TEXT NOT NULL,
            tasks_snapshot TEXT NOT NULL,
            committed_at INTEGER NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS git_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_name TEXT NOT NULL,
            task_key TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL,
            assigned_to TEXT,
            updated_at INTEGER NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS smtp_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server TEXT NOT NULL DEFAULT 'smtp.gmail.com',
            port INTEGER NOT NULL DEFAULT 587,
            sender_email TEXT NOT NULL DEFAULT '',
            password TEXT NOT NULL DEFAULT ''
        )
    ''')
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            scheduled_at INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            reminder_sent INTEGER DEFAULT 0,
            status TEXT DEFAULT 'scheduled',
            created_at INTEGER NOT NULL
        )
    """)
    cursor.execute("SELECT id FROM git_branches WHERE name = 'main'")
    if not cursor.fetchone():
        
        cursor.execute("INSERT INTO git_branches (name, current_commit_hash) VALUES ('main', NULL)")
        
        
        cursor.execute("INSERT INTO smtp_config (server, port, sender_email, password) VALUES ('smtp.gmail.com', 587, '', '')")
        
        
        initial_tasks = {
            "task-1": {
                "title": "Setup Repository & GitSync Environment",
                "description": "Initialize the GitSync task board, setup Flask backend, and verify system components.",
                "status": "done",
                "assigned_to": "System Admin"
            },
            "task-2": {
                "title": "Design Glassmorphic UI Wireframes",
                "description": "Create modern UI designs with vibrant gradient overlays, smooth animations, and dark theme support.",
                "status": "in_progress",
                "assigned_to": "UI Designer"
            },
            "task-3": {
                "title": "Setup SMTP verification flow",
                "description": "Configure Google SMTP credentials and test the registration verification email.",
                "status": "todo",
                "assigned_to": "Backend Developer"
            }
        }

        snapshot_str = json.dumps(initial_tasks)
        init_hash = hashlib.sha1(f"initial-commit-{datetime.datetime.now().isoformat()}".encode()).hexdigest()
        
        
        epoch_now = int(time.time())
        cursor.execute('''
            INSERT INTO git_commits (hash, branch_name, parent_hash, message, author, tasks_snapshot, committed_at)
            VALUES (?, 'main', NULL, 'Initial commit: Setup project tasks and environment', 'System', ?, ?)
        ''', (init_hash, snapshot_str, epoch_now))
        
        cursor.execute("UPDATE git_branches SET current_commit_hash = ? WHERE name = 'main'", (init_hash,))
        
        for task_key, task in initial_tasks.items():
            cursor.execute('''
                INSERT INTO git_tasks (branch_name, task_key, title, description, status, assigned_to, updated_at)
                VALUES ('main', ?, ?, ?, ?, ?, ?)
            ''', (
                task_key,
                task['title'],
                task['description'],
                task['status'],
                task['assigned_to'],
                epoch_now
            ))

    cursor.execute(
        "SELECT id FROM users WHERE username = ?",
        ("FLINT",)
    )

    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (
                username,
                email,
                password_hash,
                country,
                timezone,
                avatar,
                is_confirmed,
                confirmation_token,
                last_seen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "FLINT",
            "flint@gitsync.local",
            "flint-ai",
            "India",
            "UTC",
            "/static/avatars/flint.png",
            1,
            None,
            int(time.time())
        ))

    conn.commit()
    conn.close()


init_db()


COUNTRY_TIMEZONES = {
    "USA": "America/New_York",
    "India": "Asia/Kolkata",
    "United Kingdom": "Europe/London",
    "Japan": "Asia/Tokyo",
    "France": "Europe/Paris",
    "Germany": "Europe/Berlin",
    "Canada": "America/Toronto",
    "Australia": "Australia/Sydney",
    "Brazil": "America/Sao_Paulo",
    "Singapore": "Asia/Singapore",
    "Uzbekistan": "Asia/Tashkent",
    "Philippines": "Asia/Manila",
    "Vietnam": "Asia/Ho_Chi_Minh",
    "Thailand": "Asia/Bangkok",
    "Indonesia": "Asia/Jakarta",
    "Malaysia": "Asia/Kuala_Lumpur",
    "Egypt": "Africa/Cairo",
    "Nigeria": "Africa/Lagos",
    "Kenya": "Africa/Nairobi"
}


def broadcast_live_event(event_type, data=None):
    payload = json.dumps({"type": event_type, "data": data})
    disconnected = []
    for ws in list(connected_clients.keys()):
        try:
            ws.send(payload)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        connected_clients.pop(ws, None)

def broadcast_chat_message(message_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.message, c.created_at, u.username, u.avatar, u.country
            FROM chat_messages c
            JOIN users u ON c.user_id = u.id
            WHERE c.id = ?
        ''', (message_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            msg_data = dict(row)
            broadcast_live_event("chat_message", msg_data)
    except Exception as e:
        print("Error broadcasting message:", e)

def flint_system_message(text):
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE username=?",
            ("FLINT",)
        )

        flint = cursor.fetchone()

        if not flint:
            conn.close()
            return

        cursor.execute("""
            INSERT INTO chat_messages
            (user_id, message, created_at)
            VALUES (?, ?, ?)
        """, (
            flint["id"],
            text,
            int(time.time())
        ))
        msg_id = cursor.lastrowid
        conn.commit()
        conn.close()

        broadcast_chat_message(msg_id)

    except Exception as e:
        print("FLINT system message error:", e)
def create_meeting(title, scheduled_at, created_by):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO meetings
        (title, scheduled_at, created_by, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        title,
        scheduled_at,
        created_by,
        int(time.time())
    ))

    conn.commit()
    conn.close()
def cancel_next_meeting():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id,title
        FROM meetings
        WHERE scheduled_at > ?
        ORDER BY scheduled_at ASC
        LIMIT 1
    """, (
        int(time.time()),
    ))

    meeting = cursor.fetchone()

    if not meeting:
        conn.close()
        return None

    cursor.execute(
        "DELETE FROM meetings WHERE id=?",
        (meeting["id"],)
    )

    conn.commit()
    conn.close()

    return meeting["title"]
def send_meeting_email(subject, body):
    smtp_server = SMTP_SERVER
    smtp_port = SMTP_PORT
    smtp_email = SMTP_EMAIL
    smtp_password = SMTP_PASSWORD

    conn = get_db()
    cursor = conn.cursor()

    if not smtp_email or not smtp_password:
        cursor.execute("SELECT server, port, sender_email, password FROM smtp_config LIMIT 1")
        row = cursor.fetchone()
        if row:
            smtp_server = row['server']
            smtp_port = row['port']
            smtp_email = row['sender_email']
            smtp_password = row['password']

    cursor.execute("""
        SELECT email
        FROM users
        WHERE is_confirmed=1
    """)

    users = cursor.fetchall()
    conn.close()

    if not smtp_email or not smtp_password:
        return

    import smtplib
    from email.mime.text import MIMEText

    try:
        server = smtplib.SMTP(
            smtp_server,
            int(smtp_port)
        )

        server.starttls()
        server.login(
            smtp_email,
            smtp_password
        )

        for user in users:
            msg = MIMEText(body)

            msg["Subject"] = subject
            msg["From"] = smtp_email
            msg["To"] = user["email"]

            server.sendmail(
                smtp_email,
                user["email"],
                msg.as_string()
            )

        server.quit()

    except Exception as e:
        print("Meeting Email Error:", e)
def check_meetings():

    now = int(time.time())

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM meetings
        WHERE reminder_sent=0
        AND status='scheduled'
    """)

    meetings = cursor.fetchall()

    for meeting in meetings:

        meeting_time = meeting["scheduled_at"]

        reminder_time = meeting_time - (30 * 60)

        if now >= reminder_time:

            dt = datetime.datetime.utcfromtimestamp(
                meeting_time
            )

            body = f"""
Upcoming Team Meeting

Title:
{meeting['title']}

Time:
{dt.strftime('%Y-%m-%d %H:%M UTC')}

Please join the GitSync dashboard.
"""

            send_meeting_email(
                "Upcoming Team Meeting",
                body
            )

            cursor.execute("""
                UPDATE meetings
                SET reminder_sent=1
                WHERE id=?
            """, (
                meeting["id"],
            ))

            flint_system_message(
                f"📨 Meeting reminder sent for "
                f"{meeting['title']}"
            )

    conn.commit()
    conn.close()
def meeting_worker():

    while True:

        try:
            check_meetings()

        except Exception as e:
            print(
                "Meeting Worker:",
                e
            )

        time.sleep(60)
def find_common_ancestor(db, branch_a, branch_b):
    cursor = db.cursor()
    
    
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (branch_a,))
    row_a = cursor.fetchone()
    commit_a = row_a[0] if row_a else None
    
    
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (branch_b,))
    row_b = cursor.fetchone()
    commit_b = row_b[0] if row_b else None
    
    if not commit_a or not commit_b:
        return None
        
    def get_ancestors(commit_hash):
        ancestors = []
        queue = [commit_hash]
        visited = set()
        while queue:
            curr = queue.pop(0)
            if curr in visited or not curr:
                continue
            visited.add(curr)
            ancestors.append(curr)
            
            cursor.execute("SELECT parent_hash, parent2_hash FROM git_commits WHERE hash = ?", (curr,))
            row = cursor.fetchone()
            if row:
                if row['parent_hash']:
                    queue.append(row['parent_hash'])
                if row['parent2_hash']:
                    queue.append(row['parent2_hash'])
        return ancestors

    ancestors_a = get_ancestors(commit_a)
    ancestors_b = set(get_ancestors(commit_b))
    
    for ancestor in ancestors_a:
        if ancestor in ancestors_b:
            return ancestor
            
    return None

def three_way_merge(base_snapshot, target_snapshot, source_snapshot):
    all_keys = set(base_snapshot.keys()) | set(target_snapshot.keys()) | set(source_snapshot.keys())
    
    merged = {}
    conflicts = {}
    
    for key in all_keys:
        in_base = key in base_snapshot
        in_target = key in target_snapshot
        in_source = key in source_snapshot
        
        base_val = base_snapshot.get(key)
        target_val = target_snapshot.get(key)
        source_val = source_snapshot.get(key)
        
        target_changed = target_val != base_val if in_base else in_target
        source_changed = source_val != base_val if in_base else in_source
        
        if not target_changed and not source_changed:
            if in_base:
                merged[key] = base_val
        elif target_changed and not source_changed:
            if in_target:
                merged[key] = target_val
        elif source_changed and not target_changed:
            if in_source:
                merged[key] = source_val
        else:
            if target_val == source_val:
                if in_target:
                    merged[key] = target_val
            else:
                conflicts[key] = {
                    "base": base_val,
                    "ours": target_val,
                    "theirs": source_val
                }
                
    return merged, conflicts

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    country = data.get('country')
    avatar = data.get('avatar')
    if avatar and avatar.startswith("data:image/"):
        avatar = save_avatar_from_base64(avatar)
        
    if not all([username, email, password, country, avatar]):
        return jsonify({"error": "All fields are required"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    
    cursor.execute("SELECT COUNT(id) FROM users")
    user_count = cursor.fetchone()[0]
    if user_count >= 7:
        conn.close()
        return jsonify({"error": "Team is full! Maximum of 6 members allowed."}), 400
        
    from werkzeug.security import generate_password_hash
    pwd_hash = generate_password_hash(password)
    
    tz = COUNTRY_TIMEZONES.get(country, "UTC")
    token = str(uuid.uuid4())
    
    try:
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, country, timezone, avatar, is_confirmed, confirmation_token, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0)
        ''', (username, email, pwd_hash, country, tz, avatar, token))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Nickname or Email already registered"}), 400
        
    smtp_server = SMTP_SERVER
    smtp_port = SMTP_PORT
    smtp_email = SMTP_EMAIL
    smtp_password = SMTP_PASSWORD

    if not smtp_email or not smtp_password:
        cursor.execute("SELECT server, port, sender_email, password FROM smtp_config LIMIT 1")
        smtp_row = cursor.fetchone()
        if smtp_row:
            smtp_server = smtp_row['server']
            smtp_port = smtp_row['port']
            smtp_email = smtp_row['sender_email']
            smtp_password = smtp_row['password']
    
    conn.close()
    
    confirm_url = f"{request.host_url}confirm/{token}"
    email_sent = False
    smtp_error = ""
    
    if smtp_email and smtp_password:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = smtp_email
            msg['To'] = email
            msg['Subject'] = "GitSync Dashboard - Confirm Your Registration"
            
            body = f"""Hello {username},

Welcome to the GitSync Team Dashboard!
To complete your registration and activate your account, please verify your email address by clicking the link below:

{confirm_url}

If you did not request this account, you can safely ignore this email.

Best regards,
GitSync Team
"""
            msg.attach(MIMEText(body, 'plain'))
            
            
            server = smtplib.SMTP(smtp_server, int(smtp_port), timeout=10)
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, email, msg.as_string())
            server.quit()
            
            email_sent = True
        except Exception as ex:
            smtp_error = str(ex)
            print(f"[SMTP ERROR] Failed to send email to {email}: {ex}")
            
    
    print(f"\n========================================================")
    print(f"[DEVELOPMENT FALLBACK] Account verification for {username}")
    print(f"Confirmation Link: {confirm_url}")
    print(f"========================================================\n")
    flint_system_message(
    f"🌿 Welcome {username}, welcome to the team"
    )
    return jsonify({
        "success": True,
        "email_sent": email_sent,
        "smtp_error": smtp_error,
        "confirm_url": confirm_url, 
        "message": "Registration successful! " + 
                   ("A verification email has been sent." if email_sent else "Verification email failed to send, but you can confirm using the developer link below.")
    })

@app.route('/confirm/<token>')
def confirm_email(token):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE confirmation_token = ?", (token,))
    row = cursor.fetchone()
    
    if row:
        user_id = row['id']
        cursor.execute("UPDATE users SET is_confirmed = 1, confirmation_token = NULL WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        
        return f"""
        <html>
            <head>
                <title>Email Confirmed</title>
                <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
                <style>
                    body {{
                        background: radial-gradient(circle at 50% 50%, #1e1e2f 0%, #11111b 100%);
                        color: #ffffff;
                        font-family: 'Outfit', sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                    }}
                    .card {{
                        background: rgba(30, 30, 45, 0.65);
                        backdrop-filter: blur(12px);
                        -webkit-backdrop-filter: blur(12px);
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 20px;
                        padding: 40px;
                        text-align: center;
                        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
                        max-width: 450px;
                        width: 90%;
                    }}
                    .checkmark-container {{
                        margin-bottom: 25px;
                    }}
                    .checkmark {{
                        width: 80px;
                        height: 80px;
                        border-radius: 50%;
                        display: block;
                        stroke-width: 3;
                        stroke: #10b981;
                        stroke-miterlimit: 10;
                        margin: 0 auto;
                        box-shadow: inset 0px 0px 0px rgba(16, 185, 129, 0.2);
                        animation: fill .4s ease-in-out .4s forwards, scale .3s ease-in-out 0s both;
                    }}
                    .checkmark__circle {{
                        stroke-dasharray: 166;
                        stroke-dashoffset: 166;
                        stroke-width: 3;
                        stroke-miterlimit: 10;
                        stroke: #10b981;
                        fill: none;
                        animation: stroke 0.6s cubic-bezier(0.65, 0, 0.45, 1) forwards;
                    }}
                    .checkmark__check {{
                        transform-origin: 50% 50%;
                        stroke-dasharray: 48;
                        stroke-dashoffset: 48;
                        animation: stroke 0.3s cubic-bezier(0.65, 0, 0.45, 1) 0.8s forwards;
                    }}
                    @keyframes stroke {{
                        100% {{ stroke-dashoffset: 0; }}
                    }}
                    @keyframes scale {{
                        0%, 100% {{ transform: none; }}
                        50% {{ transform: scale3d(1.1, 1.1, 1); }}
                    }}
                    @keyframes fill {{
                        100% {{ box-shadow: inset 0px 0px 0px 40px rgba(16, 185, 129, 0.1); }}
                    }}
                    h2 {{
                        margin-top: 0;
                        font-weight: 800;
                        font-size: 24px;
                        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                    }}
                    p {{
                        color: #94a3b8;
                        font-size: 16px;
                        line-height: 1.6;
                        margin-bottom: 30px;
                    }}
                    .btn {{
                        display: inline-block;
                        background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
                        color: white;
                        text-decoration: none;
                        padding: 14px 28px;
                        border-radius: 10px;
                        font-weight: 600;
                        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
                        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                    }}
                    .btn:hover {{
                        transform: translateY(-2px);
                        box-shadow: 0 8px 25px rgba(99, 102, 241, 0.6);
                    }}
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="checkmark-container">
                        <svg class="checkmark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52">
                            <circle class="checkmark__circle" cx="26" cy="26" r="25" fill="none"/>
                            <path class="checkmark__check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
                        </svg>
                    </div>
                    <h2>Account Verified!</h2>
                    <p>Congratulations, <strong>{row['username']}</strong>! Your email address has been successfully confirmed. You can now log in to the dashboard.</p>
                    <a href="/" class="btn">Return to Login</a>
                </div>
            </body>
        </html>
        """
    else:
        conn.close()
        return """
        <html>
            <head>
                <title>Invalid Token</title>
                <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600&display=swap" rel="stylesheet">
                <style>
                    body {
                        background: radial-gradient(circle at 50% 50%, #1e1e2f 0%, #11111b 100%);
                        color: #ffffff;
                        font-family: 'Outfit', sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                    }
                    .card {
                        background: rgba(30, 30, 45, 0.65);
                        backdrop-filter: blur(12px);
                        border: 1px solid rgba(239, 68, 68, 0.2);
                        border-radius: 20px;
                        padding: 40px;
                        text-align: center;
                        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
                        max-width: 450px;
                        width: 90%;
                    }
                    h2 { color: #ef4444; font-weight: 600; margin-top: 0; }
                    p { color: #94a3b8; line-height: 1.6; }
                    a { color: #6366f1; text-decoration: none; font-weight: 600; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h2>Verification Failed</h2>
                    <p>The verification link is invalid, expired, or has already been used.</p>
                    <a href="/">Return to Login</a>
                </div>
            </body>
        </html>
        """, 400

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Nickname and Password are required"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash, is_confirmed FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return jsonify({"error": "Invalid nickname or password"}), 400
        
    from werkzeug.security import check_password_hash
    if not check_password_hash(row['password_hash'], password):
        return jsonify({"error": "Invalid nickname or password"}), 400
        
    if not row['is_confirmed']:
        return jsonify({"error": "Account is not verified yet. Please confirm using the link sent to your email or printed in server terminal."}), 400
        
    session['user_id'] = row['id']
    session['current_branch'] = 'main'
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_seen = ? WHERE id = ?", (int(time.time()), row['id']))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True})

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('current_branch', None)
    return jsonify({"success": True})

@app.route('/api/me', methods=['GET'])
def get_me():
    if 'user_id' not in session:
        return jsonify({"user": None})
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, country, timezone, avatar, is_confirmed
        FROM users
        WHERE id = ?
    ''', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        session.pop('user_id', None)
        return jsonify({"user": None})
        
    return jsonify({
        "user": dict(user),
        "current_branch": session.get('current_branch', 'main')
    })

@app.route('/api/users', methods=['GET'])
def get_users():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, country, timezone, avatar, last_seen, is_confirmed
        FROM users
    ''')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    active_user_ids = set(connected_clients.values())
    now = int(time.time())
    for u in users:
        u['is_online'] = u['id'] in active_user_ids or (now - u['last_seen']) < 15
        
    return jsonify({"users": users})

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_seen = ? WHERE id = ?", (int(time.time()), session['user_id']))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True})

# --- Chat Endpoints ---

@app.route('/api/chat', methods=['GET'])
def chat_get():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.message, c.created_at, u.username, u.avatar, u.country
        FROM chat_messages c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.id ASC
        LIMIT 100
    ''')
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"messages": messages})
def process_and_broadcast_message(user_id, message):
    message = message.strip()
    if not message:
        return

    conn = get_db()
    cursor = conn.cursor()

    # Save user message
    cursor.execute("""
        INSERT INTO chat_messages
        (user_id, message, created_at)
        VALUES (?, ?, ?)
    """, (
        user_id,
        message,
        int(time.time())
    ))
    user_msg_id = cursor.lastrowid

    # ------------------------
    # FLINT COMMANDS
    # ------------------------
    flint_msg_id = None
    if message.lower().startswith("@flint"):
        prompt = message[6:].strip()
        flint_reply = None

        # ----------------------------------
        # Schedule Meeting
        # ----------------------------------
        if prompt.lower().startswith("schedule meeting"):
            try:
                date_text = prompt.replace("schedule meeting", "").strip()
                meeting_dt = datetime.datetime.strptime(date_text, "%Y-%m-%d %H:%M UTC")
                epoch = int(meeting_dt.timestamp())
                cursor.execute("""
                    INSERT INTO meetings (title, scheduled_at, created_by, status)
                    VALUES (?, ?, ?, ?)
                """, ("Team Meeting", epoch, user_id, "scheduled"))
                flint_reply = f"📅 Meeting scheduled for {meeting_dt.strftime('%Y-%m-%d %H:%M UTC')}"
            except Exception:
                flint_reply = "⚠️ Invalid format.\nUse:\n@flint schedule meeting 2026-06-15 22:00 UTC"

        # ----------------------------------
        # Cancel Meeting
        # ----------------------------------
        elif prompt.lower() == "meeting cancel":
            cursor.execute("""
                UPDATE meetings
                SET status='cancelled'
                WHERE status='scheduled'
            """)
            if cursor.rowcount > 0:
                flint_reply = "❌ Active meeting cancelled."
            else:
                flint_reply = "⚠️ No active meeting found."

        # ----------------------------------
        # Normal Flint AI
        # ----------------------------------
        else:
            flint_reply = ask_flint(prompt)

        # Save Flint message
        cursor.execute(
            "SELECT id FROM users WHERE username=?",
            ("FLINT",)
        )
        flint_user = cursor.fetchone()
        if flint_user and flint_reply:
            cursor.execute("""
                INSERT INTO chat_messages
                (user_id, message, created_at)
                VALUES (?, ?, ?)
            """, (
                flint_user["id"],
                flint_reply,
                int(time.time())
            ))
            flint_msg_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # Broadcast
    if user_msg_id:
        broadcast_chat_message(user_msg_id)
    if flint_msg_id:
        broadcast_chat_message(flint_msg_id)

@app.route('/api/chat', methods=['POST'])
def chat_post():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    message = data.get('message')

    if not message or not message.strip():
        return jsonify({"error": "Message required"}), 400

    process_and_broadcast_message(session['user_id'], message)
    return jsonify({"success": True})

@sock.route('/ws/live')
def live_ws(ws):
    if 'user_id' not in session:
        ws.close(1008)  # Policy Violation
        return
        
    user_id = session['user_id']
    connected_clients[ws] = user_id
    broadcast_live_event("presence_update")
    
    try:
        while True:
            data = ws.receive()
            if data is None:
                break
            try:
                msg_data = json.loads(data)
                message = msg_data.get('message')
                if message:
                    process_and_broadcast_message(user_id, message)
            except Exception as e:
                print("Error parsing ws message:", e)
    except Exception as e:
        print("WebSocket connection error:", e)
    finally:
        connected_clients.pop(ws, None)
        broadcast_live_event("presence_update")
@app.route('/api/meetings')
def get_meetings():

    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM meetings
        WHERE status='scheduled'
        ORDER BY scheduled_at ASC
    """)

    meetings = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        "meetings": meetings
    })

@app.route('/api/meetings', methods=['POST'])
def schedule_meeting():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json or {}
    title = data.get('title')
    scheduled_at_str = data.get('scheduled_at')
    
    if not title or not scheduled_at_str:
        return jsonify({"error": "Title and schedule date/time are required"}), 400
        
    try:
        if isinstance(scheduled_at_str, (int, float)):
            epoch = int(scheduled_at_str)
        else:
            meeting_dt = datetime.datetime.strptime(scheduled_at_str, "%Y-%m-%d %H:%M UTC")
            epoch = int(meeting_dt.timestamp())
    except Exception as e:
        return jsonify({"error": "Invalid date/time format. Use YYYY-MM-DD HH:MM UTC"}), 400
        
    if epoch <= int(time.time()):
        return jsonify({"error": "Meeting must be scheduled in the future"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO meetings (title, scheduled_at, created_by, status, created_at)
        VALUES (?, ?, ?, 'scheduled', ?)
    """, (title, epoch, session['user_id'], int(time.time())))
    meeting_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    flint_system_message(f"📅 A new meeting was scheduled: '{title}' at {scheduled_at_str if isinstance(scheduled_at_str, str) else datetime.datetime.utcfromtimestamp(epoch).strftime('%Y-%m-%d %H:%M UTC')}.")
    
    broadcast_live_event("meeting_update")
    return jsonify({"success": True, "meeting_id": meeting_id})

@app.route('/api/meetings/<int:meeting_id>', methods=['DELETE'])
def cancel_meeting_route(meeting_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT created_by, title FROM meetings WHERE id = ?", (meeting_id,))
    meeting = cursor.fetchone()
    
    if not meeting:
        conn.close()
        return jsonify({"error": "Meeting not found"}), 404
        
    if meeting['created_by'] != session['user_id']:
        conn.close()
        return jsonify({"error": "Only the creator of this meeting can cancel it"}), 403
        
    cursor.execute("UPDATE meetings SET status = 'cancelled' WHERE id = ?", (meeting_id,))
    conn.commit()
    conn.close()
    
    flint_system_message(f"❌ Meeting '{meeting['title']}' was cancelled by its creator.")
    
    broadcast_live_event("meeting_update")
    return jsonify({"success": True})

# --- Git / Kanban Endpoints ---

@app.route('/api/git/branches', methods=['GET'])
def git_get_branches():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, current_commit_hash FROM git_branches")
    branches = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"branches": branches})

@app.route('/api/git/branches', methods=['POST'])
def git_create_branch():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"error": "Branch name is required"}), 400
        

    name = name.strip().replace(' ', '-').replace('/', '-')
    
    conn = get_db()
    cursor = conn.cursor()
    
    
    cursor.execute("SELECT id FROM git_branches WHERE name = ?", (name,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": f"Branch '{name}' already exists."}), 400
        
    current_branch = session.get('current_branch', 'main')
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (current_branch,))
    current_commit = cursor.fetchone()[0]
    
    cursor.execute("INSERT INTO git_branches (name, current_commit_hash) VALUES (?, ?)", (name, current_commit))
    
    
    epoch_now = int(time.time())
    cursor.execute('''
        INSERT INTO git_tasks (branch_name, task_key, title, description, status, assigned_to, updated_at)
        SELECT ?, task_key, title, description, status, assigned_to, ?
        FROM git_tasks
        WHERE branch_name = ?
    ''', (name, epoch_now, current_branch))
    
    conn.commit()
    conn.close()
    flint_system_message(
    f"🌿 Branch '{name}' was created from '{current_branch}'."
    )
   
    session['current_branch'] = name
    
    broadcast_live_event("git_update")
    return jsonify({"success": True, "branch": name})

@app.route('/api/git/checkout', methods=['POST'])
def git_checkout():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    branch_name = data.get('branch')
    
    if not branch_name:
        return jsonify({"error": "Branch name required"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM git_branches WHERE name = ?", (branch_name,))
    branch = cursor.fetchone()
    conn.close()
    
    if not branch:
        return jsonify({"error": "Branch does not exist"}), 404
        
    session['current_branch'] = branch_name
    flint_system_message(
    f"🔀 Switched active branch to '{branch_name}'."
    )
    return jsonify({"success": True, "current_branch": branch_name})

@app.route('/api/git/tasks', methods=['GET'])
def git_get_tasks():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    branch = session.get('current_branch', 'main')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, task_key, title, description, status, assigned_to
        FROM git_tasks
        WHERE branch_name = ?
    ''', (branch,))
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"tasks": tasks, "branch": branch})

@app.route('/api/git/tasks', methods=['POST'])
def git_create_task():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    title = data.get('title')
    description = data.get('description', '')
    status = data.get('status', 'todo')
    assigned_to = data.get('assigned_to', '')
    
    if not title:
        return jsonify({"error": "Title required"}), 400
        
    branch = session.get('current_branch', 'main')
    task_key = f"task-{uuid.uuid4().hex[:8]}"
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO git_tasks (branch_name, task_key, title, description, status, assigned_to, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (branch, task_key, title, description, status, assigned_to, int(time.time())))
    conn.commit()
    conn.close()
    flint_system_message(
    f"📌 New task created on '{branch}': {title}"
    )
    broadcast_live_event("git_update")
    return jsonify({"success": True, "task_key": task_key})
def ask_flint(prompt):
    global flint_memory

    try:
        messages = [
            {
                "role": "system",
                "content": """
You are FLINT.

You are a member of the VORCINEX_STUDIO team.

Traits:
- Friendly
- Helpful
- Technically strong
- Concise
- Honest when unsure

You help with:
- Python
- Flask
- SQLite
- Git
- Web Development
- Debugging
- Planning features

YOCRRZ created you.

you are a active member of the team chat.
Respond naturally as a teammate.
Do not introduce yourself every message.
"""
            }
        ]

        # Add memory
        messages.extend(flint_memory)

        # Current message
        messages.append({
            "role": "user",
            "content": prompt
        })

        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": messages,
                "temperature": 0.7
            },
            timeout=30
        )

        if r.status_code != 200:
            return f"⚠️ Groq error {r.status_code}"

        data = r.json()

        answer = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "I couldn't generate a response.")
        )

        # Store memory
        flint_memory.append({
            "role": "user",
            "content": prompt
        })

        flint_memory.append({
            "role": "assistant",
            "content": answer
        })

        # Keep last 7 exchanges
        flint_memory = flint_memory[-14:]

        return answer

    except Exception as e:
        return f"FLINT error: {e}"
@app.route('/api/git/tasks/<task_key>', methods=['PUT'])
def git_update_task(task_key):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    title = data.get('title')
    description = data.get('description')
    status = data.get('status')
    assigned_to = data.get('assigned_to')
    
    branch = session.get('current_branch', 'main')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM git_tasks WHERE branch_name = ? AND task_key = ?", (branch, task_key))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Task not found on this branch"}), 404
        
    updates = []
    params = []
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if assigned_to is not None:
        updates.append("assigned_to = ?")
        params.append(assigned_to)
        
    if not updates:
        conn.close()
        return jsonify({"error": "No updates provided"}), 400
        
    updates.append("updated_at = ?")
    params.append(int(time.time()))
    params.extend([branch, task_key])
    
    query = f"UPDATE git_tasks SET {', '.join(updates)} WHERE branch_name = ? AND task_key = ?"
    cursor.execute(query, params)
    conn.commit()
    conn.close()
    flint_system_message(
    f"✏️ Task '{task_key}' was updated on branch '{branch}'."
    )
    broadcast_live_event("git_update")
    return jsonify({"success": True})

@app.route('/api/git/tasks/<task_key>', methods=['DELETE'])
def git_delete_task(task_key):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    branch = session.get('current_branch', 'main')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM git_tasks WHERE branch_name = ? AND task_key = ?", (branch, task_key))
    conn.commit()
    conn.close()
    flint_system_message(
    f"🗑️ Task '{task_key}' was removed from '{branch}'."
    )
    broadcast_live_event("git_update")
    return jsonify({"success": True})

@app.route('/api/git/status', methods=['GET'])
def git_get_status():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    branch = session.get('current_branch', 'main')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get latest commit snapshot
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (branch,))
    row = cursor.fetchone()
    latest_commit_hash = row[0] if row else None
    
    latest_snapshot = {}
    if latest_commit_hash:
        cursor.execute("SELECT tasks_snapshot FROM git_commits WHERE hash = ?", (latest_commit_hash,))
        commit_row = cursor.fetchone()
        if commit_row:
            latest_snapshot = json.loads(commit_row['tasks_snapshot'])
            
    # Get current working tree
    cursor.execute("SELECT task_key, title, description, status, assigned_to FROM git_tasks WHERE branch_name = ?", (branch,))
    working_tasks = {row['task_key']: dict(row) for row in cursor.fetchall()}
    conn.close()
    
    uncommitted = []
    
    # 1. Added or Modified
    for task_key, task in working_tasks.items():
        if task_key not in latest_snapshot:
            uncommitted.append({
                "task_key": task_key,
                "title": task['title'],
                "type": "added"
            })
        else:
            base_task = latest_snapshot[task_key]
            is_modified = (
                task['title'] != base_task.get('title') or
                task['description'] != base_task.get('description', '') or
                task['status'] != base_task.get('status') or
                task['assigned_to'] != base_task.get('assigned_to', '')
            )
            if is_modified:
                uncommitted.append({
                    "task_key": task_key,
                    "title": task['title'],
                    "type": "modified"
                })
                
    # 2. Deleted
    for task_key, base_task in latest_snapshot.items():
        if task_key not in working_tasks:
            uncommitted.append({
                "task_key": task_key,
                "title": base_task['title'],
                "type": "deleted"
            })
            
    return jsonify({
        "branch": branch,
        "latest_commit": latest_commit_hash,
        "uncommitted_changes": uncommitted
    })

@app.route('/api/git/commit', methods=['POST'])
def git_commit():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    message = data.get('message')
    if not message or not message.strip():
        return jsonify({"error": "Commit message is required"}), 400
        
    branch = session.get('current_branch', 'main')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT username FROM users WHERE id = ?", (session['user_id'],))
    user_row = cursor.fetchone()
    username = user_row['username'] if user_row else "Unknown"
    
    # Get current working tasks
    cursor.execute("SELECT task_key, title, description, status, assigned_to FROM git_tasks WHERE branch_name = ?", (branch,))
    working_tasks = {row['task_key']: {
        "title": row['title'],
        "description": row['description'],
        "status": row['status'],
        "assigned_to": row['assigned_to']
    } for row in cursor.fetchall()}
    
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (branch,))
    parent_row = cursor.fetchone()
    parent_hash = parent_row[0] if parent_row else None
    
    epoch_now = int(time.time())
    commit_data = f"{branch}-{parent_hash}-{message}-{json.dumps(working_tasks)}-{epoch_now}"
    commit_hash = hashlib.sha1(commit_data.encode()).hexdigest()
    
    cursor.execute('''
        INSERT INTO git_commits (hash, branch_name, parent_hash, message, author, tasks_snapshot, committed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (commit_hash, branch, parent_hash, message, username, json.dumps(working_tasks), epoch_now))
    
    cursor.execute("UPDATE git_branches SET current_commit_hash = ? WHERE name = ?", (commit_hash, branch))
    
    conn.commit()
    conn.close()
    flint_system_message(
    f"✅ {username} committed to '{branch}'\n"
    f"Message: {message}\n"
    f"Commit: {commit_hash[:8]}"
    )
    broadcast_live_event("git_update")
    return jsonify({"success": True, "commit_hash": commit_hash})

@app.route('/api/git/log', methods=['GET'])
def git_log():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    branch = session.get('current_branch', 'main')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (branch,))
    row = cursor.fetchone()
    commit_hash = row[0] if row else None
    
    commits = []
    visited = set()
    queue = [commit_hash] if commit_hash else []
    
    while queue:
        curr_hash = queue.pop(0)
        if curr_hash in visited or not curr_hash:
            continue
        visited.add(curr_hash)
        
        cursor.execute('''
            SELECT hash, branch_name, parent_hash, parent2_hash, message, author, committed_at
            FROM git_commits
            WHERE hash = ?
        ''', (curr_hash,))
        c_row = cursor.fetchone()
        if c_row:
            commits.append({
                "hash": c_row['hash'],
                "branch_name": c_row['branch_name'],
                "parent_hash": c_row['parent_hash'],
                "parent2_hash": c_row['parent2_hash'],
                "message": c_row['message'],
                "author": c_row['author'],
                "committed_at": c_row['committed_at']
            })
            if c_row['parent_hash']:
                queue.append(c_row['parent_hash'])
            if c_row['parent2_hash']:
                queue.append(c_row['parent2_hash'])
                
    conn.close()
    commits.sort(key=lambda x: x['committed_at'], reverse=True)
    return jsonify({"log": commits})

@app.route('/api/git/merge', methods=['POST'])
def git_merge():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    source_branch = data.get('source_branch')
    target_branch = session.get('current_branch', 'main')
    
    if not source_branch:
        return jsonify({"error": "Source branch required"}), 400
    if source_branch == target_branch:
        return jsonify({"error": "Cannot merge branch into itself"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if target branch has uncommitted changes
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (target_branch,))
    target_row = cursor.fetchone()
    target_commit = target_row[0] if target_row else None
    
    target_snapshot = {}
    if target_commit:
        cursor.execute("SELECT tasks_snapshot FROM git_commits WHERE hash = ?", (target_commit,))
        target_snap_row = cursor.fetchone()
        if target_snap_row:
            target_snapshot = json.loads(target_snap_row['tasks_snapshot'])
            
    cursor.execute("SELECT task_key, title, description, status, assigned_to FROM git_tasks WHERE branch_name = ?", (target_branch,))
    working_tasks = {row['task_key']: dict(row) for row in cursor.fetchall()}
    
    has_uncommitted = False
    for key, task in working_tasks.items():
        if key not in target_snapshot:
            has_uncommitted = True
            break
        base = target_snapshot[key]
        if (task['title'] != base.get('title') or 
            task['description'] != base.get('description', '') or 
            task['status'] != base.get('status') or 
            task['assigned_to'] != base.get('assigned_to', '')):
            has_uncommitted = True
            break
    for key in target_snapshot:
        if key not in working_tasks:
            has_uncommitted = True
            break
            
    if has_uncommitted:
        conn.close()
        return jsonify({"error": "Please commit or discard your working tree changes before merging."}), 400
        
    # Get source latest commit
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (source_branch,))
    source_row = cursor.fetchone()
    source_commit = source_row[0] if source_row else None
    
    if not source_commit:
        conn.close()
        return jsonify({"error": f"Branch '{source_branch}' has no commits to merge."}), 400
        
    source_snapshot = {}
    cursor.execute("SELECT tasks_snapshot FROM git_commits WHERE hash = ?", (source_commit,))
    source_snap_row = cursor.fetchone()
    if source_snap_row:
        source_snapshot = json.loads(source_snap_row['tasks_snapshot'])
        
    # Find common ancestor
    base_commit_hash = find_common_ancestor(conn, target_branch, source_branch)
    
    base_snapshot = {}
    if base_commit_hash:
        cursor.execute("SELECT tasks_snapshot FROM git_commits WHERE hash = ?", (base_commit_hash,))
        base_snap_row = cursor.fetchone()
        if base_snap_row:
            base_snapshot = json.loads(base_snap_row['tasks_snapshot'])
            
    # Perform 3-way merge
    merged_snapshot, conflicts = three_way_merge(base_snapshot, target_snapshot, source_snapshot)
    
    if conflicts:
        # Save conflict state in session for resolution
        session['active_merge'] = {
            "target_branch": target_branch,
            "source_branch": source_branch,
            "merged_snapshot": merged_snapshot,
            "conflicts": conflicts
        }
        conn.close()
        flint_system_message(
    f"⚠️ Merge conflict detected while merging "
    f"'{source_branch}' into '{target_branch}'. "
    f"Manual resolution required."
    )
        return jsonify({
            "status": "conflict",
            "conflicts": conflicts
        })
        
    # No conflicts: perform merge commit
    cursor.execute("DELETE FROM git_tasks WHERE branch_name = ?", (target_branch,))
    epoch_now = int(time.time())
    for task_key, task in merged_snapshot.items():
        cursor.execute('''
            INSERT INTO git_tasks (branch_name, task_key, title, description, status, assigned_to, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (target_branch, task_key, task['title'], task['description'], task['status'], task['assigned_to'], epoch_now))
        
    cursor.execute("SELECT username FROM users WHERE id = ?", (session['user_id'],))
    username = cursor.fetchone()[0]
    
    merge_hash = hashlib.sha1(f"merge-{target_branch}-{source_branch}-{datetime.datetime.now().isoformat()}".encode()).hexdigest()
    merge_msg = f"Merge branch '{source_branch}' into {target_branch}"
    
    cursor.execute('''
        INSERT INTO git_commits (hash, branch_name, parent_hash, parent2_hash, message, author, tasks_snapshot, committed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (merge_hash, target_branch, target_commit, source_commit, merge_msg, username, json.dumps(merged_snapshot), epoch_now))
    
    cursor.execute("UPDATE git_branches SET current_commit_hash = ? WHERE name = ?", (merge_hash, target_branch))
    
    conn.commit()
    conn.close()
    
    broadcast_live_event("git_update")
    return jsonify({
        "status": "success",
        "commit_hash": merge_hash
    })

@app.route('/api/git/resolve', methods=['POST'])
def git_resolve():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    resolutions = data.get('resolutions', {})
    
    active_merge = session.get('active_merge')
    if not active_merge:
        return jsonify({"error": "No active merge found"}), 400
        
    merged_snapshot = active_merge['merged_snapshot']
    conflicts = active_merge['conflicts']
    target_branch = active_merge['target_branch']
    source_branch = active_merge['source_branch']
    
    for key, choice in resolutions.items():
        if key not in conflicts:
            continue
        if choice == 'ours':
            val = conflicts[key]['ours']
        elif choice == 'theirs':
            val = conflicts[key]['theirs']
        else:
            return jsonify({"error": f"Invalid choice for task {key}"}), 400
            
        if val is not None:
            merged_snapshot[key] = val
        elif key in merged_snapshot:
            del merged_snapshot[key]
            
    conn = get_db()
    cursor = conn.cursor()
    
    # Update working tree
    cursor.execute("DELETE FROM git_tasks WHERE branch_name = ?", (target_branch,))
    epoch_now = int(time.time())
    for task_key, task in merged_snapshot.items():
        cursor.execute('''
            INSERT INTO git_tasks (branch_name, task_key, title, description, status, assigned_to, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (target_branch, task_key, task['title'], task['description'], task['status'], task['assigned_to'], epoch_now))
        
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (target_branch,))
    parent_hash = cursor.fetchone()[0]
    
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (source_branch,))
    parent2_hash = cursor.fetchone()[0]
    
    cursor.execute("SELECT username FROM users WHERE id = ?", (session['user_id'],))
    username = cursor.fetchone()[0]
    
    commit_hash = hashlib.sha1(f"merge-{target_branch}-{source_branch}-{datetime.datetime.now().isoformat()}".encode()).hexdigest()
    commit_msg = f"Merge branch '{source_branch}' into {target_branch} (Conflicts resolved)"
    
    cursor.execute('''
        INSERT INTO git_commits (hash, branch_name, parent_hash, parent2_hash, message, author, tasks_snapshot, committed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (commit_hash, target_branch, parent_hash, parent2_hash, commit_msg, username, json.dumps(merged_snapshot), epoch_now))
    
    cursor.execute("UPDATE git_branches SET current_commit_hash = ? WHERE name = ?", (commit_hash, target_branch))
    
    conn.commit()
    conn.close()
    flint_system_message(
    f"🛠️ Merge conflicts between "
    f"'{source_branch}' and '{target_branch}' "
    f"were resolved."
    )
    session.pop('active_merge', None)
    broadcast_live_event("git_update")
    return jsonify({"success": True, "commit_hash": commit_hash})

@app.route('/api/git/discard', methods=['POST'])
def git_discard():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    branch = session.get('current_branch', 'main')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch latest commit snapshot
    cursor.execute("SELECT current_commit_hash FROM git_branches WHERE name = ?", (branch,))
    row = cursor.fetchone()
    commit_hash = row[0] if row else None
    
    if not commit_hash:
        conn.close()
        return jsonify({"error": "Cannot discard changes on a branch with no commits"}), 400
        
    cursor.execute("SELECT tasks_snapshot FROM git_commits WHERE hash = ?", (commit_hash,))
    commit_row = cursor.fetchone()
    if not commit_row:
        conn.close()
        return jsonify({"error": "Commit not found"}), 404
        
    snapshot = json.loads(commit_row['tasks_snapshot'])
    
    # Replace working tree with snapshot
    cursor.execute("DELETE FROM git_tasks WHERE branch_name = ?", (branch,))
    epoch_now = int(time.time())
    for task_key, task in snapshot.items():
        cursor.execute('''
            INSERT INTO git_tasks (branch_name, task_key, title, description, status, assigned_to, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (branch, task_key, task['title'], task['description'], task['status'], task['assigned_to'], epoch_now))
        
    conn.commit()
    conn.close()
    broadcast_live_event("git_update")
    return jsonify({"success": True})

# --- Settings & Profile Routes ---

@app.route('/api/settings/smtp', methods=['GET'])
def get_smtp_settings():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    server = SMTP_SERVER
    port = SMTP_PORT
    sender_email = SMTP_EMAIL
    pwd = SMTP_PASSWORD

    if not sender_email or not pwd:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT server, port, sender_email, password FROM smtp_config LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            server = row['server']
            port = row['port']
            sender_email = row['sender_email']
            pwd = row['password']
            
    masked_pwd = '*' * len(pwd) if pwd else ''
    return jsonify({
        "server": server,
        "port": port,
        "sender_email": sender_email,
        "password_configured": bool(pwd),
        "password_masked": masked_pwd
    })

@app.route('/api/settings', methods=['POST'])
def update_settings():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    nickname = data.get('nickname')
    country = data.get('country')
    avatar = data.get('avatar')
    password = data.get('password')
    
    smtp_server = data.get('smtp_server')
    smtp_port = data.get('smtp_port')
    smtp_email = data.get('smtp_email')
    smtp_password = data.get('smtp_password')
    
    conn = get_db()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if nickname:
        updates.append("username = ?")
        params.append(nickname)
    if country:
        tz = COUNTRY_TIMEZONES.get(country, "UTC")
        updates.append("country = ?")
        params.append(country)
        updates.append("timezone = ?")
        params.append(tz)
    if avatar:
        if avatar.startswith("data:image/"):
            avatar = save_avatar_from_base64(avatar)
        updates.append("avatar = ?")
        params.append(avatar)
    if password:
        from werkzeug.security import generate_password_hash
        pwd_hash = generate_password_hash(password)
        updates.append("password_hash = ?")
        params.append(pwd_hash)
        
    if updates:
        params.append(session['user_id'])
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        try:
            cursor.execute(query, params)
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "Nickname already taken by another team member."}), 400
            
    # Update global SMTP settings if provided
    if smtp_server is not None or smtp_port is not None or smtp_email is not None or smtp_password is not None:
        global SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD
        if smtp_server is not None:
            SMTP_SERVER = smtp_server
        if smtp_port is not None:
            SMTP_PORT = int(smtp_port)
        if smtp_email is not None:
            SMTP_EMAIL = smtp_email
        if smtp_password is not None:
            SMTP_PASSWORD = smtp_password

        cursor.execute("SELECT id FROM smtp_config LIMIT 1")
        row = cursor.fetchone()
        if row:
            smtp_updates = []
            smtp_params = []
            if smtp_server is not None:
                smtp_updates.append("server = ?")
                smtp_params.append(smtp_server)
            if smtp_port is not None:
                smtp_updates.append("port = ?")
                smtp_params.append(int(smtp_port))
            if smtp_email is not None:
                smtp_updates.append("sender_email = ?")
                smtp_params.append(smtp_email)
            if smtp_password is not None:
                smtp_updates.append("password = ?")
                smtp_params.append(smtp_password)
                
            if smtp_updates:
                smtp_params.append(row['id'])
                query = f"UPDATE smtp_config SET {', '.join(smtp_updates)} WHERE id = ?"
                cursor.execute(query, smtp_params)
        else:
            cursor.execute('''
                INSERT INTO smtp_config (server, port, sender_email, password)
                VALUES (?, ?, ?, ?)
            ''', (smtp_server or 'smtp.gmail.com', int(smtp_port or 587), smtp_email or '', smtp_password or ''))
            
    conn.commit()
    conn.close()
    
    broadcast_live_event("presence_update")
    return jsonify({"success": True})

@app.route('/api/settings/test_smtp', methods=['POST'])
def test_smtp():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    server_host = data.get('smtp_server')
    port = data.get('smtp_port')
    sender_email = data.get('smtp_email')
    password = data.get('smtp_password')
    
    if not all([server_host, port, sender_email, password]):
        return jsonify({"error": "All SMTP fields must be provided to run connection test"}), 400
        
    try:
        import smtplib
        from email.mime.text import MIMEText
        
        msg = MIMEText("Connection test from your GitSync Dashboard Settings! If you receive this, SMTP is working correctly.")
        msg['Subject'] = "GitSync SMTP Connection Test"
        msg['From'] = sender_email
        msg['To'] = sender_email
        
        server = smtplib.SMTP(server_host, int(port), timeout=10)
        server.starttls()
        server.login(sender_email, password)
        server.sendmail(sender_email, sender_email, msg.as_string())
        server.quit()
        
        return jsonify({"success": True, "message": f"SMTP test successful! Email sent to {sender_email}."})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 400

@app.route('/api/git/metrics', methods=['GET'])
def git_metrics():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Total Commits & Author Leaderboard
    cursor.execute("SELECT author, COUNT(*) as commit_count FROM git_commits GROUP BY author ORDER BY commit_count DESC")
    authors_data = [dict(row) for row in cursor.fetchall()]
    total_commits = sum(a['commit_count'] for a in authors_data)
    top_contributor = authors_data[0]['author'] if authors_data else "None"
    
    # 2. Branch Count
    cursor.execute("SELECT COUNT(*) FROM git_branches")
    total_branches = cursor.fetchone()[0]
    
    # 3. Tasks Workload Breakdown
    cursor.execute("SELECT status, COUNT(*) as count FROM git_tasks GROUP BY status")
    tasks_data = {row['status']: row['count'] for row in cursor.fetchall()}
    total_tasks = sum(tasks_data.values())
    
    # 4. Commit Heatmap Data (Grouped by Date)
    cursor.execute('''
        SELECT date(committed_at, 'unixepoch') as commit_date, COUNT(*) as count
        FROM git_commits
        GROUP BY commit_date
        ORDER BY commit_date ASC
    ''')
    heatmap_data = [dict(row) for row in cursor.fetchall()]
    
    # 5. Branch Activity Matrix
    cursor.execute("SELECT branch_name, COUNT(*) as count FROM git_commits GROUP BY branch_name ORDER BY count DESC")
    branch_activity = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        "total_commits": total_commits,
        "top_contributor": top_contributor,
        "total_branches": total_branches,
        "tasks_breakdown": tasks_data,
        "total_tasks": total_tasks,
        "authors_data": authors_data,
        "heatmap_data": heatmap_data,
        "branch_activity": branch_activity
    })


if __name__ == "__main__":

    threading.Thread(
        target=meeting_worker,
        daemon=True
    ).start()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )