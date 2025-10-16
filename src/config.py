"""Configuration management module for AFS Prometheus metrics collector."""

import os
import yaml
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VolumeConfig:
    """Configuration for a single AFS volume."""
    volume_id: str
    zone: str


@dataclass
class AFSConfig:
    """AFS API configuration."""
    access_key: str
    secret_key: str
    base_url: str
    volumes: List[VolumeConfig]


@dataclass
class ServerConfig:
    """HTTP server configuration."""
    host: str = "0.0.0.0"
    port: int = 8080
    request_timeout: int = 30


@dataclass
class CollectionConfig:
    """Data collection configuration."""
    max_retries: int = 3
    retry_delay: int = 2
    timeout_seconds: int = 25
    cache_duration: int = 30


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class Config:
    """Configuration manager for AFS Prometheus metrics collector."""
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager.
        
        Args:
            config_file: Optional path to YAML configuration file
        """
        self.afs: Optional[AFSConfig] = None
        self.server: ServerConfig = ServerConfig()
        self.collection: CollectionConfig = CollectionConfig()
        self.logging: LoggingConfig = LoggingConfig()
        
        # Load configuration from environment variables first
        self.load_from_env()
        
        # Override with config file if provided
        if config_file:
            self.load_from_file(config_file)
        elif os.path.exists("config.yaml"):
            self.load_from_file("config.yaml")
    
    def load_from_env(self) -> None:
        """Load configuration from environment variables."""
        # AFS configuration
        access_key = os.getenv("AFS_ACCESS_KEY")
        secret_key = os.getenv("AFS_SECRET_KEY")
        base_url = os.getenv("AFS_BASE_URL", "https://afs.cn-sh-01.sensecoreapi.cn")
        
        if access_key and secret_key:
            # Parse volumes from environment (simplified - single volume for now)
            volume_id = os.getenv("AFS_VOLUME_ID")
            zone = os.getenv("AFS_ZONE")
            
            volumes = []
            if volume_id and zone:
                volumes.append(VolumeConfig(volume_id=volume_id, zone=zone))
            
            self.afs = AFSConfig(
                access_key=access_key,
                secret_key=secret_key,
                base_url=base_url,
                volumes=volumes
            )
        
        # Server configuration
        self.server = ServerConfig(
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8080")),
            request_timeout=int(os.getenv("REQUEST_TIMEOUT", "30"))
        )
        
        # Collection configuration
        self.collection = CollectionConfig(
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            retry_delay=int(os.getenv("RETRY_DELAY", "2")),
            timeout_seconds=int(os.getenv("COLLECTION_TIMEOUT", "25")),
            cache_duration=int(os.getenv("CACHE_DURATION", "30"))
        )
        
        # Logging configuration
        self.logging = LoggingConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    
    def load_from_file(self, config_path: str) -> None:
        """Load configuration from YAML file.
        
        Args:
            config_path: Path to YAML configuration file
            
        Raises:
            ConfigurationError: If file cannot be read or parsed
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                raise ConfigurationError(f"Configuration file not found: {config_path}")
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            if not config_data:
                raise ConfigurationError(f"Configuration file is empty: {config_path}")
            
            # Load AFS configuration
            if 'afs' in config_data:
                afs_config = config_data['afs']
                volumes = []
                
                if 'volumes' in afs_config:
                    for vol_config in afs_config['volumes']:
                        volumes.append(VolumeConfig(
                            volume_id=vol_config['volume_id'],
                            zone=vol_config['zone']
                        ))
                
                self.afs = AFSConfig(
                    access_key=afs_config.get('access_key', ''),
                    secret_key=afs_config.get('secret_key', ''),
                    base_url=afs_config.get('base_url', 'https://afs.cn-sh-01.sensecoreapi.cn'),
                    volumes=volumes
                )
            
            # Load server configuration
            if 'server' in config_data:
                server_config = config_data['server']
                self.server = ServerConfig(
                    host=server_config.get('host', '0.0.0.0'),
                    port=server_config.get('port', 8080),
                    request_timeout=server_config.get('request_timeout', 30)
                )
            
            # Load collection configuration
            if 'collection' in config_data:
                collection_config = config_data['collection']
                self.collection = CollectionConfig(
                    max_retries=collection_config.get('max_retries', 3),
                    retry_delay=collection_config.get('retry_delay', 2),
                    timeout_seconds=collection_config.get('timeout_seconds', 25),
                    cache_duration=collection_config.get('cache_duration', 30)
                )
            
            # Load logging configuration
            if 'logging' in config_data:
                logging_config = config_data['logging']
                self.logging = LoggingConfig(
                    level=logging_config.get('level', 'INFO'),
                    format=logging_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                )
                
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in configuration file {config_path}: {e}")
        except (KeyError, TypeError, ValueError) as e:
            raise ConfigurationError(f"Invalid configuration structure in {config_path}: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration file {config_path}: {e}")
    
    def get_afs_config(self) -> AFSConfig:
        """Get AFS configuration.
        
        Returns:
            AFSConfig object
            
        Raises:
            ConfigurationError: If AFS configuration is not available
        """
        if not self.afs:
            raise ConfigurationError("AFS configuration is not available")
        return self.afs
    
    def get_server_config(self) -> ServerConfig:
        """Get server configuration.
        
        Returns:
            ServerConfig object
        """
        return self.server
    
    def get_collection_config(self) -> CollectionConfig:
        """Get collection configuration.
        
        Returns:
            CollectionConfig object
        """
        return self.collection
    
    def get_logging_config(self) -> LoggingConfig:
        """Get logging configuration.
        
        Returns:
            LoggingConfig object
        """
        return self.logging
    
    def validate(self) -> bool:
        """Validate the complete configuration.
        
        Returns:
            True if configuration is valid
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        self._validate_afs_config()
        self._validate_server_config()
        self._validate_collection_config()
        self._validate_logging_config()
        return True
    
    def _validate_afs_config(self) -> None:
        """Validate AFS configuration.
        
        Raises:
            ConfigurationError: If AFS configuration is invalid
        """
        if not self.afs:
            raise ConfigurationError("AFS configuration is required")
        
        # Validate access key format
        if not self.afs.access_key or not isinstance(self.afs.access_key, str):
            raise ConfigurationError("AFS access_key is required and must be a non-empty string")
        
        if len(self.afs.access_key.strip()) == 0:
            raise ConfigurationError("AFS access_key cannot be empty")
        
        # Validate secret key format
        if not self.afs.secret_key or not isinstance(self.afs.secret_key, str):
            raise ConfigurationError("AFS secret_key is required and must be a non-empty string")
        
        if len(self.afs.secret_key.strip()) == 0:
            raise ConfigurationError("AFS secret_key cannot be empty")
        
        # Validate base URL format
        if not self.afs.base_url or not isinstance(self.afs.base_url, str):
            raise ConfigurationError("AFS base_url is required and must be a non-empty string")
        
        if not self.afs.base_url.startswith(('http://', 'https://')):
            raise ConfigurationError("AFS base_url must start with http:// or https://")
        
        # Validate volumes configuration
        if not self.afs.volumes:
            raise ConfigurationError("At least one AFS volume must be configured")
        
        for i, volume in enumerate(self.afs.volumes):
            if not volume.volume_id or not isinstance(volume.volume_id, str):
                raise ConfigurationError(f"Volume {i}: volume_id is required and must be a non-empty string")
            
            if len(volume.volume_id.strip()) == 0:
                raise ConfigurationError(f"Volume {i}: volume_id cannot be empty")
            
            if not volume.zone or not isinstance(volume.zone, str):
                raise ConfigurationError(f"Volume {i}: zone is required and must be a non-empty string")
            
            if len(volume.zone.strip()) == 0:
                raise ConfigurationError(f"Volume {i}: zone cannot be empty")
    
    def _validate_server_config(self) -> None:
        """Validate server configuration.
        
        Raises:
            ConfigurationError: If server configuration is invalid
        """
        if not isinstance(self.server.host, str) or len(self.server.host.strip()) == 0:
            raise ConfigurationError("Server host must be a non-empty string")
        
        if not isinstance(self.server.port, int) or self.server.port <= 0 or self.server.port > 65535:
            raise ConfigurationError("Server port must be an integer between 1 and 65535")
        
        if not isinstance(self.server.request_timeout, int) or self.server.request_timeout <= 0:
            raise ConfigurationError("Server request_timeout must be a positive integer")
    
    def _validate_collection_config(self) -> None:
        """Validate collection configuration.
        
        Raises:
            ConfigurationError: If collection configuration is invalid
        """
        if not isinstance(self.collection.max_retries, int) or self.collection.max_retries < 0:
            raise ConfigurationError("Collection max_retries must be a non-negative integer")
        
        if not isinstance(self.collection.retry_delay, int) or self.collection.retry_delay <= 0:
            raise ConfigurationError("Collection retry_delay must be a positive integer")
        
        if not isinstance(self.collection.timeout_seconds, int) or self.collection.timeout_seconds <= 0:
            raise ConfigurationError("Collection timeout_seconds must be a positive integer")
        
        if not isinstance(self.collection.cache_duration, int) or self.collection.cache_duration < 0:
            raise ConfigurationError("Collection cache_duration must be a non-negative integer")
        
        # Validate that timeout is less than request timeout
        if self.collection.timeout_seconds >= self.server.request_timeout:
            raise ConfigurationError("Collection timeout_seconds must be less than server request_timeout")
    
    def _validate_logging_config(self) -> None:
        """Validate logging configuration.
        
        Raises:
            ConfigurationError: If logging configuration is invalid
        """
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        
        if not isinstance(self.logging.level, str):
            raise ConfigurationError("Logging level must be a string")
        
        if self.logging.level.upper() not in valid_levels:
            raise ConfigurationError(f"Logging level must be one of: {', '.join(valid_levels)}")
        
        if not isinstance(self.logging.format, str) or len(self.logging.format.strip()) == 0:
            raise ConfigurationError("Logging format must be a non-empty string")
    
    def validate_credentials_format(self) -> bool:
        """Validate AFS credentials format specifically.
        
        Returns:
            True if credentials format is valid
            
        Raises:
            ConfigurationError: If credentials format is invalid
        """
        if not self.afs:
            raise ConfigurationError("AFS configuration is not available for validation")
        
        # Check access key format (should be alphanumeric with possible special characters)
        access_key = self.afs.access_key.strip()
        if len(access_key) < 8:
            raise ConfigurationError("AFS access_key appears too short (minimum 8 characters)")
        
        # Check secret key format (should be alphanumeric with possible special characters)
        secret_key = self.afs.secret_key.strip()
        if len(secret_key) < 16:
            raise ConfigurationError("AFS secret_key appears too short (minimum 16 characters)")
        
        # Check for obvious placeholder values
        placeholder_values = ['your_access_key', 'your_secret_key', 'YOUR_ACCESS_KEY', 'YOUR_SECRET_KEY']
        if access_key.lower() in [p.lower() for p in placeholder_values]:
            raise ConfigurationError("AFS access_key appears to be a placeholder value")
        
        if secret_key.lower() in [p.lower() for p in placeholder_values]:
            raise ConfigurationError("AFS secret_key appears to be a placeholder value")
        
        return True