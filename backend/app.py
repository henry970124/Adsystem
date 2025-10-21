from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import yaml
import threading
import time
import logging
import os
import subprocess
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from models import Database
from flag_manager import FlagManager
from checker import ServiceChecker
from scoring import ScoringEngine
from auth import TokenManager

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化 Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'ad-ctf-secret-key-change-me'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 載入配置
config_file = os.environ.get('CONFIG_FILE', 'config.yml')
if not os.path.exists(config_file) and os.path.exists('/app/config.yml'):
    config_file = '/app/config.yml'

with open(config_file, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 初始化組件
db = Database(config['database']['path'])
flag_manager = FlagManager(db)
service_checker = ServiceChecker(db, timeout=5)
scoring_engine = ScoringEngine(db, config)
token_manager = TokenManager()

# 生成並打印 Tokens (只在第一次生成，之後從檔案讀取)
TOKEN_FILE = '/app/data/tokens.json'
if os.path.exists(TOKEN_FILE):
    with open(TOKEN_FILE, 'r') as f:
        TOKENS = json.load(f)
    # 載入到 token_manager
    token_manager.admin_token = TOKENS['admin']
    for key, value in TOKENS.items():
        if key.startswith('team'):
            token_manager.tokens[key] = value
    logger.info("使用現有 Tokens")
else:
    TOKENS = token_manager.generate_tokens(config['game']['num_teams'])
    # 保存到檔案
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, 'w') as f:
        json.dump(TOKENS, f, indent=2)
    logger.info("生成新 Tokens")

# 遊戲狀態
game_state = {
    'started': False,
    'current_round': 0,
    'round_id': None,
    'start_time': None
}

# 初始化隊伍資料
def init_teams():
    """初始化隊伍到資料庫"""
    for team_config in config['teams']:
        db.add_team(
            team_id=team_config['id'],
            name=team_config['name'],
            host=team_config['host'],
            port=team_config['port']
        )
    logger.info(f"Initialized {len(config['teams'])} teams")

# === Web 路由 ===

@app.route('/')
def index():
    """首頁 - 返回 Dashboard"""
    # 讀取 dashboard.html
    dashboard_path = '/app/dashboard.html'
    if not os.path.exists(dashboard_path):
        dashboard_path = 'dashboard.html'
    
    try:
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 替換 API URL 為當前地址
        content = content.replace('http://localhost:8001', '')
        return content
    except FileNotFoundError:
        return jsonify({
            'error': 'Dashboard not found',
            'message': 'Please access the API at /api/status'
        }), 404

# === API 路由 ===

@app.route('/api/auth/verify', methods=['POST'])
def verify_token():
    """驗證 Token"""
    data = request.json
    
    if not data or 'token' not in data:
        return jsonify({'valid': False, 'message': 'No token provided'}), 400
    
    token = data['token']
    result = token_manager.validate_token(token)
    
    return jsonify(result)

