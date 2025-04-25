import os
from dotenv import load_dotenv
import logging

class Config:
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()

        # Database Configurations
        self.teslalogger_config = self._get_teslalogger_config()
        self.teslamate_config = self._get_teslamate_config()

        # Sync Configurations
        self.sync_config = self._get_sync_config()

    def _get_teslalogger_config(self):
        """
        Retrieve TeslaLogger database configuration
        """
        return {
            'host': os.getenv('TESLALOGGER_DB_HOST', 'localhost'),
            'port': os.getenv('TESLALOGGER_DB_PORT', '3306'),
            'database': os.getenv('TESLALOGGER_DB_NAME', 'teslalogger'),
            'user': os.getenv('TESLALOGGER_DB_USER', 'root'),
            'password': os.getenv('TESLALOGGER_DB_PASSWORD', ''),
            'dialect': 'mysql+pymysql'
        }

    def _get_teslamate_config(self):
        """
        Retrieve TeslaMate database configuration
        """
        return {
            'host': os.getenv('TESLAMATE_DB_HOST', 'localhost'),
            'port': os.getenv('TESLAMATE_DB_PORT', '5432'),
            'database': os.getenv('TESLAMATE_DB_NAME', 'teslamate'),
            'user': os.getenv('TESLAMATE_DB_USER', 'teslamate'),
            'password': os.getenv('TESLAMATE_DB_PASSWORD', ''),
            'dialect': 'postgresql+psycopg2'
        }

    def _get_sync_config(self):
        """
        Retrieve sync-specific configurations
        """
        return {
            # Proximity settings for matching records
            'position_time_window': int(os.getenv('POSITION_TIME_WINDOW', 30)),  # seconds
            'position_distance_threshold': float(os.getenv('POSITION_DISTANCE_THRESHOLD', 10)),  # meters
            
            # Logging configurations
            'log_level': os.getenv('LOG_LEVEL', 'INFO'),
            
            # Specific sync toggles
            'sync_positions': os.getenv('SYNC_POSITIONS', '0') == '1',
            'sync_drives': os.getenv('SYNC_DRIVES', '0') == '1',
            'sync_charging': os.getenv('SYNC_CHARGING', '0') == '1',
            'sync_states': os.getenv('SYNC_STATES', '0') == '1',
            
            # Limits
            'position_limit': int(os.getenv('POSITION_LIMIT', 0)),

            # Test and validation flags
            'test_position': os.getenv('TEST_POSITION', '0') == '1',
            'dry_run': os.getenv('DRYRUN', '1') == '1'
        }

    def get_database_connection_string(self, db_config):
        """
        Generate SQLAlchemy connection string
        """
        return (
            f"{db_config['dialect']}://"
            f"{db_config['user']}:{db_config['password']}@"
            f"{db_config['host']}:{db_config['port']}/"
            f"{db_config['database']}"
        )

def load_config():
    """
    Load and return configuration
    """
    try:
        config = Config()
        return config
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        raise
