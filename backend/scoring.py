from typing import Dict, List
from models import Database
import logging

logger = logging.getLogger(__name__)

class ScoringEngine:
    def __init__(self, db: Database, config: Dict):
        self.db = db
        self.config = config
        self.num_teams = config['game']['num_teams']
        self.sla_total_pool = config['scoring']['sla_total_pool']  # 512
        self.base_defense_score = config['scoring']['base_defense_score']  # 12
        self.attack_score_per_flag = config['scoring']['attack_score_per_flag']  # 1
        self.defense_penalty = config['scoring']['defense_penalty_per_steal']  # 1
    
    def calculate_sla_score(self, team_id: int, service_status: Dict[int, bool]) -> float:
        """
        計算服務在線分數 (SLA Score)
        規則：512 總分池 / 在線隊伍數
        例如：12 隊都在線 -> 512/12 = 42.67 分/隊
              4 隊在線 -> 512/4 = 128 分/隊
        """
        # 只有在線的隊伍才能獲得分數
        if not service_status.get(team_id, False):
            logger.info(f"Team {team_id}: Service DOWN, SLA = 0")
            return 0.0
        
        # 計算有多少隊伍在線
        online_teams = sum(1 for is_up in service_status.values() if is_up)
        
        if online_teams == 0:
            return 0.0
        
        # SLA分數 = 512 / 在線隊伍數
        sla_score = self.sla_total_pool / online_teams
        
        logger.info(f"Team {team_id}: SLA = {sla_score:.2f} ({online_teams} teams online)")
        return round(sla_score, 2)
    
    def calculate_defense_score(self, team_id: int, flag_steals: Dict[int, int]) -> float:
        """
        計算防禦分數 (Defense Score)
        規則：基礎分 12 分
             每被一個隊伍偷到 flag 就 -1 分
             例如：沒人偷到 = 12 分
                  1 隊偷到 = 11 分
                  11 隊都偷到 = 1 分
                  12 隊都偷到 = 0 分（理論上不會發生，因為不能偷自己的）
        """
        steals = flag_steals.get(team_id, 0)
        defense_score = self.base_defense_score - (steals * self.defense_penalty)
        
        # 最低 0 分
        defense_score = max(defense_score, 0)
        
        logger.info(f"Team {team_id}: Defense = {defense_score:.2f} (stolen by {steals} teams)")
        return round(defense_score, 2)
    
    def calculate_attack_score(self, team_id: int, attack_counts: Dict[int, int]) -> float:
        """
        計算攻擊分數 (Attack Score)
        規則：每成功偷到一個其他隊伍的 flag = +1 分
             例如：偷到 11 個隊伍的 flag = 11 分
                  偷到 5 個隊伍的 flag = 5 分
        """
        attacks = attack_counts.get(team_id, 0)
        attack_score = attacks * self.attack_score_per_flag
        
        logger.info(f"Team {team_id}: Attack = {attack_score:.2f} (captured {attacks} flags)")
        return round(attack_score, 2)
    
    def calculate_round_scores(self, round_id: int):
        """
        計算本 Round 所有隊伍的分數
        """
        teams = self.db.get_teams()
        
        # 獲取服務狀態
        service_statuses = self.db.get_service_status(round_id)
        service_status_map = {s['team_id']: s['is_up'] for s in service_statuses}
        
        # 獲取 flag 竊取統計
        flag_steals = self.db.get_flag_steals(round_id)
        
        # 獲取攻擊統計
        attack_counts = self.db.get_attack_scores(round_id)
        
        logger.info(f"=== Calculating scores for Round {round_id} ===")
        logger.info(f"Service Status: {service_status_map}")
        logger.info(f"Flag Steals: {flag_steals}")
        logger.info(f"Attack Counts: {attack_counts}")
        
        # 計算每個隊伍的分數
        for team in teams:
            team_id = team['id']
            
            # 計算各項分數
            sla_score = self.calculate_sla_score(team_id, service_status_map)
            defense_score = self.calculate_defense_score(team_id, flag_steals)
            attack_score = self.calculate_attack_score(team_id, attack_counts)
            
            # 保存到資料庫
            self.db.save_scores(
                team_id=team_id,
                round_id=round_id,
                sla_score=sla_score,
                defense_score=defense_score,
                attack_score=attack_score
            )
            
            total = sla_score + defense_score + attack_score
            logger.info(
                f"Team {team_id} ({team['name']}): "
                f"SLA={sla_score}, Defense={defense_score}, Attack={attack_score}, Total={total}"
            )
        
        logger.info(f"=== Round {round_id} scoring complete ===")
    
    def get_scoreboard_summary(self) -> Dict:
        """
        獲取排行榜摘要
        """
        scoreboard = self.db.get_scoreboard()
        current_round = self.db.get_current_round()
        
        return {
            'current_round': current_round['round_number'] if current_round else 0,
            'teams': scoreboard,
            'total_teams': len(scoreboard)
        }