@app.route('/api/auth/token/<team_id>', methods=['GET'])
def get_team_token(team_id):
    """獲取指定隊伍的 Token - 僅供內部容器使用"""
    # 檢查 team_id 格式
    if not team_id.startswith('team'):
        return jsonify({'error': 'Invalid team_id format'}), 400
    
    # 檢查 token 是否存在
    if team_id not in token_manager.tokens:
        return jsonify({'error': 'Team not found'}), 404
    
    return jsonify({
        'team_id': team_id,
        'token': token_manager.tokens[team_id]
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    """獲取系統狀態"""
    response_data = {
        'game_started': game_state['started'],
        'current_round': game_state['current_round'],
        'round_duration': config['game']['round_duration'],
        'num_teams': config['game']['num_teams']
    }
    
    # 如果遊戲已開始，加入當前 round 的詳細資訊
    if game_state['started']:
        current_round = db.get_current_round()
        
        # 如果在 patch 階段 (沒有 active round 但有 phase 資訊)
        if not current_round and 'patch_phase_info' in game_state:
            response_data['round_info'] = game_state['patch_phase_info']
        elif current_round:
            from datetime import datetime, timedelta
            
            round_duration = config['game']['round_duration']
            patch_duration = config['game']['patch_duration']
            
            # 處理不同格式的時間字串（支援 ISO 和 space 分隔）
            start_time_str = current_round['start_time']
            if ' ' in start_time_str:
                # 將空格格式轉換為 ISO 格式
                start_time_str = start_time_str.replace(' ', 'T')
            start_time = datetime.fromisoformat(start_time_str)
            # 確保 start_time 有時區資訊
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=ZoneInfo('Asia/Taipei'))
            
            playing_end = start_time + timedelta(seconds=round_duration)
            patching_end = playing_end + timedelta(seconds=patch_duration)
            
            now = datetime.now(tz=ZoneInfo('Asia/Taipei'))
            
            # 判斷當前階段並計算剩餘時間
            if now < playing_end:
                phase = 'playing'
                remaining_seconds = int((playing_end - now).total_seconds())
            elif now < patching_end:
                phase = 'patching'
                remaining_seconds = int((patching_end - now).total_seconds())
            else:
                phase = 'waiting'
                remaining_seconds = 0
            
            response_data['round_info'] = {
                'round_id': current_round['id'],
                'round_number': current_round['round_number'],
                'phase': phase,
                'remaining_seconds': remaining_seconds,
                'start_time': current_round['start_time']
            }
    
    return jsonify(response_data)

@app.route('/api/teams', methods=['GET'])
def get_teams():
    """獲取所有隊伍"""
    teams = db.get_teams()
    return jsonify({'teams': teams})

@app.route('/api/scoreboard', methods=['GET'])
def get_scoreboard():
    """獲取排行榜"""
    scoreboard = db.get_scoreboard()
    current_round = db.get_current_round()
    
    return jsonify({
        'current_round': current_round['round_number'] if current_round else 0,
        'scoreboard': scoreboard
    })

@app.route('/api/round/<int:round_number>/scores', methods=['GET'])
def get_round_scores(round_number):
    """獲取特定 Round 的分數"""
    # 查找 round_id
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM rounds WHERE round_number = ?', (round_number,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': 'Round not found'}), 404
    
    round_id = result['id']
    scores = db.get_round_scores(round_id)
    
    return jsonify({'round': round_number, 'scores': scores})

@app.route('/api/flag/submit', methods=['POST'])
def submit_flag():
    """提交 Flag（需要 Token 認證）"""
    data = request.json
    
    if not data or 'token' not in data or 'flag' not in data:
        return jsonify({'error': 'Missing token or flag'}), 400
    
    token = data['token']
    flag_value = data['flag'].strip()
    
    # 驗證 Token
    auth_result = token_manager.validate_token(token)
    if not auth_result['valid']:
        return jsonify({'error': 'Invalid token'}), 401
    
    if auth_result['role'] != 'team':
        return jsonify({'error': 'Only team tokens can submit flags'}), 403
    
    # 將 "team1" 轉換為數字 1
    team_str = auth_result['team_id']
    team_id = int(team_str.replace('team', ''))
    
    # 檢查遊戲是否開始
    if not game_state['started']:
        return jsonify({'error': 'Game not started'}), 400
    
    # 檢查隊伍是否存在
    teams = db.get_teams()
    if not any(t['id'] == team_id for t in teams):
        return jsonify({'error': 'Invalid team_id'}), 400
    
    # 提交 flag
    current_round = db.get_current_round()
    if not current_round:
        return jsonify({'error': 'No active round'}), 400
    
    result = db.submit_flag(team_id, flag_value, current_round['id'])
    
    # 如果成功,廣播更新
    if result['success']:
        socketio.emit('flag_captured', {
            'attacker_id': team_id,
            'victim_id': result['target_team_id'],
            'round': current_round['round_number']
        })
    
    return jsonify(result)

