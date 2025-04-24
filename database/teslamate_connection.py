from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def establish_teslamate_connection(config):
    """
    Establish a connection to the TeslaMate database
    """
    try:
        connection_string = config.get_database_connection_string(
            config.teslamate_config
        )
        
        engine = create_engine(connection_string, pool_pre_ping=True)
        Session = sessionmaker(bind=engine)
        
        return Session()
    except Exception as e:
        logging.error(f"Failed to connect to TeslaMate database: {e}")
        raise
