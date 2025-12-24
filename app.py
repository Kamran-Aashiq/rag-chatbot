from flask import Flask, request, jsonify, send_from_directory, session, redirect
from chatbot_core import langgraph_app, VECTORSTORE_DIR, set_vectorstore, LLM_AVAILABLE, EMBEDDINGS_AVAILABLE
from indexer import index_documents
from langchain_community.vectorstores import FAISS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import sqlite3
from datetime import datetime
import os
from dotenv import load_dotenv
import uuid
from image_handler import process_image
OCR_AVAILABLE = True

app = Flask(__name__, static_folder='static')
load_dotenv()

# Secret key for session management (set SECRET_KEY in your environment for production)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# Database migration and setup functions
def ensure_database_schema():
    """Ensure database has the correct schema"""
    conn = sqlite3.connect("chat_history.db")
    cursor = conn.cursor()
    
    # Check and add missing columns
    try:
        cursor.execute("PRAGMA table_info(chat_metadata)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'last_updated' not in columns:
            print("Adding last_updated column to chat_metadata table...")
            cursor.execute("ALTER TABLE chat_metadata ADD COLUMN last_updated TEXT")
            print("last_updated column added successfully!")
            
    except Exception as e:
        print(f"Schema check error: {e}")
    
    conn.commit()
    conn.close()

def migrate_database():
    """Migrate existing database to new schema"""
    conn = sqlite3.connect("chat_history.db")
    cursor = conn.cursor()
    
    try:
        # Check if last_updated column exists in chat_metadata
        cursor.execute("PRAGMA table_info(chat_metadata)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'last_updated' not in columns:
            print("Migrating database: Adding last_updated column to chat_metadata table...")
            cursor.execute("ALTER TABLE chat_metadata ADD COLUMN last_updated TEXT")
            
            # Update existing records with last_updated value
            cursor.execute("UPDATE chat_metadata SET last_updated = created_at WHERE last_updated IS NULL")
            
            conn.commit()
            print("Database migration completed successfully!")
            
    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

# Initialize database schema
ensure_database_schema()
migrate_database()

# SQLite database setup
def setup_db():
    conn = sqlite3.connect("chat_history.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            timestamp TEXT,
            role TEXT,
            message TEXT
        )
    """)
    # Chat metadata table with proper naming
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT UNIQUE,
            chat_name TEXT,
            created_at TEXT,
            user_id TEXT,
            last_updated TEXT
        )
    """)
    # Store documents metadata table (if not created elsewhere)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            filepath TEXT,
            uploaded_at TEXT
        )
    """)
    # Users table for simple auth
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password_hash TEXT,
            reset_token TEXT,
            reset_expires TEXT
        )
    """)
    # Ensure avatar column exists (safe to run repeatedly)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
    except Exception:
        # Likely column already exists; ignore
        pass
    conn.commit()
    return conn

def save_message(conn, chat_id, role, message):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO conversations (chat_id, timestamp, role, message) VALUES (?, ?, ?, ?)",
        (chat_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), role, message)
    )
    conn.commit()

def get_conversation_history(conn, chat_id, limit=5):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, message FROM conversations WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, limit*2)
    )
    rows = cursor.fetchall()
    rows.reverse()
    history = ""
    for role, msg in rows:
        prefix = "User" if role == 'user' else "Assistant"
        history += f"{prefix}: {msg}\n"
    return history

def create_chat_metadata(conn, chat_id, chat_name, username):
    """Create or update chat metadata with proper naming"""
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Try the full insert first
        cursor.execute(
            "INSERT OR REPLACE INTO chat_metadata (chat_id, chat_name, created_at, user_id, last_updated) VALUES (?, ?, ?, ?, ?)",
            (chat_id, chat_name, now, username, now)
        )
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            # Fallback: insert without last_updated column
            cursor.execute(
                "INSERT OR REPLACE INTO chat_metadata (chat_id, chat_name, created_at, user_id) VALUES (?, ?, ?, ?)",
                (chat_id, chat_name, now, username)
            )
            # Then add the missing column for future use
            try:
                cursor.execute("ALTER TABLE chat_metadata ADD COLUMN last_updated TEXT")
                # Update the record we just inserted
                cursor.execute(
                    "UPDATE chat_metadata SET last_updated = ? WHERE chat_id = ?",
                    (now, chat_id)
                )
            except Exception:
                # Column might already exist, ignore
                pass
        else:
            raise e
    
    conn.commit()

