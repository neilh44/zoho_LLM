import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime
from typing import Dict, Any, List
from groq import Groq
import re

class ZohoResponseProcessor:
    def __init__(self):
        """Initialize the Zoho Response Processor"""
        # Initialize Groq client
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")
        self.groq_client = Groq(api_key=api_key)
        
        # Setup logging
        self.logger = self._setup_logging()
        
    def _setup_logging(self):
        """Set up basic logging configuration"""
        logger = logging.getLogger('ZohoResponse')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            os.makedirs('logs', exist_ok=True)
            handler = RotatingFileHandler(
                'logs/zoho_analysis.log',
                maxBytes=10*1024*1024,
                backupCount=5
            )
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger

    def _clean_and_structure_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Clean and structure the data"""
        # Extract the data array from the response
        data = raw_data.get('data', [])
        if not data:
            return []
            
        return data

    def _format_currency(self, amount: Any) -> str:
        """Format numeric values as currency"""
        try:
            value = float(amount)
            return f"${value:,.2f}"
        except (ValueError, TypeError):
            return str(amount)

    def process_response(
            self, 
            zoho_response: Dict[str, Any], 
            natural_query: str, 
            coql_query: str
        ) -> Dict[str, Any]:
        """Process Zoho CRM response using LLM analysis"""
        try:
            self.logger.info(f"Processing Zoho response for query: {natural_query}")
            
            # Clean and structure the data
            structured_data = self._clean_and_structure_data(zoho_response)
            
            if not structured_data:
                return {
                    'status': 'error',
                    'message': 'No data found in response'
                }

            # Format the data for better readability
            formatted_data = []
            for record in structured_data:
                formatted_record = {}
                for key, value in record.items():
                    if any(term in key.lower() for term in ['amount', 'value', 'price', 'revenue']):
                        formatted_record[key] = self._format_currency(value)
                    else:
                        formatted_record[key] = value
                formatted_data.append(formatted_record)

            # Create prompts for both tabular and narrative responses
            narrative_prompt = f"""
            Please analyze this query and its results, and provide a clear explanation in natural language.
            Focus on telling the story of what the data shows in complete sentences.

            Query: {natural_query}
            SQL Query: {coql_query}
            Results: {formatted_data}

            Provide a response that:
            1. Summarizes what was queried
            2. Describes the results found
            3. Includes specific details like names, amounts where relevant
            4. Uses complete sentences and natural language
            5. Do not include statement like "Here is the analysis of the query and its results" before the start of sentence.

            Example style of response:
            "The query retrieved deals in the 'Value Proposition' stage. There is one deal in this stage: a deal named 'Example Corp' with a value of $50,000. This indicates that Example Corp is actively engaged in discussions about the product's value proposition. The deal has a unique identifier of 12345 for tracking purposes."
            """

            tabular_prompt = f"""
            Please analyze this query and its results, and organize the information in a clear, tabular format.
            Present the key data points in a structured way that's easy to read.

            Query: {natural_query}
            SQL Query: {coql_query}
            Results: {formatted_data}

            Format the response as a markdown table with headers and properly aligned columns.
            """

            # Get both types of analysis
            try:
                narrative_completion = self.groq_client.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[{"role": "user", "content": narrative_prompt}],
                    temperature=0.1,
                    max_tokens=1000
                )
                narrative_analysis = narrative_completion.choices[0].message.content.strip()

                tabular_completion = self.groq_client.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[{"role": "user", "content": tabular_prompt}],
                    temperature=0.1,
                    max_tokens=1000
                )
                tabular_analysis = tabular_completion.choices[0].message.content.strip()
                
            except Exception as e:
                self.logger.error(f"Error in LLM analysis: {str(e)}")
                return {
                    'status': 'error',
                    'message': 'Failed to generate analysis'
                }

            # Return structured response with both formats
            return {
                'status': 'success',
                'query': {
                    'natural': natural_query,
                    'coql': coql_query
                },
                'analysis': {
                    'narrative': narrative_analysis,
                    'tabular': tabular_analysis
                },
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'record_count': len(structured_data)
                }
            }

        except Exception as e:
            self.logger.error(f"Error in process_response: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'query': {
                    'natural': natural_query,
                    'coql': coql_query
                }
            }