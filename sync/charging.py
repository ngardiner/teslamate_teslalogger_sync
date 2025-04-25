import logging
from utils.helpers import haversine_distance
from sqlalchemy import text

class ChargingSync:
    def __init__(self, teslalogger_conn, teslamate_conn, dry_run, stats):
        self.teslalogger_conn = teslalogger_conn
        self.teslamate_conn = teslamate_conn
        self.dry_run = dry_run
        self.stats = stats  # Reference to the subkey of the stats hash 
        self.logger = logging.getLogger(__name__)

    def sync(self):
        # Fetch charging records from both databases
        teslalogger_charging = self._fetch_teslalogger_charging()
        teslamate_charging = self._fetch_teslamate_charging()

        # Validate fetched charging records
        if teslalogger_charging is None:
            self.logger.error("Failed to fetch TeslaLogger charging records")
            # Return empty list instead of None
            return []
        
        if teslamate_charging is None:
            self.logger.error("Failed to fetch TeslaMate charging records")
            # Return empty list instead of None
            return []

        # Detailed logging
        self.logger.info(f"TeslaLogger Charging Records: {len(teslalogger_charging)}")
        self.logger.info(f"TeslaMate Charging Records: {len(teslamate_charging)}")

        # Find potential matches
        potential_merges = self._find_charging_matches(
            teslalogger_charging, 
            teslamate_charging
        )

        return potential_merges

    def _find_charging_matches(self, teslalogger_charging, teslamate_charging):
        matches = []
        
        for tl_charge in teslalogger_charging:
            for tm_charge in teslamate_charging:
                # Match criteria
                if (abs((tl_charge['Datum'] - tm_charge['date']).total_seconds()) <= 300 and
                    tl_charge['CarID'] == tm_charge['car_id']):
                    
                    merged_charge = self._merge_charging_record(tl_charge, tm_charge)
                    matches.append(merged_charge)

                    # Update stats
                    self.stats['processed'] += len(teslalogger_charging)
                else:
                    self.stats['skipped'] += len(teslalogger_charging) - len(potential_merges)


        return matches

    def _merge_charging_record(self, teslalogger_charge, teslamate_charge):
        # Merge logic for charging records
        merged_charge = {
            'start_date': min(
                teslalogger_charge['Datum'], 
                teslamate_charge['start_date']
            ),
            'end_date': max(
                teslalogger_charge.get('EndDate') or teslamate_charge['end_date'], 
                teslamate_charge['end_date']
            ),
            'car_id': teslalogger_charge['CarID'],
            'charge_energy_added': max(
                teslalogger_charge.get('charge_energy_added', 0), 
                teslamate_charge.get('charge_energy_added', 0)
            ),
            'battery_level': {
                'start': teslalogger_charge.get('battery_level'),
                'end': teslamate_charge.get('end_battery_level')
            },
            'charger_power': max(
                teslalogger_charge.get('charger_power', 0), 
                teslamate_charge.get('charger_power', 0)
            ),
            'location': {
                'latitude': teslalogger_charge.get('latitude') or teslamate_charge.get('latitude'),
                'longitude': teslalogger_charge.get('longitude') or teslamate_charge.get('longitude')
            },
            'cost_total': max(
                teslalogger_charge.get('cost_total', 0) or 0, 
                teslamate_charge.get('cost_total', 0) or 0
            ),
            'fast_charger_brand': (
                teslalogger_charge.get('fast_charger_brand') or 
                teslamate_charge.get('fast_charger_brand')
            ),        
        }
        return merged_charge

    def log_potential_merges(self, potential_merges):
        self.logger.info(f"Dry Run - Potential Charging Merges: {len(potential_merges)}")
        for merge in potential_merges:
            self.logger.info(f"Would merge charging record: {merge}")

        if potential_merges:
            self.logger.warning("""
            DRY RUN MODE ACTIVE
            Potential charging merges detected.
            To apply changes, set DRYRUN=0
            """)

    def _fetch_teslalogger_charging(self):
        """
        Fetch charging records from TeslaLogger database
        """
        try:
            # Use text() for raw SQL queries
            query = text("SELECT * FROM charging LIMIT 1000")  # Adjust limit as needed
            result = self.teslalogger_conn.execute(query)
            
            # Convert to list of dictionaries
            charges = []
            for row in result:
                try:
                    charge = {
                        'Datum': row.Datum,
                        'CarID': row.CarID,
                        'charge_energy_added': row.charge_energy_added,
                        'battery_level_start': row.battery_level_start,
                        'battery_level_end': row.battery_level_end,
                        'charger_power': row.charger_power,
                        'start_date': row.start_date,
                        'end_date': row.end_date,
                        'car_id': row.car_id,
                        'charge_energy_added': getattr(row, 'charge_energy_added', None),
                        'battery_level_start': getattr(row, 'start_battery_level', None),
                        'battery_level_end': getattr(row, 'end_battery_level', None),
                        'charger_power': getattr(row, 'charge_power', None),
                        'latitude': getattr(row, 'latitude', None),
                        'longitude': getattr(row, 'longitude', None),
                        'cost_total': getattr(row, 'cost_total', None),
                        'fast_charger_brand': getattr(row, 'fast_charger_brand', None),
                    }
                    charges.append(charge)
                except Exception as field_error:
                    self.logger.warning(f"Could not process charging row: {field_error}")
            
            self.logger.info(f"Fetched {len(charges)} charging records from TeslaLogger")
            return charges
        
        except Exception as e:
            self.logger.error(f"Error fetching TeslaLogger charging records: {e}")
            return None

    def _fetch_teslamate_charging(self):
        """
        Fetch charging records from TeslaMate database
        """
        try:
            # Use text() for raw SQL queries
            query = text("SELECT * FROM charging_processes LIMIT 1000")  # Adjust limit as needed
            result = self.teslamate_conn.execute(query)
            
            # Convert to list of dictionaries
            charges = []
            for row in result:
                try:
                    charge = {
                        'date': row.start_date,
                        'end_date': row.end_date,
                        'car_id': row.car_id,
                        'charge_energy_added': row.charge_energy_added,
                        'battery_level_start': row.start_battery_level,
                        'battery_level_end': row.end_battery_level,
                        'charger_power': row.charge_power,
                        # Add other relevant fields
                    }
                    charges.append(charge)
                except Exception as field_error:
                    self.logger.warning(f"Could not process TeslaMate charging row: {field_error}")
            
            self.logger.info(f"Fetched {len(charges)} charging records from TeslaMate")
            return charges
        
        except Exception as e:
            self.logger.error(f"Error fetching TeslaMate charging records: {e}")
            return None