def get_chat_name(conn, chat_id):
    """Get chat name from metadata, fallback to first user message"""
    cursor = conn.cursor()
    cursor.execute("SELECT chat_name FROM chat_metadata WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    
    if row and row[0]:
        return row[0]
    
    # Fallback: get first user message
    cursor.execute(
        "SELECT message FROM conversations WHERE chat_id = ? AND role = 'user' ORDER BY id ASC LIMIT 1", 
        (chat_id,)
    )
    first_message = cursor.fetchone()
    if first_message and first_message[0]:
        return first_message[0][:30] + '...' if len(first_message[0]) > 30 else first_message[0]
    
    return "New Chat"

def update_chat_name(conn, chat_id, new_name):
    """Update chat name in metadata"""
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE chat_metadata SET chat_name = ?, last_updated = ? WHERE chat_id = ?",
        (new_name, now, chat_id)
    )
    conn.commit()

# Note: the LangGraph workflow is defined in chatbot_core.py and imported as langgraph_app.

# Flask Routes
@app.route('/')
def serve_index():
    # Require login for main UI
    if not session.get('logged_in'):
        return redirect('/login')
    return send_from_directory('static', 'index.html')


@app.route('/login', methods=['GET'])
def login_page():
    # Serve the login page from the dedicated auth folder if present;
    # otherwise fall back to top-level static/login.html so missing files
    # in static/auth don't cause a 404.
    auth_path = os.path.join('static', 'auth', 'login.html')
    if os.path.exists(auth_path):
        return send_from_directory(os.path.join('static', 'auth'), 'login.html')
    # fallback to the top-level static login page
    return send_from_directory('static', 'login.html')


@app.route('/login', methods=['POST'])
def login_action():
    # Accept both JSON and form-encoded requests
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username')
    password = data.get('password')

    # First try matching against users table (if present)
    conn = setup_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    if row:
        password_hash = row[0]
        if check_password_hash(password_hash, password):
            session['logged_in'] = True
            session['username'] = username
            conn.close()
            return jsonify({'success': True})
        conn.close()
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    # Fallback to environment credentials for dev convenience
    expected_user = os.environ.get('ADMIN_USER', 'admin')
    expected_pass = os.environ.get('ADMIN_PASS', 'admin')
    conn.close()
    if username == expected_user and password == expected_pass:
        session['logged_in'] = True
        session['username'] = username
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401


@app.route('/forgot', methods=['GET'])
def forgot_page():
    # Serve the forgot-password page from the dedicated auth folder if present;
    # otherwise fall back to top-level static/forgot.html
    auth_path = os.path.join('static', 'auth', 'forgot.html')
    if os.path.exists(auth_path):
        return send_from_directory(os.path.join('static', 'auth'), 'forgot.html')
    return send_from_directory('static', 'forgot.html')


