"""
The "root" of the entire historic_data part
"""
import json
import pathlib
import threading
import time
import datetime as dt
from typing import Callable, Optional
from config import config
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
        current_ship: Optional[str] = None
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
                    current_ship = line_as_json["SuitName"]
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

    def __parse_logs_and_filter_cmdrs(self, paths: list[pathlib.Path]):
        pvp_events = []
        died_events = []
        for path in paths:
            with open(path, "r", encoding="utf8") as current_file:
                response = self.__handle_log_file(current_file, current_file.name)
                if response is None:
                    logger.info(f"Parsed file {path.name} - No relevant events")
                    continue
                pvp_from_file, died_from_file = response
                logger.info(f"Parsed file {path.name} - {len(pvp_from_file)} PVPKills and {len(died_from_file)} "
                            f"Died Events")
                pvp_events.extend(pvp_from_file)
                died_events.extend(died_from_file)
        return pvp_events, died_events

    def __thread(self):
        self._cb("Running History Logs Aggregation for PvpBot... Do not close EDMC until finished")
        time.sleep(1)  # Small delay so the user can actually read what is written here
        relevant_log_paths = self._filter_logs_by_timestamp()
        self._cb(f"{str(len(relevant_log_paths))} Logs found matching Time Criteria")
        pvp_events, died_events_as_pvp_events = self.__parse_logs_and_filter_cmdrs(relevant_log_paths)
        self._cb(f"{len(pvp_events)} PVP Events and {len(died_events_as_pvp_events)} "
                 f"Died Events found... Sending to Backend")

        from classes.event_handling import push_kill_event_batch

        pvp_events.extend(died_events_as_pvp_events)

        if len(pvp_events) > 0:
            push_kill_event_batch(pvp_events)

        # Sleep for 2 seconds. A bit scuffed, but whatever.
        # I will just assume this is enough time to send stuff to the Backend
        time.sleep(2)
        configuration.run_historic_aggregation_on_next_startup = False
        self._cb(f"Historic Data finished and turned off.")

    def __init__(self, only_cmdrs: Optional[list[str]], lower_unix_bound: Optional[int],
                 upper_unix_bound: Optional[int], ui_callback: Callable[[str], None]):
        self._cmdrs = only_cmdrs
        self._bounds = (lower_unix_bound, upper_unix_bound)
        self._cb = ui_callback
        threading.Thread(name="pvpbot-historic-worker", target=self.__thread, daemon=True).start()
