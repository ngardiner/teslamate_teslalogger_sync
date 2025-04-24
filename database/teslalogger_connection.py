from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def establish_teslalogger_connection(config):
    """
    Establish a connection to the TeslaLogger database

    :param config: Configuration object
    :return: SQLAlchemy engine
    """
    try:
        # Construct connection string
        connection_string = (
            f"mysql+pymysql://{config.TESLALOGGER_DB_USER}:{config.TESLALOGGER_DB_PASS}@"
            f"{config.TESLALOGGER_DB_HOST}:{config.TESLALOGGER_DB_PORT}/{config.TESLALOGGER_DB_NAME}"
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
