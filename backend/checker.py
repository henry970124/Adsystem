import requests
import time
from typing import Dict, List, Tuple
from models import Database
import logging

logger = logging.getLogger(__name__)

class ServiceChecker:
    def __init__(self, db: Database, timeout: int = 5):
        self.db = db
        self.timeout = timeout

    def check_endpoint_functionality(self, url: str, endpoint: str) -> Tuple[bool, str]:
        """
        檢查單一端點的功能性 - 測試實際功能是否可用
        返回: (是否正常, 錯誤訊息)
        """
        try:
            # 根據不同端點測試不同功能
            if endpoint == '/files':
                # 測試檔案列表功能
                response = requests.get(f"{url}/files", timeout=self.timeout)
                if response.status_code != 200:
                    return False, f"HTTP {response.status_code}"
                # 檢查是否有檔案列表內容
                if len(response.text) < 100:
                    return False, "No file listing"
                return True, None
                
            elif endpoint == '/logs':
                # 測試日誌搜尋功能 - 發送 POST 請求測試搜尋
                response = requests.post(
                    f"{url}/logs",
                    data={'keyword': 'test'},
                    timeout=self.timeout
                )
                if response.status_code != 200:
                    return False, f"HTTP {response.status_code}"
                # 檢查搜尋功能是否回應
                if len(response.text) < 100:
                    return False, "Search not working"
                return True, None
                
            elif endpoint == '/monitor':
                # 測試監控功能 - 發送 POST 請求測試 dig 指令
                response = requests.post(
                    f"{url}/monitor",
                    data={'host': 'localhost'},
                    timeout=self.timeout
                )
                if response.status_code != 200:
                    return False, f"HTTP {response.status_code}"
                # 檢查監控指令是否有輸出
                if len(response.text) < 100:
                    return False, "Monitor command not working"
                return True, None
            
            return False, "Unknown endpoint"
            
        except requests.exceptions.Timeout:
            return False, "Timeout"
        except requests.exceptions.ConnectionError:
            return False, "Connection refused"
        except Exception as e:
            return False, str(e)

    def check_service(self, team_id: int, host: str, port: int, round_id: int = None) -> Tuple[bool, float, str]:
        """
        檢查單一服務狀態 - 測試三個端點的實際功能
        返回: (是否在線, 響應時間, 錯誤訊息)
        """
        base_url = f"http://{host}:{port}"
        start_time = time.time()

        # 需要測試的三個端點
        endpoints = [
            '/files',     # 檔案列表功能
            '/logs',      # 日誌搜尋功能
            '/monitor'    # 監控指令功能
        ]

        successful_checks = 0
        errors = []

        try:
            # 測試每個端點的實際功能
            for endpoint in endpoints:
                is_ok, error_msg = self.check_endpoint_functionality(base_url, endpoint)
                
                if is_ok:
                    successful_checks += 1
                else:
                    errors.append(f"{endpoint}: {error_msg}")

            response_time = time.time() - start_time

            # 如果至少有2個端點功能正常，認為服務在線
            is_up = successful_checks >= 2

            if is_up:
                if successful_checks == 3:
                    error_msg = None
                else:
                    error_msg = f"Partial ({successful_checks}/3): {'; '.join(errors)}"
            else:
                error_msg = f"Failed ({successful_checks}/3): {'; '.join(errors)}"

            logger.info(f"Team {team_id} service check: {successful_checks}/3 endpoints functional")

            return is_up, response_time, error_msg

        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"Team {team_id} check exception: {e}")
            return False, response_time, f"Check failed: {str(e)}"

    def check_all_services(self, teams: List[Dict], round_id: int) -> Dict[int, bool]:
        """
        檢查所有隊伍的服務狀態
        返回: {team_id: is_up}
        """
        results = {}

        for team in teams:
            team_id = team['id']
            host = team['host']
            port = team['port']

            is_up, response_time, error_msg = self.check_service(team_id, host, port, round_id)

            # 記錄到資料庫
            self.db.record_service_status(
                team_id=team_id,
                round_id=round_id,
                is_up=is_up,
                response_time=response_time,
                error_message=error_msg
            )

            results[team_id] = is_up

            status = "UP" if is_up else "DOWN"
            logger.info(f"Team {team_id} ({host}:{port}): {status} - {response_time:.2f}s")
            if error_msg:
                logger.warning(f"Team {team_id} status: {error_msg}")

        return results
