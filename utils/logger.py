import logging
import sys

def setup_logging(log_level=logging.INFO):
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('tesla_sync.log')
        ]
    )
    return logging.getLogger()