@app.route('/api/chats', methods=['GET'])
def get_chats():
    if not session.get('logged_in'):
        return jsonify([]), 401
    
    username = session.get('username')
    conn = setup_db()
    cursor = conn.cursor()
    
    try:
        # Try the new query first
        cursor.execute("""
            SELECT chat_id, chat_name, last_updated 
            FROM chat_metadata 
            WHERE user_id = ? 
            ORDER BY last_updated DESC
        """, (username,))
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            # Fallback to old query without last_updated
            cursor.execute("""
                SELECT chat_id, chat_name, created_at 
                FROM chat_metadata 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            """, (username,))
        else:
            conn.close()
            raise e
    
    chats = []
    for row in cursor.fetchall():
        chat_id, chat_name, timestamp = row
        chats.append({
            'id': chat_id, 
            'name': chat_name,
            'last_updated': timestamp  # This will be created_at if last_updated doesn't exist
        })
    
    # If no chats in metadata, check conversations table as fallback
    if not chats:
        cursor.execute("""
            SELECT DISTINCT chat_id 
            FROM conversations 
            WHERE chat_id LIKE ? 
            ORDER BY id DESC
        """, (f'{username}-%',))
        
        for row in cursor.fetchall():
            chat_id = row[0]
            chat_name = get_chat_name(conn, chat_id)
            chats.append({
                'id': chat_id,
                'name': chat_name,
                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
    
    conn.close()
    return jsonify(chats)


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or request.form or {}
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    if not username or not email or not password:
        return jsonify({'error': 'username, email and password required'}), 400
    conn = setup_db()
    cursor = conn.cursor()
    try:
        pw_hash = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)", (username, email, pw_hash))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Account created'}), 201
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


@app.route('/forgot', methods=['POST'])
def forgot_password():
    data = request.get_json(silent=True) or request.form or {}
    email = data.get('email')
    if not email:
        return jsonify({'error': 'email required'}), 400
    conn = setup_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        # Do not reveal whether the email exists
        return jsonify({'message': 'If that email exists, a reset link has been sent.'})
    user_id = row[0]
    token = str(uuid.uuid4())
    expires = (datetime.now() + timedelta(hours=1)).isoformat()
    cursor.execute("UPDATE users SET reset_token = ?, reset_expires = ? WHERE id = ?", (token, expires, user_id))
    conn.commit()
    conn.close()
    # In production you'd send this token via email. For dev, return the token so user can complete reset.
    return jsonify({'message': 'Reset token generated (development only)', 'token': token})


@app.route('/reset', methods=['POST'])
def reset_password():
    data = request.get_json(silent=True) or request.form or {}
    token = data.get('token')
    new_password = data.get('password')
    if not token or not new_password:
        return jsonify({'error': 'token and new password required'}), 400
    conn = setup_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, reset_expires FROM users WHERE reset_token = ?", (token,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Invalid token'}), 400
    user_id, expires = row
    if datetime.fromisoformat(expires) < datetime.now():
        conn.close()
        return jsonify({'error': 'Token expired'}), 400
    pw_hash = generate_password_hash(new_password)
    cursor.execute("UPDATE users SET password_hash = ?, reset_token = NULL, reset_expires = NULL WHERE id = ?", (pw_hash, user_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Password has been reset'})


@app.route('/api/user', methods=['GET'])
def get_current_user():
    if not session.get('logged_in'):
        return jsonify({'user': None}), 200
    username = session.get('username')
    conn = setup_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, avatar FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'user': {'username': username}})
    avatar_val = row[3]
    # Normalize avatar to a web-accessible path
    if avatar_val:
        # If it already looks like a web path, use it; otherwise convert to /uploads/<basename>
        if avatar_val.startswith('/') or avatar_val.startswith('http'):
            avatar_web = avatar_val
        else:
            avatar_web = '/uploads/' + os.path.basename(avatar_val)
    else:
        avatar_web = None
    user = {'id': row[0], 'username': row[1], 'email': row[2], 'avatar': avatar_web}
    return jsonify({'user': user})


@app.route('/api/user/update', methods=['POST'])
def update_user():
    if not session.get('logged_in'):
        return jsonify({'error': 'not logged in'}), 401
    data = request.get_json(silent=True) or request.form or {}
    new_username = data.get('username')
    new_email = data.get('email')
    if not new_username and not new_email:
        return jsonify({'error': 'username or email required'}), 400
    old_username = session.get('username')
    conn = setup_db()
    cursor = conn.cursor()
    try:
        # If updating username, ensure it's not already taken
        if new_username and new_username != old_username:
            cursor.execute("SELECT id FROM users WHERE username = ?", (new_username,))
            if cursor.fetchone():
                conn.close()
                return jsonify({'error': 'username already taken'}), 400
        # If updating email, ensure it's not already taken by another user
        if new_email:
            cursor.execute("SELECT id FROM users WHERE email = ? AND username != ?", (new_email, old_username))
            if cursor.fetchone():
                conn.close()
                return jsonify({'error': 'email already in use'}), 400

        # Build update statement dynamically
        updates = []
        params = []
        if new_username:
            updates.append('username = ?')
            params.append(new_username)
        if new_email:
            updates.append('email = ?')
            params.append(new_email)
        params.append(old_username)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
        cursor.execute(sql, tuple(params))
        conn.commit()
        # If username changed, update session
        if new_username:
            session['username'] = new_username
        conn.close()
        return jsonify({'message': 'Profile updated', 'username': new_username or old_username, 'email': new_email})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


@app.route('/api/user/avatar', methods=['POST'])
def upload_avatar():
    if not session.get('logged_in'):
        return jsonify({'error': 'not logged in'}), 401
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.mimetype.startswith('image/'):
        return jsonify({'error': 'Image required'}), 400
    upload_folder = 'uploads'
    os.makedirs(upload_folder, exist_ok=True)
    filename = f"avatar_{uuid.uuid4()}.png"
    path = os.path.join(upload_folder, filename)
    file.save(path)
    username = session.get('username')
    conn = setup_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET avatar = ? WHERE username = ?", (path, username))
    conn.commit()
    conn.close()
    # Return a web-friendly avatar URL
    avatar_web = '/uploads/' + os.path.basename(path)
    return jsonify({'message': 'Avatar uploaded', 'avatar': avatar_web})


@app.route('/api/user/change_password', methods=['POST'])
def change_password():
    if not session.get('logged_in'):
        return jsonify({'error': 'not logged in'}), 401
    data = request.get_json(silent=True) or request.form or {}
    current = data.get('current_password')
    new = data.get('new_password')
    if not current or not new:
        return jsonify({'error': 'current_password and new_password required'}), 400
    username = session.get('username')
    conn = setup_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'user not found'}), 404
    pw_hash = row[0]
    if not check_password_hash(pw_hash, current):
        conn.close()
        return jsonify({'error': 'current password incorrect'}), 403
    new_hash = generate_password_hash(new)
    cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Password changed'})

