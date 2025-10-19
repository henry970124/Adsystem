"""
Token 認證系統
生成並管理 Team Token 和 Admin Token
"""
import secrets
import hashlib
from typing import Dict, List

class TokenManager:
    def __init__(self):
        self.tokens = {}
        self.admin_token = None
        
    def generate_tokens(self, num_teams: int = 12) -> Dict[str, str]:
        """
        生成 Team Tokens 和 Admin Token
        
        Returns:
            {
                'admin': 'admin_token_xxx',
                'team1': 'team1_token_xxx',
                'team2': 'team2_token_xxx',
                ...
            }
        """
        tokens = {}
        
        # 生成 Admin Token
        admin_secret = secrets.token_hex(32)  # 64 字元
        self.admin_token = f"ADMIN_{admin_secret}"
        tokens['admin'] = self.admin_token
        
        # 生成 Team Tokens
        for i in range(1, num_teams + 1):
            team_id = f"team{i}"
            team_secret = secrets.token_hex(32)  # 64 字元
            team_token = f"TEAM{i}_{team_secret}"
            self.tokens[team_id] = team_token
            tokens[team_id] = team_token
        
        return tokens
    
    def validate_token(self, token: str) -> Dict:
        """
        驗證 Token 並返回身份信息
        
        Returns:
            {
                'valid': bool,
                'role': 'admin' | 'team',
                'team_id': str (僅 team 角色)
            }
        """
        # 檢查 Admin Token
        if token == self.admin_token:
            return {
                'valid': True,
                'role': 'admin',
                'team_id': None
            }
        
        # 檢查 Team Token
        for team_id, team_token in self.tokens.items():
            if token == team_token:
                return {
                    'valid': True,
                    'role': 'team',
                    'team_id': team_id
                }
        
        return {
            'valid': False,
            'role': None,
            'team_id': None
        }
    
    def get_team_from_token(self, token: str) -> str:
        """從 Token 獲取 Team ID"""
        result = self.validate_token(token)
        return result.get('team_id') if result['valid'] else None
    
    def is_admin(self, token: str) -> bool:
        """檢查是否為 Admin Token"""
        result = self.validate_token(token)
        return result['valid'] and result['role'] == 'admin'
