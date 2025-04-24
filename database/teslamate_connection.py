from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def establish_teslamate_connection(config):
    """
    Establish a connection to the TeslaMate database

    :param config: Configuration object
    :return: SQLAlchemy engine
    """
    try:
        # Construct connection string
        connection_string = (
            f"postgresql://{config.TESLAMATE_DB_USER}:{config.TESLAMATE_DB_PASS}@"
            f"{config.TESLAMATE_DB_HOST}:{config.TESLAMATE_DB_PORT}/{config.TESLAMATE_DB_NAME}"
        )
        
        engine = create_engine(connection_string, pool_pre_ping=True)

        # Test connection
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("TeslaMate Database Connection Successful")

        Session = sessionmaker(bind=engine)
        
        return Session()
    except Exception as e:
        logging.error(f"Failed to connect to TeslaMate database: {e}")
        raise