@app.route('/api/message', methods=['POST'])
def handle_message():
    data = request.json
    query = data.get('message')
    chat_id = data.get('chat_id')
    if not query or not chat_id:
        return jsonify({'error': 'Message and chat_id are required'}), 400

    conn = setup_db()
    
    # If this is the first user message, create chat metadata with proper name
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM conversations WHERE chat_id = ?", (chat_id,))
    message_count = cursor.fetchone()[0]
    
    if message_count == 0:
        # This is a new chat - use first user message as chat name (truncated)
        chat_name = query[:30] + '...' if len(query) > 30 else query
        create_chat_metadata(conn, chat_id, chat_name, session.get('username'))
    
    save_message(conn, chat_id, 'user', query)
    
    try:
        if not LLM_AVAILABLE:
            conn.close()
            return jsonify({'error': 'LLM not configured. Set OPENAI_API_KEY.'}), 500
        history = get_conversation_history(conn, chat_id)
        final_state = langgraph_app.invoke({"question": query, "chat_id": chat_id, "history": history})
        answer = final_state.get("final_answer") or final_state.get("raw_response")
        save_message(conn, chat_id, 'assistant', answer)
        conn.close()
        return jsonify({'response': answer})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/chats', methods=['POST'])
def create_chat():
    """Create a new chat with proper metadata"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.json
    chat_id = data.get('chat_id')
    chat_name = data.get('name', 'New AquaAI Chat')
    
    if not chat_id:
        return jsonify({'error': 'Chat ID is required'}), 400
    
    conn = setup_db()
    create_chat_metadata(conn, chat_id, chat_name, session.get('username'))
    conn.close()
    
    return jsonify({'success': True, 'chat_id': chat_id, 'name': chat_name})

@app.route('/api/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    chat_id = request.form.get('chat_id')
    if not file or not chat_id:
        return jsonify({'error': 'File and chat_id are required'}), 400
    # Accept files that are PDFs either by mimetype or by filename extension
    filename_lower = (file.filename or '').lower()
    if not (file.mimetype == 'application/pdf' or filename_lower.endswith('.pdf')):
        return jsonify({'error': 'Only PDF files are allowed (mimetype or .pdf extension)'}), 400
    # Use request.content_length for the overall request size. FileStorage.content_length is unreliable
    max_size = 10 * 1024 * 1024
    req_len = request.content_length
    if req_len is not None and req_len > max_size:
        return jsonify({'error': 'File size exceeds 10MB limit'}), 400

    # Save uploaded PDF to uploads/ and index it (append)
    upload_folder = 'uploads'
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, f"{uuid.uuid4()}.pdf")
    file.save(file_path)

    # Index the uploaded file (index_documents will save metadata and persist vectorstore)
    result = None
    try:
        result = index_documents([file_path], save_metadata=True)
    except Exception as e:
        # If indexing fails with an exception (rare, indexer usually returns a dict), return an error
        try:
            conn = setup_db()
            save_message(conn, chat_id, 'assistant', f"Document uploaded but indexing failed: {str(e)}")
            conn.close()
        except Exception:
            pass
        return jsonify({'error': 'Indexing failed', 'details': str(e)}), 500

    # If indexer ran but indexed zero documents, surface that as an error so the client knows
    if isinstance(result, dict) and result.get('indexed', 0) == 0:
        # log to DB that upload succeeded but no documents were indexed
        try:
            conn = setup_db()
            save_message(conn, chat_id, 'assistant', f"Document uploaded but could not be indexed: {result.get('message')}")
            conn.close()
        except Exception:
            pass
        # Also print to server log for debugging
        print('Indexing result indicated zero documents indexed:', result)
        return jsonify({'error': 'Unable to index document', 'message': result.get('message')}), 400
    # If indexer produced/updated a vectorstore, allow chatbot_core to pick it up
    try:
        if isinstance(result, dict) and result.get('vectorstore_dir'):
            try:
                from chatbot_core import EMBEDDINGS_AVAILABLE, embeddings
                if EMBEDDINGS_AVAILABLE:
                    # Respect opt-in flag for dangerous pickle loading
                    allow_deser = os.environ.get('ALLOW_DANGEROUS_DESERIALIZATION', '0') in ('1', 'true', 'True')
                    if allow_deser:
                        vs = FAISS.load_local(result['vectorstore_dir'], embeddings, allow_dangerous_deserialization=True)
                    else:
                        vs = FAISS.load_local(result['vectorstore_dir'], embeddings)
                    set_vectorstore(vs)
                else:
                    # Can't load vectorstore without embeddings configured
                    print('Index updated on disk but embeddings are not configured; vectorstore not loaded.')
            except Exception as e:
                # Log but don't crash the upload flow
                print('Error loading vectorstore after indexing:', e)
    except Exception:
        # Be defensive: indexer may return unexpected types
        pass

    conn = setup_db()
    # index_documents may return None or a dict; handle both safely
    if isinstance(result, dict):
        msg_extra = result.get('message', '')
    else:
        msg_extra = str(result) if result is not None else ''

    message = f"Document uploaded: {file.filename}. {msg_extra}"
    save_message(conn, chat_id, 'assistant', message)
    conn.close()

    return jsonify({'message': message})


@app.route('/api/diagnostics', methods=['GET'])
def diagnostics():
    """Return a small diagnostics JSON with environment and feature availability."""
    vs_exists = os.path.exists(VECTORSTORE_DIR)
    allow_deser = os.environ.get('ALLOW_DANGEROUS_DESERIALIZATION', '0') in ('1', 'true', 'True')
    return jsonify({
        'llm_available': LLM_AVAILABLE,
        'embeddings_available': EMBEDDINGS_AVAILABLE,
        'ocr_available': OCR_AVAILABLE,
        'vectorstore_exists': vs_exists,
        'allow_dangerous_deserialization': allow_deser,
        'env_vars': {
            'OPENAI_API_KEY_set': bool(os.environ.get('OPENAI_API_KEY')),
            'TESSERACT_CMD': os.environ.get('TESSERACT_CMD')
        }
    })


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Serve files from the uploads directory
    return send_from_directory('uploads', filename)

@app.route('/api/image', methods=['POST'])
def handle_image():
    """Accept an image upload, run OCR (if available), and ask the LLM to answer a question using the OCR text.

    Form fields:
    - file: image file
    - chat_id: chat identifier
    - question: optional user question about the image
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    chat_id = request.form.get('chat_id')
    question = request.form.get('question') or 'Describe the image and extract any readable text.'
    if not file or not chat_id:
        return jsonify({'error': 'File and chat_id are required'}), 400

    if not file.mimetype.startswith('image/'):
        return jsonify({'error': 'Only image files are allowed'}), 400

    upload_folder = 'uploads'
    os.makedirs(upload_folder, exist_ok=True)
    # preserve original extension if possible
    filename = file.filename or f"{uuid.uuid4()}.png"
    _, ext = os.path.splitext(filename)
    if not ext:
        ext = '.png'
    file_path = os.path.join(upload_folder, f"{uuid.uuid4()}{ext}")
    file.save(file_path)

    if not OCR_AVAILABLE:
        return jsonify({'error': 'OCR not available. Install Pillow and pytesseract and ensure Tesseract OCR is installed on the system.'}), 500

    try:
        if not LLM_AVAILABLE:
            return jsonify({'error': 'LLM not configured. Set OPENAI_API_KEY.'}), 500
        # pass the configured llm from chatbot_core
        from chatbot_core import llm as configured_llm
        result = process_image(file_path, question, chat_id, configured_llm, setup_db, save_message, get_conversation_history)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify(result)

