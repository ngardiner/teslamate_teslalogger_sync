import logging
from utils.helpers import haversine_distance
from sqlalchemy import text

class DriveSync:
    def __init__(self, teslalogger_conn, teslamate_conn, dry_run):
        self.teslalogger_conn = teslalogger_conn
        self.teslamate_conn = teslamate_conn
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)

    def sync(self):
        # Fetch drives from both databases
        teslalogger_drives = self._fetch_teslalogger_drives()
        teslamate_drives = self._fetch_teslamate_drives()

        # Validate fetched drives
        if teslalogger_drives is None:
            self.logger.error("Failed to fetch TeslaLogger drives")
            return []
        
        if teslamate_drives is None:
            self.logger.error("Failed to fetch TeslaMate drives")
            return []

        # Find potential matches
        potential_merges = self._find_drive_matches(
            teslalogger_drives, 
            teslamate_drives
        )

        return potential_merges

    def _fetch_teslalogger_drives(self):
        """
        Fetch drives from TeslaLogger database
        """
        try:
            # Use text() for raw SQL queries
            query = text("SELECT * FROM drivestate LIMIT 1000")  # Adjust limit as needed
            result = self.teslalogger_conn.execute(query)
            
            # Convert to list of dictionaries
            drives = []
            for row in result:
                try:
                    drive = {
                        'StartDate': row.StartDate,
                        'EndDate': row.EndDate,
                        'CarID': row.CarID,
                        'distance': row.distance if hasattr(row, 'distance') else None,
                        'speed_max': row.speed_max,
                        # Add other relevant fields
                    }
                    drives.append(drive)
                except Exception as field_error:
                    self.logger.warning(f"Could not process drive row: {field_error}")
            
            self.logger.info(f"Fetched {len(drives)} drives from TeslaLogger")
            return drives
        
        except Exception as e:
            self.logger.error(f"Error fetching TeslaLogger drives: {e}")
            return None

    def _fetch_teslamate_drives(self):
        """
        Fetch drives from TeslaMate database
        """
        try:
            # Use text() for raw SQL queries
            query = text("SELECT * FROM drives LIMIT 1000")  # Adjust limit as needed
            result = self.teslamate_conn.execute(query)
            
            # Convert to list of dictionaries
            drives = []
            for row in result:
                try:
                    drive = {
                        'start_date': row.start_date,
                        'end_date': row.end_date,
                        'car_id': row.car_id,
                        'distance': row.end_km - row.start_km if hasattr(row, 'end_km') and hasattr(row, 'start_km') else None,
                        'speed_max': row.speed_max,
                        # Add other relevant fields
                    }
                    drives.append(drive)
                except Exception as field_error:
                    self.logger.warning(f"Could not process drive row: {field_error}")
            
            self.logger.info(f"Fetched {len(drives)} drives from TeslaMate")
            return drives
        
        except Exception as e:
            self.logger.error(f"Error fetching TeslaMate drives: {e}")
            return None

    def _find_drive_matches(self, teslalogger_drives, teslamate_drives):
        matches = []
        
        for tl_drive in teslalogger_drives:
            for tm_drive in teslamate_drives:
                # Match criteria
                if (abs((tl_drive['StartDate'] - tm_drive['start_date']).total_seconds()) <= 300 and
                    tl_drive['CarID'] == tm_drive['car_id']):
                    
                    merged_drive = self._merge_drive_record(tl_drive, tm_drive)
                    matches.append(merged_drive)

        return matches

    def _merge_drive_record(self, teslalogger_drive, teslamate_drive):
        # Merge logic for drive records
        merged_drive = {
            'start_date': min(teslalogger_drive['StartDate'], teslamate_drive['start_date']),
            'end_date': max(
                teslalogger_drive.get('EndDate') or teslamate_drive['end_date'], 
                teslamate_drive['end_date']
            ),
            'car_id': teslalogger_drive['CarID'],
            'distance': max(
                teslalogger_drive.get('distance', 0), 
                teslamate_drive.get('distance', 0)
            ),
            'speed_max': max(
                teslalogger_drive.get('speed_max', 0), 
                teslamate_drive.get('speed_max', 0)
            ),
            # Add more merged fields as needed
        }
        return merged_drive

    def log_potential_merges(self, potential_merges):
        self.logger.info(f"Dry Run - Potential Drive Merges: {len(potential_merges)}")
        for merge in potential_merges:
            self.logger.info(f"Would merge drive: {merge}")

        if potential_merges:
            self.logger.warning("""
            DRY RUN MODE ACTIVE
            Potential drive merges detected.
            To apply changes, set DRYRUN=0
            """)
