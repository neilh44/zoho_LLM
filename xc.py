import requests
import json
from typing import Dict, Any, Optional

class ZohoCRMHandler:
    def __init__(self, refresh_token: str, client_id: str, client_secret: str):
        """Initialize with your OAuth credentials"""
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.base_url = "https://www.zohoapis.in"
        
    def refresh_access_token(self) -> str:
        """Get new access token using refresh token"""
        url = "https://accounts.zoho.in/oauth/v2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token"
        }
        
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            token_info = response.json()
            self.access_token = token_info['access_token']
            return self.access_token
        except requests.exceptions.RequestException as e:
            print(f"Error refreshing token: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Error details: {e.response.text}")
            raise

    def execute_coql(self, query: str) -> Dict[str, Any]:
        """Execute a COQL query"""
        if not self.access_token:
            self.refresh_access_token()
            
        url = f"{self.base_url}/crm/v4/coql"
        headers = {
            "Authorization": f"Zoho-oauthtoken {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {"select_query": query}

        try:
            response = requests.post(url, headers=headers, json=payload)
            
            # If token expired, refresh and retry once
            if response.status_code == 401:
                print("Token expired, refreshing...")
                self.refresh_access_token()
                headers["Authorization"] = f"Zoho-oauthtoken {self.access_token}"
                response = requests.post(url, headers=headers, json=payload)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error executing query: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Error details: {e.response.text}")
            raise

def main():
    # Your Zoho credentials
    CREDENTIALS = {
        "client_id": "1000.OADXPQO0SDC4R4YBLOQ0XB1H2UMAVE",
        "client_secret": "c8d64d1c8926951cee2444729a1b55e9a40492c97f",
        "refresh_token": "1000.ee86048feee7a2d1801f3af84beea830.db88bd9924d483141906dd924bbc03af"
    }

    # Initialize handler
    zoho = ZohoCRMHandler(**CREDENTIALS)

    # Example COQL queries
    queries = [
        """
        SELECT First_Name, Last_Name, Email, Phone 
        FROM Leads 
        WHERE Created_Time >= '2024-01-01' 
        LIMIT 5
        """,
        """
        SELECT Deal_Name, Amount, Stage, Closing_Date 
        FROM Deals 
        WHERE Amount > 10000 
        ORDER BY Amount DESC 
        LIMIT 5
        """
    ]

    # Execute each query
    for query in queries:
        try:
            print(f"\nExecuting query:\n{query.strip()}\n")
            results = zoho.execute_coql(query.strip())
            print("Results:")
            print(json.dumps(results, indent=2))
            
        except Exception as e:
            print(f"Query failed: {str(e)}")
            continue

if __name__ == "__main__":
    main()