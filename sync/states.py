import logging
from utils.helpers import haversine_distance
from sqlalchemy import text

class StateSync:
    def __init__(self, teslalogger_conn, teslamate_conn, dry_run):
        self.teslalogger_conn = teslalogger_conn
        self.teslamate_conn = teslamate_conn
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)

    def sync(self):
        # Fetch state records from both databases
        teslalogger_states = self._fetch_teslalogger_states()
        teslamate_states = self._fetch_teslamate_states()

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
                if (abs((tl_state['StartDate'] - tm_state['start_date']).total_seconds()) <= 300 and
                    tl_state['CarID'] == tm_state['car_id']):
                    
                    merged_state = self._merge_state_record(tl_state, tm_state)
                    matches.append(merged_state)

        return matches

    def _merge_state_record(self, teslalogger_state, teslamate_state):
        # Merge logic for state records
        merged_state = {
            'start_date': min(teslalogger_state['StartDate'], teslamate_state['start_date']),
            'end_date': max(
                teslalogger_state['EndDate'] or teslamate_state['end_date'],
                teslamate_state['end_date']
            ),
            'car_id': teslalogger_state['CarID'],
            'state': teslalogger_state['state'] or teslamate_state['state'],
            'additional_details': {
                'start_position': teslalogger_state.get('StartPos'),
                'end_position': teslalogger_state.get('EndPos')
            }
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
                        'state': row.state,
                        'battery_level': row.battery_level,
                        'ideal_battery_range_km': row.ideal_battery_range_km,
                        # Add other relevant fields
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
                        'state': row.state,
                        'battery_level': row.battery_level,
                        # Add other relevant fields
                    }
                    states.append(state)
                except Exception as field_error:
                    self.logger.warning(f"Could not process TeslaMate state row: {field_error}")
            
            self.logger.info(f"Fetched {len(states)} states from TeslaMate")
            return states
        
        except Exception as e:
            self.logger.error(f"Error fetching TeslaMate states: {e}")
            return None
