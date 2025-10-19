from flask import Flask, request, render_template, session, redirect, send_file, abort, jsonify
import sqlite3
import os
import subprocess
import shlex
import requests
import time
from pathlib import Path

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key')

TEAM_ID = os.environ.get('TEAM_ID', 'team1')
TEAM_TOKEN = os.environ.get('TEAM_TOKEN', '')
MAIN_SERVER = os.environ.get('MAIN_SERVER', 'http://172.30.0.10:5000')

if not TEAM_TOKEN:
    try:
        response = requests.get(f"{MAIN_SERVER}/api/auth/token/{TEAM_ID}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            TEAM_TOKEN = data.get('token', '')
            print(f"✓ Fetched token from main server for {TEAM_ID}")
        else:
            print(f"✗ Failed to fetch token: HTTP {response.status_code}")
    except Exception as e:
        print(f"✗ Error fetching token from main server: {e}")

FLAGS = {
    'monitor': os.environ.get('FLAG_MONITOR', 'FLAG{default_monitor}'),
    'logs': os.environ.get('FLAG_LOGS', 'FLAG{default_logs}'),
    'download': os.environ.get('FLAG_DOWNLOAD', 'FLAG{default_download}')
}

def fetch_flags_from_server():
    """從主服務器獲取當前所有 Flags"""
    global FLAGS
    try:
        team_num = int(TEAM_ID.replace('team', ''))
        url = f"{MAIN_SERVER}/api/team/{team_num}/flags"
        
        params = {'token': TEAM_TOKEN} if TEAM_TOKEN else {}
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if 'flags' in data:
                new_flags = data['flags']
                has_valid_flags = any(flag for flag in new_flags.values())
                
                if has_valid_flags:
                    FLAGS = new_flags
                    print(f"✓ Fetched {len(FLAGS)} flags from server:")
                    for vuln_type, flag in FLAGS.items():
                        print(f"  - {vuln_type}: {flag}")
                    update_flag_files()
                else:
                    print(f"⚠ Fetched flags are empty (game may not have started yet)")
        else:
            print(f"✗ Failed to fetch flags: HTTP {response.status_code}")
            print(f"  Response: {response.text[:200]}")
    except Exception as e:
        print(f"✗ Error fetching flags: {e}")

def update_flag_files():
    global FLAGS
    flag_path = '/app/secret_flag.txt'
    try:
        with open(flag_path, 'w') as f:
            f.write(f"Congratulations! You found the flag:\n{FLAGS['download']}\n")
        print(f"✓ Updated {flag_path} with download flag")
    except Exception as e:
        print(f"✗ Error updating {flag_path}: {e}")
    log_path = os.path.join(LOG_DIR, 'flag.log')
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(log_path, 'w') as f:
            f.write(f"FLAG: {FLAGS['logs']}\n")
        print(f"✓ Updated {log_path} with logs flag")
    except Exception as e:
        print(f"✗ Error updating {log_path}: {e}")
    try:
        conn = sqlite3.connect('blog.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE posts SET content = ? WHERE id = 999', (FLAGS['monitor'],))
        conn.commit()
        conn.close()
        print(f"✓ Updated database post (id=999) with monitor flag")
    except Exception as e:
        print(f"✗ Error updating database: {e}")
def flag_updater():
    """定期從主服務器更新 Flag"""
    while True:
        time.sleep(10)
        fetch_flags_from_server()
FILES_DIR = '/app/files'
UPLOAD_DIR = '/app/uploads'
LOG_DIR = '/app/logs'

# ==================== 資料庫初始化 ====================

def init_db():
    conn = sqlite3.connect('blog.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        INSERT OR IGNORE INTO users (username, password, is_admin) 
        VALUES ('admin', 'admin123', 1)
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO posts (id, title, content) 
        VALUES (999, 'Hidden Flag Post', 'Flag will be updated here')
    ''')
    
    conn.commit()
    conn.close()

def init_files():
    os.makedirs(FILES_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    sample_files = {
        'readme.txt': 'Welcome to our system management service!',
        'document.pdf': 'Sample document content.',
        'image.png': 'PNG image placeholder',
    }
    
    for filename, content in sample_files.items():
        filepath = os.path.join(FILES_DIR, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                f.write(content)
    
    log_files = {
        'access.log': 'Access log entries...\n',
        'error.log': 'Error log entries...\n',
        'system.log': 'System log entries...\n',
    }
    
    for filename, content in log_files.items():
        filepath = os.path.join(LOG_DIR, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                f.write(content)

# ==================== 路由 ====================

@app.route('/')
def index():
    return render_template('home.html', session=session)

@app.route('/monitor', methods=['GET', 'POST'])
def monitor():
    """
    系統監控 - Command Injection 漏洞!
    攻擊: host=google.com; cat /app/logs/flag.log
    """
    host = ''
    output = ''
    
    if request.method == 'POST':
        host = request.form.get('host', '')
        
        if host:
            try:
                cmd = f"dig {host}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                output = result.stdout + result.stderr
            except subprocess.TimeoutExpired:
                output = "Command timed out!"
            except Exception as e:
                output = f"Error: {str(e)}"
    
    return render_template('monitor.html', host=host, output=output)

@app.route('/logs', methods=['GET', 'POST'])
def logs():
    keyword = ''
    output = ''
    
    if request.method == 'POST':
        keyword = request.form.get('keyword', '')
        
        if keyword:
            try:
                cmd = f"grep -r \"{keyword}\" {LOG_DIR}/"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                output = result.stdout if result.stdout else "No matches found"
            except subprocess.TimeoutExpired:
                output = "Search timed out!"
            except Exception as e:
                output = f"Error: {str(e)}"
    
    return render_template('logs.html', keyword=keyword, output=output)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('blog.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username=? AND password=?', (username, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session['username'] = user[1]
            session['is_admin'] = user[3]
            return redirect('/profile')
        else:
            return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/profile')
def profile():
    if 'username' not in session:
        return redirect('/login')
    
    return render_template(
        'profile.html',
        username=session['username'],
        is_admin=session.get('is_admin', 0),
        flag=FLAGS.get('monitor', 'FLAG{default}')
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/files')
def list_files():
    try:
        files = []
        for filename in os.listdir(FILES_DIR):
            filepath = os.path.join(FILES_DIR, filename)
            if os.path.isfile(filepath):
                files.append({
                    'name': filename,
                    'size': os.path.getsize(filepath)
                })
        
        return render_template('files.html', files=files)
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/download')
def download():
    filename = request.args.get('file', '')
    
    if not filename:
        return "No file specified", 400
    
    try:
        filepath = os.path.join(FILES_DIR, filename)
        
        if os.path.exists(filepath) and os.path.isfile(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            return f"File '{filename}' not found!", 404
            
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/health')
def health():
    """健康檢查"""
    return 'OK', 200

# ==================== 應用初始化 ====================

def init_app():
    init_db()
    init_files()
    print(f"Team ID: {TEAM_ID}")
    print(f"Main Server: {MAIN_SERVER}")
    fetch_flags_from_server()
    import threading
    updater_thread = threading.Thread(target=flag_updater, daemon=True)
    updater_thread.start()
    print(f"✓ Application initialized for {TEAM_ID}")

# ==================== 啟動 ====================

if __name__ == '__main__':
    init_app()
    
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)

