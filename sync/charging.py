import logging
from utils.helpers import haversine_distance

class ChargingSync:
    def __init__(self, teslalogger_conn, teslamate_conn, dry_run):
        self.teslalogger_conn = teslalogger_conn
        self.teslamate_conn = teslamate_conn
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)

    def sync(self):
        # Fetch charging records from both databases
        teslalogger_charging = self._fetch_teslalogger_charging()
        teslamate_charging = self._fetch_teslamate_charging()

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

        return matches

    def _merge_charging_record(self, teslalogger_charge, teslamate_charge):
        # Merge logic for charging records
        merged_charge = {
            'start_date': min(teslalogger_charge['Datum'], teslamate_charge['date']),
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
            # Add more merged fields as needed
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
        # Fetch charging records from TeslaLogger database
        # Implement database query
        pass

    def _fetch_teslamate_charging(self):
        # Fetch charging records from TeslaMate database
        # Implement database query
        pass
