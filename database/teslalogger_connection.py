import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def establish_teslalogger_connection(config):
    """
    Establish a connection to the TeslaLogger database

    :param config: Configuration object
    :return: SQLAlchemy engine
    """
    try:
        # Use the method from config to generate connection string
        connection_string = config.get_database_connection_string(config.teslalogger_config)
        
        engine = create_engine(connection_string, pool_pre_ping=True)

        # Test connection
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            logging.info("TeslaLogger Database Connection Successful")

        Session = sessionmaker(bind=engine)
        
        return Session()
    except Exception as e:
        logging.error(f"Failed to connect to TeslaLogger database: {e}")
        raise