@app.route('/api/team/<int:team_id>/flag', methods=['GET'])
def get_team_flag(team_id):
    """獲取隊伍當前的 Flag (僅供該隊伍查看自己的 flag 或 Admin) - 返回 monitor flag"""
    # 驗證權限
    token = request.args.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    auth_result = token_manager.validate_token(token)
    if not auth_result['valid']:
        return jsonify({'error': 'Invalid token'}), 401
    
    # 檢查權限：必須是 admin 或是該隊伍自己
    if auth_result['role'] == 'team':
        team_str = auth_result['team_id']
        requester_team_id = int(team_str.replace('team', ''))
        if requester_team_id != team_id:
            return jsonify({'error': 'You can only view your own flags'}), 403
    elif auth_result['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    current_round = db.get_current_round()
    if not current_round:
        return jsonify({'error': 'No active round'}), 400
    
    flag = flag_manager.get_team_flag(team_id, current_round['id'], 'monitor')
    
    if not flag:
        return jsonify({'error': 'Flag not found'}), 404
    
    return jsonify({
        'team_id': team_id,
        'round': current_round['round_number'],
        'flag': flag
    })

@app.route('/api/team/<int:team_id>/flags', methods=['GET'])
def get_team_flags(team_id):
    """獲取隊伍當前的所有 Flags(三個漏洞) - 僅供該隊伍或 Admin"""
    # 驗證權限
    token = request.args.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    auth_result = token_manager.validate_token(token)
    if not auth_result['valid']:
        return jsonify({'error': 'Invalid token'}), 401
    
    # 檢查權限：必須是 admin 或是該隊伍自己
    if auth_result['role'] == 'team':
        team_str = auth_result['team_id']
        requester_team_id = int(team_str.replace('team', ''))
        if requester_team_id != team_id:
            return jsonify({'error': 'You can only view your own flags'}), 403
    elif auth_result['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    current_round = db.get_current_round()
    
    # 如果沒有 active round (patch 階段或遊戲未開始),返回空 flags
    if not current_round:
        return jsonify({
            'team_id': team_id,
            'round': 0,
            'flags': {
                'download': '',
                'logs': '',
                'monitor': ''
            }
        }), 200
    
    flags = flag_manager.get_team_all_flags(team_id, current_round['id'])
    
    if not flags:
        return jsonify({'error': 'Flags not found'}), 404
    
    return jsonify({
        'team_id': team_id,
        'round': current_round['round_number'],
        'flags': flags
    })

@app.route('/api/service-status', methods=['GET'])
def get_service_status():
    """獲取所有服務狀態"""
    current_round = db.get_current_round()
    if not current_round:
        return jsonify({'services': []}), 200
    
    statuses = db.get_service_status(current_round['id'])
    
    # 組合隊伍資訊
    teams = {t['id']: t for t in db.get_teams()}
    result = []
    
    for status in statuses:
        team_id = status['team_id']
        if team_id in teams:
            result.append({
                'team_id': team_id,
                'team_name': teams[team_id]['name'],
                'is_up': status['is_up'],
                'response_time': status['response_time'],
                'checked_at': status['checked_at']
            })
    
    return jsonify({'services': result})

@app.route('/api/flag/history', methods=['GET'])
def get_flag_history():
    """獲取 Flag 提交歷史"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                fs.submitted_at as timestamp,
                fs.flag_value as flag,
                fs.is_valid as success,
                t1.name as attacker_team,
                t2.name as victim_team
            FROM flag_submissions fs
            LEFT JOIN teams t1 ON fs.submitter_team_id = t1.id
            LEFT JOIN teams t2 ON fs.target_team_id = t2.id
            ORDER BY fs.submitted_at DESC
            LIMIT 100
        ''')
        
        history = []
        for row in cursor.fetchall():
            # 隱藏 flag 內容,只顯示前8個字符
            flag_value = row['flag']
            masked_flag = flag_value[:8] + '*' * (len(flag_value) - 8) if len(flag_value) > 8 else '****'
            
            # 修正時間格式 - 處理資料庫中的時間字串，套用台灣時區
            timestamp_str = row['timestamp']
            try:
                # 嘗試解析時間戳
                if isinstance(timestamp_str, str):
                    if ' ' in timestamp_str:
                        dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    else:
                        dt = datetime.fromisoformat(timestamp_str)
                    # 如果沒有時區資訊，假設是台灣時區
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=ZoneInfo('Asia/Taipei'))
                    formatted_timestamp = dt.strftime('%Y-%m-%d %p %I:%M:%S')
                else:
                    formatted_timestamp = timestamp_str
            except:
                formatted_timestamp = timestamp_str
            
            history.append({
                'timestamp': formatted_timestamp,
                'flag': masked_flag,  # 使用遮罩後的 flag
                'success': bool(row['success']),
                'attacker_team': row['attacker_team'] or 'Unknown',
                'victim_team': row['victim_team'] or 'Unknown'
            })
        
        conn.close()
        return jsonify({'history': history})
    except Exception as e:
        logger.error(f"Error in get_flag_history: {e}")
        return jsonify({'history': [], 'error': str(e)}), 200  # 返回空列表而不是錯誤

@app.route('/api/admin/logs', methods=['GET'])
def get_admin_logs():
    """獲取服務器日誌（僅 Admin）"""
    # 從 request headers 獲取 token
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.replace('Bearer ', '')
    
    if not token or not token_manager.is_admin(token):
        return jsonify({'error': 'Admin access required'}), 401
    
    # 返回遊戲狀態摘要
    logs = [
        f"[INFO] Game running - Round {game_state['current_round']}",
        f"[INFO] Game started: {game_state['started']}",
        f"[INFO] Phase: {game_state.get('phase', 'N/A')}",
        f"[INFO] Active teams: {len(db.get_teams())}"
    ]
    
    return jsonify({'logs': logs})

@app.route('/api/patch/upload', methods=['POST'])
def upload_patch():
    """上傳 Patch 文件（僅 Team）"""
    token = request.form.get('token')
    
    if not token:
        return jsonify({'success': False, 'message': 'No token provided'}), 400
    
    # 驗證 Token
    auth_result = token_manager.validate_token(token)
    if not auth_result['valid'] or auth_result['role'] != 'team':
        return jsonify({'success': False, 'message': 'Invalid team token'}), 401
    
    # 將 "team1" 轉換為數字 1
    team_str = auth_result['team_id']
    team_id = int(team_str.replace('team', ''))
    
    # 檢查文件
    if 'patch' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['patch']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    if not file.filename.endswith('.py'):
        return jsonify({'success': False, 'message': 'Only .py files allowed'}), 400
    
    # 保存 Patch 到持久化目錄
    patch_dir = '/app/data/patches'  # 改為持久化路徑
    os.makedirs(patch_dir, exist_ok=True)
    
    patch_path = os.path.join(patch_dir, f'{team_id}_app.py')
    file.save(patch_path)
    
    # 同時保存一份到 /app/patches 供立即套用使用
    temp_patch_dir = '/app/patches'
    os.makedirs(temp_patch_dir, exist_ok=True)
    temp_patch_path = os.path.join(temp_patch_dir, f'{team_id}_app.py')
    file.seek(0)  # 重置文件指針
    file.save(temp_patch_path)
    
    logger.info(f"Patch uploaded for team {team_id} (saved to persistent storage)")
    
    return jsonify({
        'success': True,
        'message': f'Patch uploaded successfully. Will be applied in next patch phase.'
    })

@app.route('/api/patch/download', methods=['GET'])
def download_patch():
    """下載當前的 Patch 文件（僅 Team）"""
    token = request.args.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'success': False, 'message': 'No token provided'}), 400
    
    # 驗證 Token
    auth_result = token_manager.validate_token(token)
    if not auth_result['valid'] or auth_result['role'] != 'team':
        return jsonify({'success': False, 'message': 'Invalid team token'}), 401
    
    # 將 "team1" 轉換為數字 1
    team_str = auth_result['team_id']
    team_id = int(team_str.replace('team', ''))
    
    # 從持久化目錄檢查 patch 檔案
    patch_dir = '/app/data/patches'
    patch_path = os.path.join(patch_dir, f'{team_id}_app.py')
    
    if not os.path.exists(patch_path):
        return jsonify({
            'success': False, 
            'message': 'No patch file found. Please upload a patch first.'
        }), 404
    
    try:
        from flask import send_file
        return send_file(
            patch_path,
            as_attachment=True,
            download_name=f'team{team_id}_patch.py',
            mimetype='text/x-python'
        )
    except Exception as e:
        logger.error(f"Error downloading patch for team {team_id}: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to download patch: {str(e)}'
        }), 500


@app.route('/api/patch/list', methods=['GET'])
def list_patches():
    """列出所有可用的 Patch 文件"""
    token = request.args.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'success': False, 'message': 'No token provided'}), 400
    
    # 驗證 Token（需要是 team 或 admin）
    auth_result = token_manager.validate_token(token)
    if not auth_result['valid']:
        return jsonify({'success': False, 'message': 'Invalid token'}), 401
    
    if auth_result['role'] not in ['team', 'admin']:
        return jsonify({'success': False, 'message': 'Invalid token type'}), 403
    
    # 從持久化目錄列出所有 patch 檔案
    patch_dir = '/app/data/patches'
    if not os.path.exists(patch_dir):
        return jsonify({'patches': []})
    
    patches = []
    teams = db.get_teams()
    team_dict = {t['id']: t['name'] for t in teams}
    
    for filename in os.listdir(patch_dir):
        if filename.endswith('_app.py'):
            try:
                team_id = int(filename.split('_')[0])
                file_path = os.path.join(patch_dir, filename)
                file_size = os.path.getsize(file_path)
                file_mtime = os.path.getmtime(file_path)
                
                from datetime import datetime
                # 修正時間格式 - 使用台灣時區 (UTC+8)
                dt = datetime.fromtimestamp(file_mtime, tz=ZoneInfo('Asia/Taipei'))
                upload_time = dt.strftime('%Y-%m-%d %p %I:%M:%S')  # 使用 %p 顯示 AM/PM，%I 為12小時制
                
                patches.append({
                    'team_id': team_id,
                    'team_name': team_dict.get(team_id, f'Team {team_id}'),
                    'filename': filename,
                    'size': file_size,
                    'upload_time': upload_time
                })
            except (ValueError, IndexError):
                continue
    
    # 按隊伍 ID 排序
    patches.sort(key=lambda x: x['team_id'])
    
    return jsonify({
        'success': True,
        'patches': patches,
        'count': len(patches)
    })

@app.route('/api/patch/download/<int:target_team_id>', methods=['GET'])
def download_other_team_patch(target_team_id):
    """下載其他隊伍的 Patch 文件"""
    token = request.args.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'success': False, 'message': 'No token provided'}), 400
    
    # 驗證 Token（需要是 team 或 admin）
    auth_result = token_manager.validate_token(token)
    if not auth_result['valid']:
        return jsonify({'success': False, 'message': 'Invalid token'}), 401
    
    if auth_result['role'] not in ['team', 'admin']:
        return jsonify({'success': False, 'message': 'Invalid token type'}), 403
    
    # 從持久化目錄檢查目標隊伍的 patch
    patch_dir = '/app/data/patches'
    patch_path = os.path.join(patch_dir, f'{target_team_id}_app.py')
    
    if not os.path.exists(patch_path):
        return jsonify({
            'success': False,
            'message': f'Team {target_team_id} has not uploaded a patch yet.'
        }), 404
    
    try:
        from flask import send_file
        return send_file(
            patch_path,
            as_attachment=True,
            download_name=f'team{target_team_id}_patch.py',
            mimetype='text/x-python'
        )
    except Exception as e:
        logger.error(f"Error downloading patch from team {target_team_id}: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to download patch: {str(e)}'
        }), 500

@app.route('/api/game/start', methods=['POST'])
def start_game():
    """啟動遊戲（需要 Admin Token）"""
    data = request.json or {}
    token = data.get('token')
    
    # 驗證 Admin Token
    if not token or not token_manager.is_admin(token):
        return jsonify({'error': 'Admin token required'}), 401
    
    if game_state['started']:
        return jsonify({'error': 'Game already started'}), 400
    
    game_state['started'] = True
    game_state['start_time'] = datetime.now(tz=ZoneInfo('Asia/Taipei'))
    
    # 啟動遊戲循環
    threading.Thread(target=game_loop, daemon=True).start()
    
    logger.info("Game started!")
    socketio.emit('game_started', {'message': 'Game has started'})
    
    return jsonify({'message': 'Game started successfully'})

@app.route('/api/game/stop', methods=['POST'])
def stop_game():
    """停止遊戲（需要 Admin Token）"""
    data = request.json or {}
    token = data.get('token')
    
    # 驗證 Admin Token
    if not token or not token_manager.is_admin(token):
        return jsonify({'error': 'Admin token required'}), 401
    
    game_state['started'] = False
    
    # 結束當前 round
    if game_state['round_id']:
        db.close_round(game_state['round_id'])
    
    logger.info("Game stopped!")
    socketio.emit('game_stopped', {'message': 'Game has stopped'})
    
    return jsonify({'message': 'Game stopped successfully'})

# === 遊戲循環 ===

def apply_patches():
    """套用所有隊伍的 Patch 到正在運行的容器"""
    # 從持久化目錄讀取 patches
    persistent_patch_dir = '/app/data/patches'
    temp_patch_dir = '/app/patches'
    
    if not os.path.exists(persistent_patch_dir):
        logger.info("No persistent patches directory found")
        return
    
    logger.info("=== Applying Patches ===")
    
    # 獲取所有 patch 文件
    teams = db.get_teams()
    applied_count = 0
    
    for team in teams:
        team_id = team['id']
        team_name = f"team{team_id}"
        persistent_patch_file = os.path.join(persistent_patch_dir, f'{team_id}_app.py')
        
        if os.path.exists(persistent_patch_file):
            try:
                # 使用 docker cp 將檔案複製到正在運行的容器
                result = subprocess.run([
                    'docker', 'cp',
                    persistent_patch_file,
                    f'{team_name}:/app/app.py'
                ], capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    logger.info(f"Patch applied for {team_name}")
                    applied_count += 1
                    
                    # 重啟容器內的 Apache 以載入新代碼
                    restart_result = subprocess.run([
                        'docker', 'exec', team_name,
                        'bash', '-c', 'pkill -HUP apache2 || apachectl graceful'
                    ], capture_output=True, text=True, timeout=10)
                    
                    if restart_result.returncode == 0:
                        logger.info(f"Apache restarted for {team_name}")
                    else:
                        logger.warning(f"Could not restart Apache for {team_name}, container may need manual restart")
                    
                    # 注意：不刪除持久化的 patch 文件，這樣下次重啟後仍可使用
                    # 只清理臨時目錄中的文件
                    temp_patch_file = os.path.join(temp_patch_dir, f'{team_id}_app.py')
                    if os.path.exists(temp_patch_file):
                        os.remove(temp_patch_file)
                else:
                    logger.error(f"Failed to apply patch for {team_name}: {result.stderr}")
                
            except subprocess.TimeoutExpired:
                logger.error(f"Timeout applying patch for {team_name}")
            except Exception as e:
                logger.error(f"Failed to apply patch for {team_name}: {e}")
    
    if applied_count == 0:
        logger.info("No patches to apply")
    else:
        logger.info(f"Applied {applied_count} patches to running containers")

def game_loop():
    """主遊戲循環 - 5分鐘比賽 + 5分鐘套用patch"""
    logger.info("Game loop started")
    
    while game_state['started']:
        try:
            # ========== 階段 1: 比賽階段 (5 分鐘) ==========
            game_state['current_round'] += 1
            round_number = game_state['current_round']
            game_state['phase'] = 'playing'
            
            logger.info(f"=== Round {round_number} - PLAYING PHASE ===")
            
            # 創建 Round
            round_id = db.create_round(round_number)
            game_state['round_id'] = round_id
            
            # 生成新 Flags
            teams = db.get_teams()
            flags = flag_manager.create_flags_for_round(
                round_id, 
                round_number, 
                teams, 
                config['game']['flag_lifetime']
            )
            logger.info(f"Generated {len(flags)} flags for round {round_number}")
            
            # 廣播新 Round 開始
            socketio.emit('round_started', {
                'round': round_number,
                'phase': 'playing',
                'duration': config['game']['round_duration']
            })
            
            # Round 計時
            round_start = time.time()
            round_duration = config['game']['round_duration']
            check_interval = config['game']['service_check_interval']
            
            # 在 Round 期間定期檢查服務
            while time.time() - round_start < round_duration and game_state['started']:
                # 檢查所有服務
                service_status = service_checker.check_all_services(teams, round_id)
                
                # 廣播服務狀態更新
                socketio.emit('service_status_updated', {
                    'round': round_number,
                    'status': service_status
                })
                
                # 等待下次檢查
                time.sleep(check_interval)
            
            # Round 結束
            if game_state['started']:
                logger.info(f"=== Round {round_number} - SCORING ===")
                
                # 計算分數
                scoring_engine.calculate_round_scores(round_id)
                
                # 結束 Round
                db.close_round(round_id)
                
                # 廣播分數更新
                scoreboard = db.get_scoreboard()
                socketio.emit('scoreboard_updated', {
                    'round': round_number,
                    'scoreboard': scoreboard
                })
                
                logger.info(f"Round {round_number} scoring complete")
                
                # ========== 階段 2: Patch 套用階段 (5 分鐘) ==========
                logger.info(f"=== Round {round_number} - PATCH PHASE ===")
                game_state['phase'] = 'patching'
                
                # 計算 patch 階段結束時間
                patch_duration = config['game'].get('patch_duration', 300)
                patch_end_time = datetime.now(tz=ZoneInfo('Asia/Taipei')) + timedelta(seconds=patch_duration)
                
                # 保存 patch 階段資訊供 API 使用
                game_state['patch_phase_info'] = {
                    'round_id': round_id,
                    'round_number': round_number,
                    'phase': 'patching',
                    'remaining_seconds': patch_duration,
                    'start_time': datetime.now(tz=ZoneInfo('Asia/Taipei')).isoformat()
                }
                
                # 廣播進入 Patch 階段
                socketio.emit('phase_changed', {
                    'phase': 'patching',
                    'duration': patch_duration,
                    'message': '正在套用 Patch，服務暫停中...'
                })
                
                # 記錄 patch 階段開始時間
                patch_start = time.time()
                
                # Patch 階段：重啟容器並套用 patches
                # 注意：簡單的 restart 不會恢復被刪除的檔案
                # 檔案恢復需要靠 secret_flag.txt 在應用啟動時自動創建
                
                team_names = [f"team{team['id']}" for team in teams]
                
                # Step 1: 停止並刪除所有容器
                logger.info("Stopping and removing all team containers...")
                try:
                    subprocess.run(
                        ['docker', 'rm', '-f'] + team_names,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    logger.info(f"Removed containers: {', '.join(team_names)}")
                except Exception as e:
                    logger.error(f"Error stopping/removing containers: {e}")
                
                # Step 2: 確保網路存在
                logger.info("Step 2: Ensuring network exists...")
                try:
                    result = subprocess.run(
                        ['docker', 'network', 'inspect', 'adsystem_ad-network'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode != 0:
                        logger.info("Network not found, creating adsystem_ad-network...")
                        subprocess.run(
                            ['docker', 'network', 'create', '--subnet=172.30.0.0/24', 'adsystem_ad-network'],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        logger.info("Network created")
                except Exception as e:
                    logger.error(f"Error checking/creating network: {e}")

                # Step 3: 從映像重新創建所有容器
                logger.info("Step 3: Recreating containers from clean images...")
                recreate_success = 0
                recreate_failed = 0
                
                for team in teams:
                    team_id = team['id']
                    team_name = f"team{team_id}"
                    image_name = f"adsystem_{team_name}"
                    
                    try:
                        # 從映像重新創建容器
                        docker_run_cmd = [
                            'docker', 'run', '-d',
                            '--name', team_name,
                            '--network', 'adsystem_ad-network',
                            '--ip', f'172.30.0.{100 + team_id}',
                            '-p', f'{8100 + team_id}:8000',
                            '-e', f'TEAM_ID={team_name}',
                            '-e', 'MAIN_SERVER=http://172.30.0.10:5000',
                            '-e', 'PORT=8000',
                            '-e', f'SECRET_KEY={team_name}-secret-key',
                            '-e', 'APACHE_LOG_DIR=/var/log/apache2',
                            '-v', f'adsystem_{team_name}-logs:/app/logs',
                            '-v', f'adsystem_{team_name}-files:/app/files',
                            image_name
                        ]
                        
                        result = subprocess.run(
                            docker_run_cmd,
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        
                        if result.returncode == 0:
                            recreate_success += 1
                            logger.info(f"Successfully recreated {team_name}")
                        else:
                            recreate_failed += 1
                            logger.error(f"Failed to recreate {team_name}: {result.stderr}")
                            
                    except subprocess.TimeoutExpired:
                        recreate_failed += 1
                        logger.error(f"Timeout recreating {team_name}")
                    except Exception as e:
                        recreate_failed += 1
                        logger.error(f"Error recreating {team_name}: {e}")

                logger.info(f"Recreation complete: {recreate_success} success, {recreate_failed} failed")

                # Step 4: 等待容器完全啟動
                logger.info("Step 4: Waiting for containers to fully start...")
                time.sleep(15)
                
                # Step 5: 套用 Patches
                logger.info("Step 5: Applying patches...")
                apply_patches()

                # Step 6: 等待 patches 套用完成
                time.sleep(5)
                
                # 預熱請求：觸發 WSGI 應用初始化 (創建 secret_flag.txt 等檔案)
                logger.info("Warming up team containers (triggering WSGI app initialization)...")
                import requests
                warmup_success = 0
                warmup_failed = 0
                for team in teams:
                    team_id = team['id']
                    try:
                        # 訪問健康檢查端點觸發應用載入
                        response = requests.get(f"http://172.30.0.{100 + team_id}:8000/health", timeout=5)
                        if response.status_code == 200:
                            warmup_success += 1
                        else:
                            warmup_failed += 1
                            logger.warning(f"team{team_id} warmup returned HTTP {response.status_code}")
                    except Exception as e:
                        warmup_failed += 1
                        logger.error(f"Failed to warm up team{team_id}: {e}")
                logger.info(f"Warmup complete: {warmup_success} success, {warmup_failed} failed")
                
                # 等待剩餘的 patch 時間
                patch_duration = config['game'].get('patch_duration', 300)
                applied_time = time.time() - patch_start
                remaining_time = patch_duration - applied_time
                
                if remaining_time > 0:
                    logger.info(f"Waiting {remaining_time:.0f}s before next round...")
                    
                    # 在等待期間更新剩餘時間
                    wait_start = time.time()
                    while time.time() - wait_start < remaining_time and game_state['started']:
                        elapsed = time.time() - wait_start
                        remaining = int(remaining_time - elapsed)
                        if remaining > 0:
                            game_state['patch_phase_info']['remaining_seconds'] = remaining
                        time.sleep(1)  # 每秒更新一次
                
                # 清除 patch 階段資訊
                if 'patch_phase_info' in game_state:
                    del game_state['patch_phase_info']
                
                logger.info("Patch phase complete, ready for next round")
        
        except Exception as e:
            logger.error(f"Error in game loop: {e}", exc_info=True)
            time.sleep(5)
    
    logger.info("Game loop ended")

# === WebSocket 事件 ===

@socketio.on('connect')
def handle_connect():
    """客戶端連接"""
    logger.info("Client connected")
    emit('connected', {'message': 'Connected to A&D CTF server'})

@socketio.on('disconnect')
def handle_disconnect():
    """客戶端斷開"""
    logger.info("Client disconnected")

# === 啟動應用 ===

if __name__ == '__main__':
    # 初始化隊伍
    init_teams()
    
    # 打印 Tokens
    print("\n" + "="*80)
    print("🔐 AUTHENTICATION TOKENS")
    print("="*80)
    print("\n🛡️  ADMIN TOKEN:")
    print(f"   {TOKENS['admin']}")
    print("\n" + "-"*80)
    print("\n👥 TEAM TOKENS:")
    for i in range(1, config['game']['num_teams'] + 1):
        team_id = f"team{i}"
        print(f"   Team {i:2d}: {TOKENS[team_id]}")
    print("\n" + "="*80)
    print("⚠️  請妥善保管這些 Token！它們只會在啟動時顯示一次。")
    print("="*80 + "\n")
    
    logger.info("Tokens generated and printed")
    
    # 啟動服務器
    host = config['server']['host']
    port = config['server']['port']
    debug = config['server']['debug']
    
    logger.info(f"Starting A&D CTF server on {host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
