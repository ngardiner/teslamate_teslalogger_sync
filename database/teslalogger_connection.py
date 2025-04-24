from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def establish_teslalogger_connection(config):
    """
    Establish a connection to the TeslaLogger database
    """
    try:
        connection_string = config.get_database_connection_string(
            config.teslalogger_config
        )
        
        engine = create_engine(connection_string, pool_pre_ping=True)

        # Test connection
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("TeslaLogger Database Connection Successful")

        Session = sessionmaker(bind=engine)
        
        return Session()
    except Exception as e:
        logging.error(f"Failed to connect to TeslaLogger database: {e}")
        raise
