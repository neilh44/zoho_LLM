import os
import json
import logging
from typing import Dict, Any
from groq import Groq
from logging.handlers import RotatingFileHandler

class NaturalToCoqlConverter:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._setup_logging()
        
        # Initialize Groq client
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")
            
        self.groq_client = Groq(api_key=api_key)

    def _setup_logging(self):
        """Set up logging configuration"""
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            os.makedirs('logs', exist_ok=True)
            handler = RotatingFileHandler(
                'logs/coql_converter.log',
                maxBytes=10*1024*1024,
                backupCount=5
            )
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Parse and validate the LLM response to ensure it returns valid COQL JSON
        """
        try:
            # Clean up any potential markdown formatting
            cleaned_response = response.replace('```json', '').replace('```', '').strip()
            
            # Try to parse as JSON
            query_data = json.loads(cleaned_response)
            
            # Handle both possible response formats (direct dict or dict in array)
            if isinstance(query_data, list):
                if not query_data:
                    raise ValueError("Empty response array")
                query_data = query_data[0]
            
            if not isinstance(query_data, dict):
                raise ValueError(f"Expected dict, got {type(query_data)}")
                
            if "select_query" not in query_data:
                raise ValueError("Response missing required 'select_query' field")
                
            return query_data
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON response: {str(e)}")
            raise ValueError(f"Invalid JSON response: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error parsing LLM response: {str(e)}")
            raise

    def convert_to_coql(self, natural_query: str) -> Dict[str, Any]:
        """Convert natural language to Zoho COQL query format"""
        system_prompt = """
        You are a Zoho CRM COQL expert. Convert natural language to COQL (CRM Object Query Language) queries.
        
        Always return a JSON object with a "select_query" key containing the COQL query string.
        
        Key COQL rules to follow:
        1. SELECT can specify up to 50 field API names
        2. WHERE can include up to 25 criteria
        3. Maximum LIMIT is 2000
        4. JOINs through lookup fields MUST use dot notation
        5. Maximum of two JOINs allowed (e.g., field.lookup1.lookup2)
        6. Keywords are not case-sensitive except for aggregate functions
        7. Default sorting is by record ID ascending
        8. Special characters and SQL reserved words must be enclosed in quotes
        9. When using lookup fields:
           - Account_Name returns just the ID
           - Account_Name.Account_Name returns the actual name
        10. For simple queries without specific fields, use common fields like:
            - Contacts: Last_Name, First_Name, Email, Phone, Account_Name.Account_Name
            - Leads: Last_Name, Company, Email, Phone, Lead_Status
            - Deals: Deal_Name, Amount, Stage, Closing_Date, Account_Name.Account_Name
        
        Example response format:
        {"select_query": "select Last_Name, Email from Contacts where Last_Name is not null limit 100"}
        """
        
        try:
            user_prompt = f"Convert this natural language query to Zoho COQL. Return ONLY valid JSON with the COQL query, no other text: {natural_query}"
            
            completion = self.groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )

            response = completion.choices[0].message.content.strip()
            self.logger.info(f"Raw LLM response: {response}")

            # Parse and validate the response
            query_data = self._parse_llm_response(response)
            
            # Validate the COQL query
            if not self.validate_coql_query(query_data["select_query"]):
                raise ValueError("Generated COQL query failed validation")

            return query_data

        except Exception as e:
            self.logger.error(f"Error in COQL query conversion: {str(e)}")
            raise

    def validate_coql_query(self, query: str) -> bool:
        """
        Validate COQL query against basic rules
        Returns True if valid, raises ValueError with specific error if invalid
        """
        try:
            # Check for required clauses
            if not query.lower().startswith('select'):
                raise ValueError("Query must start with SELECT")
            
            if 'from' not in query.lower():
                raise ValueError("Query must contain FROM clause")

            # Check field limit in SELECT
            select_part = query.lower().split('from')[0].replace('select', '').strip()
            fields = [f.strip() for f in select_part.split(',')]
            if len(fields) > 50:
                raise ValueError("SELECT clause cannot have more than 50 fields")

            # Check criteria limit in WHERE
            if 'where' in query.lower():
                where_part = query.lower().split('where')[1].split('order by')[0].split('group by')[0].split('limit')[0]
                criteria_count = where_part.count('and') + where_part.count('or') + 1
                if criteria_count > 25:
                    raise ValueError("WHERE clause cannot have more than 25 criteria")

            # Check LIMIT value
            if 'limit' in query.lower():
                limit_part = query.lower().split('limit')[1].strip().split()[0]
                if int(limit_part) > 2000:
                    raise ValueError("LIMIT cannot exceed 2000")

            # Check JOIN depth
            dot_counts = [field.count('.') for field in fields]
            if max(dot_counts, default=0) > 2:
                raise ValueError("Maximum of two JOINs allowed")

            return True

        except Exception as e:
            self.logger.error(f"COQL validation error: {str(e)}")
            raise ValueError(f"Invalid COQL query: {str(e)}")
