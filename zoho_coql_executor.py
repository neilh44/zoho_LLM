import json
import logging
import requests
import os
from typing import Dict, Any
from logging.handlers import RotatingFileHandler

class ZohoCoqlExecutor:
    def __init__(self):
        # Initialize logging
        self.logger = logging.getLogger(self.__class__.__name__)
        self._setup_logging()
        
        # Hardcoded credentials
        CREDENTIALS = {
            "client_id": "1000.OADXPQO0SDC4R4YBLOQ0XB1H2UMAVE",
            "client_secret": "c8d64d1c8926951cee2444729a1b55e9a40492c97f",
            "refresh_token": "1000.0adbfa72e9c001a172d6fa5a3116e9a3.42dfad3af49661566127fa46806e4dec"
        }
        
        # Initialize with credentials
        self.client_id = CREDENTIALS["client_id"]
        self.client_secret = CREDENTIALS["client_secret"]
        self.refresh_token = CREDENTIALS["refresh_token"]
        self.access_token = None
        self.base_url = "https://www.zohoapis.in"
        self.logger.info("ZohoCoqlExecutor initialized successfully")

    def _setup_logging(self):
        """Set up logging configuration"""
        self.logger.setLevel(logging.DEBUG)  # Changed to DEBUG for more detailed logging
        
        if not self.logger.handlers:
            os.makedirs('logs', exist_ok=True)
            
            # File handler for all levels
            file_handler = RotatingFileHandler(
                'logs/zoho_executor.log',
                maxBytes=10*1024*1024,
                backupCount=5
            )
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
            
            # Add console handler for immediate feedback
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter('%(levelname)s - %(message)s')
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

    def _log_request_details(self, method: str, url: str, headers: Dict, payload: Dict = None):
        """Log detailed request information"""
        self.logger.debug(f"Request Method: {method}")
        self.logger.debug(f"Request URL: {url}")
        
        # Log headers excluding sensitive information
        safe_headers = headers.copy()
        if 'Authorization' in safe_headers:
            safe_headers['Authorization'] = 'REDACTED'
        self.logger.debug(f"Request Headers: {json.dumps(safe_headers, indent=2)}")
        
        if payload:
            self.logger.debug(f"Request Payload: {json.dumps(payload, indent=2)}")

    def _log_response_details(self, response: requests.Response):
        """Log detailed response information"""
        self.logger.debug(f"Response Status Code: {response.status_code}")
        self.logger.debug(f"Response Headers: {json.dumps(dict(response.headers), indent=2)}")
        
        try:
            response_json = response.json()
            self.logger.debug(f"Response Body: {json.dumps(response_json, indent=2)}")
        except json.JSONDecodeError:
            self.logger.debug(f"Response Text: {response.text}")

    def _refresh_access_token(self) -> str:
        """Get new access token using refresh token"""
        self.logger.info("Refreshing access token")
        url = "https://accounts.zoho.in/oauth/v2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token"
        }
        
        try:
            self.logger.debug("Making token refresh request")
            self._log_request_details("POST", url, {}, params)
            
            response = requests.post(url, params=params)
            self._log_response_details(response)
            
            response.raise_for_status()
            token_info = response.json()
            self.access_token = token_info['access_token']
            self.logger.info("Access token refreshed successfully")
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error refreshing token: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error(f"Response status code: {e.response.status_code}")
                self.logger.error(f"Response headers: {json.dumps(dict(e.response.headers), indent=2)}")
                self.logger.error(f"Response body: {e.response.text}")
            self.logger.error(error_msg, exc_info=True)
            raise

    def execute_coql(self, query_dict: Dict[str, str]) -> Dict[str, Any]:
        """Execute a COQL query"""
        # Enable debug logging for requests
        import http.client as http_client
        http_client.HTTPConnection.debuglevel = 1
        
        # Create requests session with logging
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True
        
        # Extract and validate the query string
        query = query_dict.get('select_query')
        if not query:
            self.logger.error("Missing required 'select_query' in query_dict")
            raise ValueError("Select query is required")
        
        self.logger.debug(f"Processing COQL query: {query.strip()}")
            
        if not self.access_token:
            self._refresh_access_token()
            
        url = f"{self.base_url}/crm/v4/coql"
        headers = {
            "Authorization": f"Zoho-oauthtoken {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {"select_query": query}

        try:
            self.logger.info("Executing COQL query")
            self._log_request_details("POST", url, headers, payload)
            
            # Log the exact request being made
            self.logger.debug(f"Making request to URL: {url}")
            self.logger.debug(f"Request headers: {headers}")
            self.logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
            
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                self.logger.debug(f"Raw response status: {response.status_code}")
                self.logger.debug(f"Raw response headers: {response.headers}")
                self.logger.debug(f"Raw response content: {response.content.decode('utf-8')}")
                self._log_response_details(response)
            except requests.exceptions.RequestException as req_err:
                self.logger.error(f"Request failed with error: {str(req_err)}")
                raise
            
            # If token expired, refresh and retry once
            if response.status_code == 401:
                self.logger.info("Token expired, refreshing and retrying")
                self._refresh_access_token()
                headers["Authorization"] = f"Zoho-oauthtoken {self.access_token}"
                
                self.logger.info("Retrying COQL query with new token")
                self._log_request_details("POST", url, headers, payload)
                
                response = requests.post(url, headers=headers, json=payload)
                self._log_response_details(response)
            
            # Specific handling for 400 errors
            if response.status_code == 400:
                self.logger.error("400 Bad Request Error")
                self.logger.error(f"Query that caused error: {query.strip()}")
                try:
                    error_details = response.json()
                    self.logger.error(f"Error details from Zoho: {json.dumps(error_details, indent=2)}")
                except json.JSONDecodeError:
                    self.logger.error(f"Raw error response: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            self.logger.info("Query executed successfully")
            return result
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error executing query: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error(f"Response status code: {e.response.status_code}")
                self.logger.error(f"Response headers: {json.dumps(dict(e.response.headers), indent=2)}")
                try:
                    error_response = e.response.json()
                    self.logger.error(f"Detailed error response: {json.dumps(error_response, indent=2)}")
                    if 'code' in error_response:
                        self.logger.error(f"Error code: {error_response['code']}")
                    if 'details' in error_response:
                        self.logger.error(f"Error details: {error_response['details']}")
                    if 'message' in error_response:
                        self.logger.error(f"Error message: {error_response['message']}")
                except json.JSONDecodeError:
                    self.logger.error(f"Raw error response: {e.response.text}")
                
            self.logger.error(error_msg, exc_info=True)
            self.logger.error(f"Query that caused error: {query.strip()}")  # Log the problematic query
            raise

def main():
    """Example usage of ZohoCoqlExecutor"""
    try:
        executor = ZohoCoqlExecutor()
        
        # Example query
        query = {
            "select_query": """
                SELECT First_Name, Last_Name, Email, Phone 
                FROM Leads 
                WHERE Created_Time >= '2024-01-01' 
                LIMIT 5
            """
        }
        
        results = executor.execute_coql(query)
        print("Results:")
        print(json.dumps(results, indent=2))
        
    except Exception as e:
        logging.error("Error in main function", exc_info=True)
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()