@app.route('/api/chats/<chat_id>', methods=['GET'])
def get_chat_messages(chat_id):
    conn = setup_db()
    cursor = conn.cursor()
    cursor.execute("SELECT role, message, timestamp FROM conversations WHERE chat_id = ? ORDER BY id", (chat_id,))
    messages = [{'sender': row[0], 'content': row[1], 'time': row[2][-8:-3]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(messages)

# FIXED: Renamed this endpoint to avoid conflict
@app.route('/api/chats/<chat_id>', methods=['DELETE'])
def delete_user_chat(chat_id):
    conn = setup_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM chat_metadata WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Chat deleted'})

@app.route('/api/chats/<chat_id>/rename', methods=['POST'])
def rename_chat(chat_id):
    data = request.json
    new_name = data.get('name')
    if not new_name:
        return jsonify({'error': 'New name is required'}), 400
    
    conn = setup_db()
    update_chat_name(conn, chat_id, new_name)
    conn.close()
    
    return jsonify({'message': 'Chat renamed', 'name': new_name})

# Admin routes
@app.route('/admin')
def admin_dashboard():
    # Simple admin check - you might want to implement proper admin authentication
    if not session.get('logged_in'):
        return redirect('/login')
    return send_from_directory('static', 'admin.html')

@app.route('/api/admin/statistics')
def admin_statistics():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    conn = setup_db()
    cursor = conn.cursor()
    
    try:
        # Total users
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Total chats (unique chat_ids)
        cursor.execute("SELECT COUNT(DISTINCT chat_id) FROM conversations")
        total_chats = cursor.fetchone()[0]
        
        # Total documents
        cursor.execute("SELECT COUNT(*) FROM documents")
        total_documents = cursor.fetchone()[0]
        
        # Active today (users with activity in last 24 hours)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("SELECT COUNT(DISTINCT chat_id) FROM conversations WHERE timestamp > ?", (yesterday,))
        active_today = cursor.fetchone()[0]
        
        return jsonify({
            'total_users': total_users,
            'total_chats': total_chats,
            'total_documents': total_documents,
            'active_today': active_today
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/admin/users')
def admin_users():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    offset = (page - 1) * limit
    
    conn = setup_db()
    cursor = conn.cursor()
    
    try:
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Get users with pagination
        cursor.execute("""
            SELECT u.id, u.username, u.email, 
                   COUNT(DISTINCT c.chat_id) as chat_count,
                   MAX(c.timestamp) as last_active
            FROM users u
            LEFT JOIN conversations c ON c.chat_id LIKE u.username || '-%'
            GROUP BY u.id, u.username, u.email
            ORDER BY u.id DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        users = []
        for row in cursor.fetchall():
            users.append({
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'chat_count': row[3],
                'last_active': row[4],
                'is_active': bool(row[4])  # Simple active check
            })
        
        total_pages = (total_users + limit - 1) // limit
        
        return jsonify({
            'users': users,
            'total_pages': total_pages,
            'current_page': page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/admin/chats')
def admin_chats():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    offset = (page - 1) * limit
    
    conn = setup_db()
    cursor = conn.cursor()
    
    try:
        # Get total count
        cursor.execute("SELECT COUNT(DISTINCT chat_id) FROM conversations")
        total_chats = cursor.fetchone()[0]
        
        # Get chats with pagination and user info
        cursor.execute("""
            SELECT 
                c.chat_id,
                u.username,
                COUNT(c.id) as message_count,
                MIN(c.timestamp) as created_at,
                MAX(c.timestamp) as last_activity
            FROM conversations c
            LEFT JOIN users u ON c.chat_id LIKE u.username || '-%'
            GROUP BY c.chat_id, u.username
            ORDER BY last_activity DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        chats = []
        for row in cursor.fetchall():
            chats.append({
                'chat_id': row[0],
                'username': row[1] or 'Unknown',
                'message_count': row[2],
                'created_at': row[3],
                'last_activity': row[4]
            })
        
        total_pages = (total_chats + limit - 1) // limit
        
        return jsonify({
            'chats': chats,
            'total_pages': total_pages,
            'current_page': page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/admin/documents')
def admin_documents():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    conn = setup_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, filename, filepath, uploaded_at, 
                   LENGTH(filepath) as file_size,
                   filepath LIKE '%vectorstore%' as is_indexed
            FROM documents 
            ORDER BY uploaded_at DESC
        """)
        
        documents = []
        for row in cursor.fetchall():
            documents.append({
                'id': row[0],
                'filename': row[1],
                'filepath': row[2],
                'uploaded_at': row[3],
                'file_size': row[4],
                'is_indexed': bool(row[5])
            })
        
        return jsonify({'documents': documents})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/admin/system-status')
def admin_system_status():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        # Reuse your existing diagnostics
        vs_exists = os.path.exists(VECTORSTORE_DIR)
        allow_deser = os.environ.get('ALLOW_DANGEROUS_DESERIALIZATION', '0') in ('1', 'true', 'True')
        
        return jsonify({
            'llm_available': LLM_AVAILABLE,
            'embeddings_available': EMBEDDINGS_AVAILABLE,
            'ocr_available': OCR_AVAILABLE,
            'vectorstore_exists': vs_exists,
            'allow_dangerous_deserialization': allow_deser,
            'env_vars': {
                'OPENAI_API_KEY_set': bool(os.environ.get('OPENAI_API_KEY')),
                'TESSERACT_CMD': os.environ.get('TESSERACT_CMD')
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    conn = setup_db()
    cursor = conn.cursor()
    
    try:
        # First, get the username to delete associated chats
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        username = user[0]
        
        # Delete user's chats
        cursor.execute("DELETE FROM conversations WHERE chat_id LIKE ?", (f'{username}-%',))
        cursor.execute("DELETE FROM chat_metadata WHERE user_id = ?", (username,))
        
        # Delete user
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        conn.commit()
        return jsonify({'message': 'User deleted successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# FIXED: Renamed this endpoint to avoid conflict
@app.route('/api/admin/chats/<chat_id>', methods=['DELETE'])
def admin_delete_chat(chat_id):
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    conn = setup_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM conversations WHERE chat_id = ?", (chat_id,))
        cursor.execute("DELETE FROM chat_metadata WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return jsonify({'message': 'Chat deleted successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# Debug route to check database content
@app.route('/debug/chats')
def debug_chats():
    conn = setup_db()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, role, message FROM conversations ORDER BY id DESC LIMIT 10")
    chats = cursor.fetchall()
    cursor.execute("SELECT chat_id, chat_name, user_id FROM chat_metadata")
    metadata = cursor.fetchall()
    conn.close()
    return jsonify({
        'chats': chats, 
        'metadata': metadata,
        'session_username': session.get('username'),
        'logged_in': session.get('logged_in')
    })
@app.route('/debug-session')
def debug_session():
    return jsonify({
        'logged_in': session.get('logged_in'),
        'username': session.get('username'),
        'session_keys': list(session.keys())
    })
if __name__ == '__main__':
    app.run(debug=True)