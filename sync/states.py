import logging
from utils.helpers import haversine_distance
from sqlalchemy import text
from datetime import timedelta

class StateSync:
    def __init__(self, teslalogger_conn, teslamate_conn, dry_run):
        self.teslalogger_conn = teslalogger_conn
        self.teslamate_conn = teslamate_conn
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)

    def sync(self):
        # Fetch states from both databases
        teslalogger_states = self._fetch_teslalogger_states()
        teslamate_states = self._fetch_teslamate_states()

        # Validate fetched states
        if teslalogger_states is None:
            self.logger.error("Failed to fetch TeslaLogger states")
            return []
        
        if teslamate_states is None:
            self.logger.error("Failed to fetch TeslaMate states")
            return []

        # Detailed logging
        self.logger.info(f"TeslaLogger States: {len(teslalogger_states)}")
        self.logger.info(f"TeslaMate States: {len(teslamate_states)}")

        # Find potential matches
        potential_merges = self._find_state_matches(
            teslalogger_states, 
            teslamate_states
        )

        return potential_merges

    def _find_state_matches(self, teslalogger_states, teslamate_states):
        matches = []
        
        for tl_state in teslalogger_states:
            for tm_state in teslamate_states:
                # Match criteria
                # Compare start times with a 5-minute tolerance
                time_diff = abs(tl_state['StartDate'] - tm_state['start_date'])
                
                # Check if states are from the same car
                car_match = (tl_state['CarID'] == tm_state['car_id'])
                
                # Compare state attributes
                state_match = (
                    tl_state.get('state') == tm_state.get('state') or
                    tl_state.get('state') is None or
                    tm_state.get('state') is None
                )
                
                # Combine match criteria
                if (time_diff <= timedelta(minutes=5) and 
                    car_match and 
                    state_match):
                    
                    merged_state = self._merge_state_record(tl_state, tm_state)
                    matches.append(merged_state)

        return matches

    def _merge_state_record(self, teslalogger_state, teslamate_state):
        # Merge logic for state records
        merged_state = {
            'start_date': min(
                teslalogger_state['StartDate'], 
                teslamate_state['start_date']
            ),
            'end_date': max(
                teslalogger_state.get('EndDate') or teslamate_state['end_date'], 
                teslamate_state['end_date']
            ),
            'car_id': teslalogger_state['CarID'],
            'state': teslalogger_state.get('state') or teslamate_state.get('state'),
            'battery_level': max(
                teslalogger_state.get('battery_level', 0) or 0,
                teslamate_state.get('battery_level', 0) or 0
            ),
            'ideal_battery_range_km': max(
                teslalogger_state.get('ideal_battery_range_km', 0) or 0,
                teslamate_state.get('ideal_battery_range_km', 0) or 0
            ),
            'outside_temp': teslalogger_state.get('outside_temp') or teslamate_state.get('outside_temp'),
            'inside_temp': teslalogger_state.get('inside_temp') or teslamate_state.get('inside_temp'),
            'climate_state': teslalogger_state.get('climate_state') or teslamate_state.get('climate_state'),
            'charge_state': teslalogger_state.get('charge_state') or teslamate_state.get('charge_state'),
        }
        return merged_state

    def log_potential_merges(self, potential_merges):
        self.logger.info(f"Dry Run - Potential State Merges: {len(potential_merges)}")
        for merge in potential_merges:
            self.logger.info(f"Would merge state record: {merge}")

        if potential_merges:
            self.logger.warning("""
            DRY RUN MODE ACTIVE
            Potential state merges detected.
            To apply changes, set DRYRUN=0
            """)

    def _fetch_teslalogger_states(self):
        """
        Fetch state records from TeslaLogger database
        """
        try:
            # Use text() for raw SQL queries
            query = text("SELECT * FROM state LIMIT 1000")  # Adjust limit as needed
            result = self.teslalogger_conn.execute(query)
            
            # Convert to list of dictionaries
            states = []
            for row in result:
                try:
                    state = {
                        'StartDate': row.StartDate,
                        'EndDate': row.EndDate,
                        'CarID': row.CarID,
                        'state': getattr(row, 'state', None),
                        'battery_level': getattr(row, 'battery_level', None),
                        'ideal_battery_range_km': getattr(row, 'ideal_battery_range_km', None),
                        'outside_temp': getattr(row, 'outside_temp', None),
                        'inside_temp': getattr(row, 'inside_temp', None),
                        'climate_state': getattr(row, 'climate_state', None),
                        'charge_state': getattr(row, 'charge_state', None),
                    }
                    states.append(state)
                except Exception as field_error:
                    self.logger.warning(f"Could not process state row: {field_error}")
            
            self.logger.info(f"Fetched {len(states)} states from TeslaLogger")
            return states
        
        except Exception as e:
            self.logger.error(f"Error fetching TeslaLogger states: {e}")
            return None

    def _fetch_teslamate_states(self):
        """
        Fetch state records from TeslaMate database
        """
        try:
            # Use text() for raw SQL queries
            query = text("SELECT * FROM states LIMIT 1000")  # Adjust limit as needed
            result = self.teslamate_conn.execute(query)
            
            # Convert to list of dictionaries
            states = []
            for row in result:
                try:
                    state = {
                        'start_date': row.start_date,
                        'end_date': row.end_date,
                        'car_id': row.car_id,
                        'state': getattr(row, 'state', None),
                        'battery_level': getattr(row, 'battery_level', None),
                        'ideal_battery_range_km': getattr(row, 'ideal_battery_range_km', None),
                        'outside_temp': getattr(row, 'outside_temp', None),
                        'inside_temp': getattr(row, 'inside_temp', None),
                        'climate_state': getattr(row, 'climate_state', None),
                        'charge_state': getattr(row, 'charge_state', None),
                    }
                    states.append(state)
                except Exception as field_error:
                    self.logger.warning(f"Could not process TeslaMate state row: {field_error}")
            
            self.logger.info(f"Fetched {len(states)} states from TeslaMate")
            return states
        
        except Exception as e:
            self.logger.error(f"Error fetching TeslaMate states: {e}")
            return None
