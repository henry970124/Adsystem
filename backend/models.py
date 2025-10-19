import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import json

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # 啟用 WAL 模式以提高並發性能
        conn.execute('PRAGMA journal_mode=WAL')
        # 設置較短的 busy timeout
        conn.execute('PRAGMA busy_timeout=30000')
        return conn
    
    def init_db(self):
        """初始化資料庫結構"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Teams 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Rounds 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_number INTEGER NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Flags 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                round_id INTEGER NOT NULL,
                flag_value TEXT NOT NULL UNIQUE,
                vuln_type TEXT DEFAULT 'monitor',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id),
                FOREIGN KEY (round_id) REFERENCES rounds(id)
            )
        ''')
        
        # 檢查並添加 vuln_type 欄位（如果不存在）
        cursor.execute("PRAGMA table_info(flags)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'vuln_type' not in columns:
            cursor.execute('ALTER TABLE flags ADD COLUMN vuln_type TEXT DEFAULT "monitor"')
        
        # Flag Submissions 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS flag_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submitter_team_id INTEGER NOT NULL,
                target_team_id INTEGER NOT NULL,
                round_id INTEGER NOT NULL,
                flag_value TEXT NOT NULL,
                is_valid BOOLEAN NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (submitter_team_id) REFERENCES teams(id),
                FOREIGN KEY (target_team_id) REFERENCES teams(id),
                FOREIGN KEY (round_id) REFERENCES rounds(id)
            )
        ''')
        
        # Service Status 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                round_id INTEGER NOT NULL,
                is_up BOOLEAN NOT NULL,
                response_time REAL,
                error_message TEXT,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id),
                FOREIGN KEY (round_id) REFERENCES rounds(id)
            )
        ''')
        
        # Scores 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                round_id INTEGER NOT NULL,
                sla_score REAL DEFAULT 0,
                defense_score REAL DEFAULT 0,
                attack_score REAL DEFAULT 0,
                total_score REAL DEFAULT 0,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id),
                FOREIGN KEY (round_id) REFERENCES rounds(id),
                UNIQUE(team_id, round_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_team(self, team_id: int, name: str, host: str, port: int):
        """新增隊伍"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO teams (id, name, host, port) VALUES (?, ?, ?, ?)',
            (team_id, name, host, port)
        )
        conn.commit()
        conn.close()
    
    def get_teams(self) -> List[Dict]:
        """獲取所有隊伍"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM teams ORDER BY id')
        teams = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return teams
    
    def create_round(self, round_number: int) -> int:
        """創建新 Round"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO rounds (round_number, start_time, status) VALUES (?, ?, ?)',
            (round_number, datetime.now(), 'active')
        )
        round_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return round_id
    
    def get_current_round(self) -> Optional[Dict]:
        """獲取當前 Round"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM rounds WHERE status = "active" ORDER BY id DESC LIMIT 1'
        )
        round_data = cursor.fetchone()
        conn.close()
        return dict(round_data) if round_data else None
    
    def close_round(self, round_id: int):
        """結束 Round"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE rounds SET status = "closed", end_time = ? WHERE id = ?',
            (datetime.now(), round_id)
        )
        conn.commit()
        conn.close()
    
    def add_flag(self, team_id: int, round_id: int, flag_value: str, expires_at: datetime = None, vuln_type: str = 'monitor'):
        """新增 Flag（expires_at 設為 None 表示永不過期）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        # expires_at 可以是 None，表示永不過期
        cursor.execute(
            'INSERT INTO flags (team_id, round_id, flag_value, expires_at, vuln_type) VALUES (?, ?, ?, ?, ?)',
            (team_id, round_id, flag_value, expires_at, vuln_type)
        )
        conn.commit()
        conn.close()
    
    def get_flag(self, flag_value: str) -> Optional[Dict]:
        """根據 Flag 值查詢 Flag（不再檢查過期時間）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM flags WHERE flag_value = ?',
            (flag_value,)
        )
        flag = cursor.fetchone()
        conn.close()
        
        return dict(flag) if flag else None
    
    def submit_flag(self, submitter_team_id: int, flag_value: str, round_id: int) -> Dict:
        """提交 Flag"""
        flag = self.get_flag(flag_value)
        is_valid = False
        target_team_id = None
        message = "Invalid flag"
        
        if flag:
            target_team_id = flag['team_id']
            # 不能提交自己的 flag
            if target_team_id == submitter_team_id:
                message = "Cannot submit your own flag"
            else:
                # 檢查是否已經提交過這個具體的 flag
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM flag_submissions 
                    WHERE submitter_team_id = ? AND flag_value = ?
                ''', (submitter_team_id, flag_value))
                
                if cursor.fetchone():
                    message = "This flag has already been submitted"
                else:
                    is_valid = True
                    message = "Flag accepted"
                conn.close()
        
        # 只記錄有效的提交（避免 NULL target_team_id）
        if is_valid and target_team_id is not None:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO flag_submissions 
                (submitter_team_id, target_team_id, round_id, flag_value, is_valid)
                VALUES (?, ?, ?, ?, ?)
            ''', (submitter_team_id, target_team_id, round_id, flag_value, is_valid))
            conn.commit()
            conn.close()
        
        return {
            'success': is_valid,
            'message': message,
            'target_team_id': target_team_id
        }
    
    def record_service_status(self, team_id: int, round_id: int, is_up: bool, 
                             response_time: float = None, error_message: str = None):
        """記錄服務狀態"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO service_status 
            (team_id, round_id, is_up, response_time, error_message)
            VALUES (?, ?, ?, ?, ?)
        ''', (team_id, round_id, is_up, response_time, error_message))
        conn.commit()
        conn.close()
    
    def get_service_status(self, round_id: int) -> List[Dict]:
        """獲取所有隊伍的最新服務狀態"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ss.* FROM service_status ss
            INNER JOIN (
                SELECT team_id, MAX(checked_at) as max_time
                FROM service_status
                WHERE round_id = ?
                GROUP BY team_id
            ) latest ON ss.team_id = latest.team_id AND ss.checked_at = latest.max_time
            WHERE ss.round_id = ?
        ''', (round_id, round_id))
        statuses = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return statuses
    
    def save_scores(self, team_id: int, round_id: int, sla_score: float, 
                   defense_score: float, attack_score: float):
        """保存分數"""
        total_score = sla_score + defense_score + attack_score
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO scores 
            (team_id, round_id, sla_score, defense_score, attack_score, total_score, calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (team_id, round_id, sla_score, defense_score, attack_score, total_score, datetime.now()))
        conn.commit()
        conn.close()
    
    def get_scoreboard(self) -> List[Dict]:
        """獲取總排行榜"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 獲取當前 Round
        cursor.execute('SELECT id FROM rounds WHERE status = "active" ORDER BY round_number DESC LIMIT 1')
        current_round = cursor.fetchone()
        round_id = current_round['id'] if current_round else None
        
        # 查詢排行榜，包含最新的服務狀態
        cursor.execute('''
            SELECT 
                t.id,
                t.name,
                COALESCE(SUM(s.sla_score), 0) as total_sla,
                COALESCE(SUM(s.defense_score), 0) as total_defense,
                COALESCE(SUM(s.attack_score), 0) as total_attack,
                COALESCE(SUM(s.total_score), 0) as total_score,
                COALESCE(
                    (SELECT is_up FROM service_status 
                     WHERE team_id = t.id AND round_id = ? 
                     ORDER BY checked_at DESC LIMIT 1), 
                    0
                ) as is_up
            FROM teams t
            LEFT JOIN scores s ON t.id = s.team_id
            GROUP BY t.id, t.name
            ORDER BY total_score DESC
        ''', (round_id,) if round_id else (None,))
        
        scoreboard = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return scoreboard
    
    def get_round_scores(self, round_id: int) -> List[Dict]:
        """獲取特定 Round 的分數"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.id, t.name, s.*
            FROM teams t
            LEFT JOIN scores s ON t.id = s.team_id AND s.round_id = ?
            ORDER BY COALESCE(s.total_score, 0) DESC
        ''', (round_id,))
        scores = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return scores
    
    def get_flag_steals(self, round_id: int) -> Dict[int, int]:
        """獲取每隊在本 Round 被竊取的次數"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT target_team_id, COUNT(*) as steal_count
            FROM flag_submissions
            WHERE round_id = ? AND is_valid = 1
            GROUP BY target_team_id
        ''', (round_id,))
        steals = {row['target_team_id']: row['steal_count'] for row in cursor.fetchall()}
        conn.close()
        return steals
    
    def get_attack_scores(self, round_id: int) -> Dict[int, int]:
        """獲取每隊在本 Round 的攻擊分數"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT submitter_team_id, COUNT(*) as attack_count
            FROM flag_submissions
            WHERE round_id = ? AND is_valid = 1
            GROUP BY submitter_team_id
        ''', (round_id,))
        attacks = {row['submitter_team_id']: row['attack_count'] for row in cursor.fetchall()}
        conn.close()
        return attacks
