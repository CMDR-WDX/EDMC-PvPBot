"""
The "root" of the entire historic_data part
"""
import json
import pathlib
import threading
import time
import datetime as dt
from typing import Callable, Optional
from classes.logger_factory import logger
from classes.data import create_pvpkill_event, create_kill_from_died_event
from classes.plugin_settings import configuration

class HistoricDataManager:

    def _filter_logs_by_timestamp(self) -> list[pathlib.Path]:
        filtered_logs = []
        logs_directory = configuration.journal_dir
        for log_file in pathlib.Path(logs_directory).glob("*.log"):
            if not log_file.is_file():
                continue
            file_timestamp = int(log_file.stat().st_mtime)
            # Check lower bound
            lower, upper = self._bounds
            if lower is not None and lower > file_timestamp:
                # [file]      [lower, ... , upper]
                continue
            if upper is not None and upper < file_timestamp:
                # [lower, ... , upper]      [file]
                continue
            filtered_logs.append(log_file)
        return filtered_logs

    def __is_cmdr_relevant(self, name: str):
        if self._cmdrs is None:
            return True
        if len(self._cmdrs) == 0:
            return True
        for entry in self._cmdrs:
            entry_upper = entry.upper()
            if entry_upper == name.upper():
                return True
        return False

    def __handle_log_file(self, file, filename) -> Optional[tuple[list, list]]:
        died_events_in_this_file = []
        pvpkill_events_in_this_file = []

        cmdr_name: Optional[str] = None
        current_ship: Optional[str] = 'unknown'
        current_rank: Optional[int] = None

        line = file.readline()
        while line != "":
            try:
                line_as_json = json.loads(line)
                if line_as_json["event"] == "Commander":
                    cmdr_name = str(line_as_json["Name"])
                    if not self.__is_cmdr_relevant(cmdr_name):
                        return None
                elif line_as_json["event"] == "Rank":
                    current_rank = line_as_json["Combat"]
                elif line_as_json["event"] == "Loadout":
                    current_ship = line_as_json["Ship"]
                elif line_as_json["event"] == "SuitLoadout":
                    current_ship = "on_foot"
                    # current_ship = line_as_json["SuitName"] # Can be reactivated later.
                    # For now, all on-foot kills are just treated as "on_foot"
                elif line_as_json["event"] == "Died":
                    # handle Died
                    data = create_kill_from_died_event(line_as_json, cmdr_name, current_ship, current_rank)
                    if data is not None:
                        data.log_origin = filename
                        died_events_in_this_file.append(data)
                elif line_as_json["event"] == "PVPKill":
                    # handle PVP Kill
                    data = create_pvpkill_event(line_as_json, cmdr_name, current_ship, current_rank)
                    if data is not None:
                        data.log_origin = filename
                        pvpkill_events_in_this_file.append(data)
            except Exception as e:
                # Do nothing and hope the line wasn't *that* important :D
                logger.warning(f"Failed to parse Line as json (exception on next line): '{line}'")
                logger.exception(e)
            finally:
                line = file.readline()

        # All Lines were Read
        if cmdr_name is None:
            return None

        if len(pvpkill_events_in_this_file) == 0 and len(died_events_in_this_file) == 0:
            return None

        return pvpkill_events_in_this_file, died_events_in_this_file

    def __parse_logs_and_filter_cmdrs(self, paths: list[pathlib.Path], currentStatusCallback: Optional[Callable[[int, int], None]]):
        pvp_events = []
        died_events = []
        counter: int = 0
        total: int = len(paths)
        last_ui_update_time = dt.datetime.now()
        for path in paths:
            with open(path, "r", encoding="utf8") as current_file:
                response = self.__handle_log_file(current_file, current_file.name)
                if response is None:
                    logger.info(f"Parsed file {path.name} - No relevant events")
                else:
                    pvp_from_file, died_from_file = response
                    logger.info(f"Parsed file {path.name} - {len(pvp_from_file)} PVPKills and {len(died_from_file)} "
                                f"Died Events")
                    pvp_events.extend(pvp_from_file)
                    died_events.extend(died_from_file)
            counter+=1
            if currentStatusCallback is not None:
                duration_since_last_update = dt.datetime.now() - last_ui_update_time
                if duration_since_last_update.total_seconds() > 3:
                    last_ui_update_time = dt.datetime.now()
                    currentStatusCallback(counter, total)
                    
        return pvp_events, died_events

    def __thread(self):
        self.ui_handler.notify_start()
        time.sleep(1)  # Small delay so the user can actually read what is written here
        relevant_log_paths = self._filter_logs_by_timestamp()
        self.ui_handler.notify_progress(0, len(relevant_log_paths))
        pvp_events, died_events_as_pvp_events = self.__parse_logs_and_filter_cmdrs(relevant_log_paths, self.ui_handler.notify_progress)

        self.ui_handler.notify_progress(len(relevant_log_paths), len(relevant_log_paths))
        pvp_events.extend(died_events_as_pvp_events)

        
        if len(pvp_events) == 0:
            self.ui_handler.notify_finished(True)
            configuration.run_historic_aggregation_on_next_startup = False
            return
        
        self.ui_handler.notify_submitting()
        

   
        def handle_callback(success: bool) -> None:
            self.ui_handler.notify_finished(success)
            logger.info("Historic Data Job is complete. Turning off again.")
            configuration.run_historic_aggregation_on_next_startup = False
        
        from classes.event_handling import handle_historic_data
        handle_historic_data(pvp_events, handle_callback)


    def __init__(self, only_cmdrs: Optional[list[str]], lower_unix_bound: Optional[int],
                 upper_unix_bound: Optional[int], ui_handler):
        self._cmdrs = only_cmdrs
        self._bounds = (lower_unix_bound, upper_unix_bound)

        from classes.ui import HistoryAggregatorUI
        self.ui_handler: HistoryAggregatorUI = ui_handler
        threading.Thread(name="pvpbot-historic-worker", target=self.__thread, daemon=True).start()
