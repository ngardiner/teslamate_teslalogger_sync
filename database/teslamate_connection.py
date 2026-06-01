import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

def establish_teslamate_connection(config):
    try:
        c = config.teslamate_config
        url = URL.create(
            drivername=c['dialect'],
            username=c['user'],
            password=c['password'],
            host=c['host'],
            port=int(c['port']),
            database=c['database'],
        )
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logging.info("TeslaMate database connection successful")
        return engine
    except Exception as e:
        logging.error(f"Failed to connect to TeslaMate database: {e}")
        raise
