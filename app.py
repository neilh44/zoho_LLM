from flask import Flask, render_template, request, jsonify
from natural_to_coql import NaturalToCoqlConverter
from zoho_coql_executor import ZohoCoqlExecutor
from zoho_response_processor import ZohoResponseProcessor
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import os
import traceback

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Set up logging
def setup_logging():
    logger = logging.getLogger('zoho_app')
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        os.makedirs('logs', exist_ok=True)
        handler = RotatingFileHandler(
            'logs/app.log',
            maxBytes=10*1024*1024,
            backupCount=5
        )
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # Also add console handler for development
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# Initialize services with better error handling
def initialize_services():
    try:
        converter = NaturalToCoqlConverter()
        logger.info("Successfully initialized COQL converter")
    except Exception as e:
        logger.error(f"Failed to initialize COQL converter: {str(e)}\n{traceback.format_exc()}")
        raise

    try:
        executor = ZohoCoqlExecutor()
        logger.info("Successfully initialized Zoho executor")
    except Exception as e:
        logger.error(f"Failed to initialize Zoho executor: {str(e)}\n{traceback.format_exc()}")
        raise
        
    try:
        processor = ZohoResponseProcessor()
        logger.info("Successfully initialized Zoho response processor")
    except Exception as e:
        logger.error(f"Failed to initialize Zoho response processor: {str(e)}\n{traceback.format_exc()}")
        raise
        
    return converter, executor, processor

# Initialize services
try:
    converter, executor, processor = initialize_services()
except Exception as e:
    logger.error(f"Critical error during service initialization: {str(e)}")
    raise

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/query', methods=['POST'])
def query():
    try:
        data = request.get_json()
        if not data:
            data = request.form

        # Get natural language query from request
        natural_query = data.get('natural_query')
        if not natural_query:
            return jsonify({'error': 'No query provided'}), 400
            
        logger.info(f"Received natural language query: {natural_query}")
            
        # Convert natural language to COQL
        try:
            conversion_result = converter.convert_to_coql(natural_query)
            coql_query = conversion_result.get('select_query')
            
            if not coql_query:
                return jsonify({'error': 'Failed to generate COQL query'}), 400
                
            logger.info(f"Generated COQL query: {coql_query}")
            
        except Exception as e:
            logger.error(f"Error during query conversion: {str(e)}\n{traceback.format_exc()}")
            return jsonify({'error': 'Failed to convert natural language to COQL'}), 400
        
        # Execute COQL query against Zoho CRM
        try:
            zoho_response = executor.execute_coql({'select_query': coql_query})
            logger.info("Successfully executed COQL query")
            
        except Exception as e:
            logger.error(f"Error during query execution: {str(e)}\n{traceback.format_exc()}")
            return jsonify({'error': 'Failed to execute query in Zoho CRM'}), 400

        # Process response with enhanced analysis
        try:
            # Extract data from Zoho response
            data = zoho_response.get('data', [])
            
            if not data:
                return jsonify({
                    'status': 'error',
                    'message': 'No data found in Zoho response',
                    'query': {
                        'natural': natural_query,
                        'coql': coql_query
                    }
                })

            # Process the response using ZohoResponseProcessor
            processed_response = processor.process_response(
                zoho_response=zoho_response,
                natural_query=natural_query,
                coql_query=coql_query
            )
            
            logger.info("Successfully processed response with enhanced analysis")
            return jsonify(processed_response)
            
        except Exception as e:
            logger.error(f"Error during response processing: {str(e)}\n{traceback.format_exc()}")
            return jsonify({
                'error': 'Failed to process query response',
                'details': str(e)
            }), 400
            
    except ValueError as ve:
        logger.error(f"Validation error: {str(ve)}")
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'An unexpected error occurred'}), 500


@app.route('/health')
def health_check():
    """Simple health check endpoint that verifies all services are running"""
    try:
        health_status = {
            'status': 'healthy',
            'services': {
                'converter': converter is not None,
                'executor': executor is not None,
                'processor': processor is not None
            }
        }
        return jsonify(health_status), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(e)}\n{traceback.format_exc()}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true')