import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

def establish_teslalogger_connection(config):
    try:
        c = config.teslalogger_config
        url = URL.create(
            drivername=c['dialect'],
            username=c['user'],
            password=c['password'],
            host=c['host'],
            port=int(c['port']),
            database=c['database'],
        )
        engine = create_engine(url, pool_pre_ping=True, connect_args={
            'init_command': 'SET SESSION net_write_timeout=3600, net_read_timeout=3600',
        })
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logging.info("TeslaLogger database connection successful")
        return engine
    except Exception as e:
        logging.error(f"Failed to connect to TeslaLogger database: {e}")
        raise
