#!/usr/bin/env python3
"""
Main entry point for AFS Prometheus metrics collector server.

This script initializes the configuration, sets up logging, creates the
necessary components, and starts the HTTP server.
"""

import sys
import os
import signal
import argparse
from typing import Optional

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config, ConfigurationError
from src.logging_config import setup_logging, get_logger
from src.afs_client import AFSClient
from src.metrics_transformer import MetricsTransformer
from src.metrics_handler import MetricsHandler
from src.http_server import MetricsServer
from src.retry_handler import create_retry_config


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='AFS Prometheus Metrics Collector Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Start with default config
  %(prog)s --config config.yaml    # Start with specific config file
  %(prog)s --debug                  # Start in debug mode
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        help='Path to configuration file (default: config.yaml if exists)'
    )
    
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug mode'
    )
    
    parser.add_argument(
        '--validate-config',
        action='store_true',
        help='Validate configuration and exit'
    )
    
    parser.add_argument(
        '--test-connection',
        action='store_true',
        help='Test AFS API connection and exit'
    )
    
    return parser.parse_args()


def setup_signal_handlers(server: Optional[MetricsServer] = None):
    """Set up signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        logger = get_logger(__name__)
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        
        # Perform cleanup here if needed
        if server:
            logger.info("Stopping HTTP server...")
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def validate_configuration(config: Config) -> bool:
    """
    Validate configuration and log results.
    
    Args:
        config: Configuration to validate
        
    Returns:
        True if configuration is valid
    """
    logger = get_logger(__name__)
    
    try:
        logger.info("Validating configuration...")
        config.validate()
        logger.info("Configuration validation successful")
        
        # Additional validation checks
        afs_config = config.get_afs_config()
        logger.info(f"Configured {len(afs_config.volumes)} AFS volumes:")
        for i, volume in enumerate(afs_config.volumes, 1):
            logger.info(f"  {i}. Volume {volume.volume_id} in zone {volume.zone}")
        
        server_config = config.get_server_config()
        logger.info(f"Server will listen on {server_config.host}:{server_config.port}")
        
        collection_config = config.get_collection_config()
        logger.info(f"Collection timeout: {collection_config.timeout_seconds}s, "
                   f"max retries: {collection_config.max_retries}, "
                   f"cache duration: {collection_config.cache_duration}s")
        
        return True
        
    except ConfigurationError as e:
        logger.error(f"Configuration validation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during configuration validation: {e}")
        return False


def test_afs_connection(config: Config) -> bool:
    """
    Test AFS API connection.
    
    Args:
        config: Configuration object
        
    Returns:
        True if connection test successful
    """
    logger = get_logger(__name__)
    
    try:
        logger.info("Testing AFS API connection...")
        
        afs_config = config.get_afs_config()
        collection_config = config.get_collection_config()
        
        # Create retry configuration
        retry_config = create_retry_config(
            max_attempts=collection_config.max_retries,
            base_delay=collection_config.retry_delay,
            max_delay=30.0
        )
        
        # Create AFS client
        afs_client = AFSClient(
            access_key=afs_config.access_key,
            secret_key=afs_config.secret_key,
            base_url=afs_config.base_url,
            retry_config=retry_config
        )
        
        # Test connection
        if afs_client.test_connection():
            logger.info("AFS API connection test successful")
            
            # Test actual data retrieval from first volume
            if afs_config.volumes:
                volume = afs_config.volumes[0]
                logger.info(f"Testing data retrieval from volume {volume.volume_id}...")
                
                try:
                    quota_data = afs_client.get_volume_quotas(
                        volume_id=volume.volume_id,
                        zone=volume.zone,
                        timeout=collection_config.timeout_seconds
                    )
                    
                    dir_count = len(quota_data.get('dir_quota_list', []))
                    logger.info(f"Successfully retrieved quota data for {dir_count} directories")
                    
                except Exception as e:
                    logger.error(f"Data retrieval test failed: {e}")
                    return False
            
            return True
        else:
            logger.error("AFS API connection test failed")
            return False
            
    except Exception as e:
        logger.error(f"Connection test failed with error: {e}")
        return False


def main():
    """Main entry point."""
    args = parse_arguments()
    
    try:
        # Load configuration
        config = Config(config_file=args.config)
        
        # Set up logging
        logging_config = config.get_logging_config()
        setup_logging(logging_config)
        
        logger = get_logger(__name__)
        logger.info("Starting AFS Prometheus Metrics Collector")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Working directory: {os.getcwd()}")
        
        # Validate configuration
        if not validate_configuration(config):
            logger.error("Configuration validation failed, exiting")
            sys.exit(1)
        
        # Handle special modes
        if args.validate_config:
            logger.info("Configuration validation completed successfully")
            sys.exit(0)
        
        if args.test_connection:
            if test_afs_connection(config):
                logger.info("Connection test completed successfully")
                sys.exit(0)
            else:
                logger.error("Connection test failed")
                sys.exit(1)
        
        # Create components
        logger.info("Initializing components...")
        
        afs_config = config.get_afs_config()
        collection_config = config.get_collection_config()
        
        # Create retry configuration
        retry_config = create_retry_config(
            max_attempts=collection_config.max_retries,
            base_delay=collection_config.retry_delay,
            max_delay=60.0
        )
        
        # Create AFS client
        afs_client = AFSClient(
            access_key=afs_config.access_key,
            secret_key=afs_config.secret_key,
            base_url=afs_config.base_url,
            retry_config=retry_config
        )
        
        # Create metrics transformer
        transformer = MetricsTransformer()
        
        # Create metrics handler
        metrics_handler = MetricsHandler(
            config=config,
            afs_client=afs_client,
            transformer=transformer
        )
        
        # Create HTTP server
        server = MetricsServer(
            config=config,
            metrics_handler=metrics_handler
        )
        
        # Set up signal handlers
        setup_signal_handlers(server)
        
        logger.info("All components initialized successfully")
        
        # Start server
        logger.info("Starting HTTP server...")
        server.start_server(debug=args.debug)
        
    except ConfigurationError as e:
        # Don't use logger here as logging might not be set up
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
        
    except KeyboardInterrupt:
        logger = get_logger(__name__)
        logger.info("Received keyboard interrupt, shutting down...")
        sys.exit(0)
        
    except Exception as e:
        # Try to use logger, but fall back to print if logging not set up
        try:
            logger = get_logger(__name__)
            logger.error(f"Unexpected error: {e}")
        except:
            print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()