import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List
from models import Database
from zoneinfo import ZoneInfo

class FlagManager:
    def __init__(self, db: Database, flag_format: str = "FLAG{{{team_id}_{round}_{secret}}}"):
        self.db = db
        self.flag_format = flag_format
        self.vulnerability_types = ['monitor', 'logs', 'download']  # 三種漏洞類型
    
    def generate_flag(self, team_id: int, round_number: int, vuln_type: str = '') -> str:
        """生成唯一的 Flag（Hash 格式）"""
        # 生成隨機數據（加入漏洞類型確保不同）
        random_data = f"{team_id}_{round_number}_{vuln_type}_{secrets.token_hex(16)}_{datetime.now(tz=ZoneInfo('Asia/Taipei')).isoformat()}"
        # 使用 SHA256 生成 Hash
        flag_hash = hashlib.sha256(random_data.encode()).hexdigest()
        flag = self.flag_format.format(
            team_id=team_id,
            round=round_number,
            secret=flag_hash[:32]  # 使用前 32 個字元
        )
        return flag
    
    def create_flags_for_round(self, round_id: int, round_number: int, 
                               teams: List[Dict], flag_lifetime: int = None):
        """為所有隊伍生成本 Round 的 Flags（每個漏洞一個）"""
        # 不再使用過期時間，flags 在整個遊戲期間都有效
        flags = {}
        
        for team in teams:
            team_flags = {}
            for vuln_type in self.vulnerability_types:
                flag_value = self.generate_flag(team['id'], round_number, vuln_type)
                self.db.add_flag(team['id'], round_id, flag_value, None, vuln_type)
                team_flags[vuln_type] = flag_value
            flags[team['id']] = team_flags
        
        return flags
    
    def get_team_flag(self, team_id: int, round_id: int, vuln_type: str = 'monitor') -> str:
        """獲取特定隊伍在特定 Round 的特定漏洞的 Flag"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT flag_value FROM flags WHERE team_id = ? AND round_id = ? AND vuln_type = ?',
            (team_id, round_id, vuln_type)
        )
        result = cursor.fetchone()
        conn.close()
        return result['flag_value'] if result else None
    
    def get_team_all_flags(self, team_id: int, round_id: int) -> Dict[str, str]:
        """獲取特定隊伍在特定 Round 的所有 Flag"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT vuln_type, flag_value FROM flags WHERE team_id = ? AND round_id = ?',
            (team_id, round_id)
        )
        results = cursor.fetchall()
        conn.close()
        return {row['vuln_type']: row['flag_value'] for row in results} if results else {}
