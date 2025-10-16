"""
HTTP server module for serving Prometheus metrics from AFS data.

This module implements a Flask-based HTTP server that exposes AFS storage
metrics through a /metrics endpoint compatible with Prometheus scraping.
"""

import time
from typing import Optional
from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import RequestTimeout

from src.afs_client import AFSClient
from src.metrics_transformer import MetricsTransformer
from src.metrics_handler import MetricsHandler
from src.config import Config
from src.exceptions import AuthenticationError, APIError
from src.logging_config import get_logger, log_operation


class MetricsServer:
    """
    Flask-based HTTP server for serving Prometheus metrics.
    
    This server provides:
    - /metrics endpoint for Prometheus scraping
    """
    
    def __init__(self, config: Config, metrics_handler: MetricsHandler):
        """
        Initialize the metrics server.
        
        Args:
            config: Configuration object
            metrics_handler: Metrics handler for orchestrating data collection
        """
        self.config = config
        self.metrics_handler = metrics_handler
        self.logger = get_logger(__name__)
        
        # Initialize Flask app
        self.app = Flask(__name__)
        self.app.config['REQUEST_TIMEOUT'] = config.get_server_config().request_timeout
        
        # Register routes
        self._register_routes()
        
        # Configure request timeout handling
        self._configure_timeout_handling()
    
    def _register_routes(self) -> None:
        """Register HTTP routes for the server."""
        
        @self.app.route('/metrics', methods=['GET'])
        def metrics_endpoint():
            """
            Prometheus metrics endpoint.
            
            Returns real-time AFS storage metrics in Prometheus format.
            """
            return self._handle_metrics_request()
        
        @self.app.errorhandler(RequestTimeout)
        def handle_timeout(error):
            """Handle request timeout errors."""
            self.logger.set_context(endpoint=request.path, client_ip=request.remote_addr)
            self.logger.error(f"Request timeout: {str(error)[:200]}")
            self.logger.clear_context()
            return jsonify({
                'error': 'Request timeout',
                'message': 'The request took too long to process'
            }), 408
        
        @self.app.errorhandler(500)
        def handle_internal_error(error):
            """Handle internal server errors."""
            self.logger.set_context(endpoint=request.path, client_ip=request.remote_addr)
            self.logger.error(f"Internal server error: {str(error)[:200]}")
            self.logger.clear_context()
            return jsonify({
                'error': 'Internal server error',
                'message': 'An unexpected error occurred'
            }), 500
    
    def _configure_timeout_handling(self) -> None:
        """Configure request timeout handling."""
        
        @self.app.before_request
        def before_request():
            """Set up request timeout and logging context."""
            request.start_time = time.time()
            self.logger.set_context(
                endpoint=request.path,
                method=request.method,
                client_ip=request.remote_addr,
                user_agent=request.headers.get('User-Agent', 'Unknown')[:100]
            )
        
        @self.app.after_request
        def after_request(response):
            """Log request completion."""
            if hasattr(request, 'start_time'):
                duration = time.time() - request.start_time
                self.logger.info(f"Request completed - status: {response.status_code}, duration: {duration:.3f}s")
            self.logger.clear_context()
            return response
    
    def _handle_metrics_request(self) -> Response:
        """
        Handle requests to the /metrics endpoint.
        
        Returns:
            Flask Response with Prometheus metrics in text format
        """
        try:
            with log_operation(self.logger, "metrics request processing", level='DEBUG'):
                # Collect metrics using the metrics handler (with caching)
                metrics, collection_duration = self.metrics_handler.collect_metrics()
                
                # Format metrics in Prometheus exposition format
                metrics_text = self.metrics_handler.transformer.format_prometheus_metrics(metrics)
                
                # Log cache status for debugging
                cache_status = self.metrics_handler.get_cache_status()
                cache_info = "cached" if cache_status['cached'] else "fresh"
                
                self.logger.info(f"Returned {len(metrics)} metrics ({cache_info}) - "
                               f"collection: {collection_duration:.3f}s, "
                               f"response_size: {len(metrics_text)} bytes")
                
                return Response(
                    metrics_text,
                    mimetype='text/plain; version=0.0.4; charset=utf-8',
                    status=200
                )
                
        except Exception as e:
            error_msg = str(e)[:200]
            self.logger.error(f"Error processing metrics request: {error_msg}")
            
            # Create simple error response
            error_text = f"# Error collecting metrics: {error_msg}\n"
            return Response(
                error_text,
                mimetype='text/plain; version=0.0.4; charset=utf-8',
                status=500
            )
    

    

    
    def start_server(self, debug: bool = False) -> None:
        """
        Start the HTTP server.
        
        Args:
            debug: Enable Flask debug mode
        """
        server_config = self.config.get_server_config()
        
        self.logger.set_context(
            host=server_config.host,
            port=server_config.port,
            operation='start_server'
        )
        
        try:
            with log_operation(self.logger, f"HTTP server startup on {server_config.host}:{server_config.port}", level='INFO'):
                self.app.run(
                    host=server_config.host,
                    port=server_config.port,
                    debug=debug,
                    threaded=True  # Enable threading for concurrent requests
                )
        except Exception as e:
            self.logger.error(f"Failed to start HTTP server: {str(e)[:200]}")
            raise
        finally:
            self.logger.clear_context()
    
    def get_app(self) -> Flask:
        """
        Get the Flask application instance.
        
        Returns:
            Flask application instance
        """
        return self.app