import datetime
import queue
import threading
import time
from dataclasses import dataclass
import requests
from classes.plugin_settings import configuration
from classes.logger_factory import logger
from typing import Callable

__PVP_BOT_SERVER_URL = "http://localhost:8080"


@dataclass
class _PostCommand:
    endpoint: str
    body: dict


class HttpThread:
    """
    Messages to the Backend are done here to not block the Main Thread. If there was an issue here,
    the listeners (self.__callbacks) will get invoked - one of these Callbacks should be the UI. It can
    then display the error on the UI.
    """

    @staticmethod
    def __write_ui_message(msg: str):
        from classes.ui import ui
        ui.notify_about_new_warning(msg)

    # This is not run in the main thread
    def __thread_loop(self):
        wait_next_loop_because_of_timeout = False
        while True:
            if wait_next_loop_because_of_timeout:
                logger.info("HTTP Thread is sleeping for 1 Minute because Server rejects with 429")
                time.sleep(60)
                wait_next_loop_because_of_timeout = False
            logger.info("Awaiting new HTTP POST Job in Thread...")
            # Blocking
            entry = self.__message_queue.get()
            logger.info("Received new HTTP Post Job in Thread.")
            try:
                logger.info(f"Sending Request to {entry.endpoint}")
                response = requests.post(entry.endpoint, json=entry.body,
                                         headers={"Authorization": configuration.api_key})
                status_code = response.status_code

                from classes.ui import ui
                if status_code == 200:
                    continue  # Server is Happy w/ Response. New Kill/Died-Entry has been created
                elif status_code == 400:
                    # Server complains about something where the client is at fault.
                    HttpThread.__write_ui_message(f"PvpBot Backend rejected an event for the following "
                                                  f"reason:\n{response.text}")
                elif status_code == 401:
                    # Server complains about bad Auth
                    HttpThread.__write_ui_message("PvpBot rejected your API Key. Make sure it is correct.")
                elif status_code == 429:
                    # Too many requests. Block this thread for a minute and retry
                    HttpThread.__write_ui_message("PvpBot complains about too many requests. "
                                                  "Waiting a minute and retrying.")
                    self.__message_queue.put(entry)
                    wait_next_loop_because_of_timeout = True
                elif status_code == 500:
                    # Internal Server Error
                    HttpThread.__write_ui_message("PvpBots Backend shit the bed :). Your Request is dropped.")
                else:
                    HttpThread.__write_ui_message(f"PvpBot Responded w/ {str(status_code)} unexpectedly.")

            except requests.exceptions.ConnectionError as ex:
                logger.exception(ex)
                from classes.ui import ui
                ui.notify_about_new_warning("Error connecting to Server. See logs for more infos.")
            except Exception as ex:
                error_str = str(ex)
                logger.exception(ex)
                # Inline Import to avoid Circular Dependency
                from classes.ui import ui
                ui.notify_about_new_warning(f"Pvp Bot Failed with the following Error:\n{error_str}")

    def __init__(self, baseurl: str = "http://localhost:8080"):
        self.__baseurl = baseurl
        self.__message_queue: queue.Queue[_PostCommand] = queue.Queue()

        self.__thread = threading.Thread(name="pvpbot-http-sender-thread", target=self.__thread_loop)
        self.__thread.start()

    def push_new_message(self, endpoint: str, post_body: dict):
        command = _PostCommand(f"{self.__baseurl}{endpoint}", post_body)
        self.__message_queue.put(command)


@dataclass
class DiedVictimInfo:
    name: str
    ship: str
    rank: int


def timestamp_to_unix(stamp: str) -> int:
    # e.g: "2020-03-12T12:49:54Z"
    date_time_obj = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    unix_stamp = int(date_time_obj.timestamp())
    return unix_stamp


def convert_named_rank_to_number(rank_named: str) -> int:
    as_lower = rank_named.lower().strip()
    if as_lower == "harmless":
        return 0
    if as_lower == "mostly harmless":
        return 1
    if as_lower == "novice":
        return 2
    if as_lower == "competent":
        return 3
    if as_lower == "expert":
        return 4
    if as_lower == "master":
        return 5
    if as_lower == "dangerous":
        return 6
    if as_lower == "deadly":
        return 7
    if as_lower == "elite":
        return 8
    else:
        return -1  # Undefined state


_http_handler = HttpThread(__PVP_BOT_SERVER_URL)


def handle_died_event(own_cmdr_name: str, own_rank: int, event: dict[str, any], current_ship: str | None):
    event_dict_keys = event.keys()
    if "KillerName" not in event_dict_keys and "Killers" not in event_dict_keys:
        # There was no Killer, self-inflicted death. No need to log
        return

    killers: list[DiedVictimInfo] = []

    if "KillerName" in event_dict_keys:
        # There is just one Killer
        if not str(event["KillerName"]).upper().startswith("CMDR "):
            # We died to an NPC, Station, or something like that. Not a CMDR. ignore.
            return
        only_killer = DiedVictimInfo(
            str(event["KillerName"]),
            str(event["KillerShip"]),
            convert_named_rank_to_number(str(event["KillerRank"]))
        )
        killers.append(only_killer)
    elif "Killers" in event_dict_keys:
        # There are multiple killers in a wing
        killers_array = event["Killers"]
        for killer in killers_array:
            if not str(killer["Name"]).upper().startswith("CMDR "):
                # This killer an NPC. Ignore.
                continue
            this_killer = DiedVictimInfo(
                str(killer["Name"]),
                str(killer["Ship"]),
                convert_named_rank_to_number(str(killer["Rank"]))
            )

            killers.append(this_killer)

    # At this Point all Killers are aggregated.
    if len(killers) <= 0:
        # No player killers. Drop event
        return

    # Go through all Killers and strip their Cmdr Prefix
    for entry in killers:
        name_without_cmdr_prefix = entry.name.split(" ", 1)[1]
        entry.name = name_without_cmdr_prefix

    unix_timestamp = timestamp_to_unix(event["timestamp"])
    killers_dict = [{"name": f.name, "ship": f.ship, "rank": f.rank} for f in killers]

    post_body = {
        "timestamp": unix_timestamp,
        "victim": {
            "name": own_cmdr_name,
            "ship": current_ship,
            "rank": own_rank
        },
        "killers": killers_dict
    }

    _http_handler.push_new_message("/died", post_body)


def handle_kill_event(own_cmdr_name: str, own_rank: int, event: dict[str, any], current_ship: str | None):
    cmdr_name = str(event["Victim"])
    combat_rank = int(event["CombatRank"])
    timestamp_str = str(event["timestamp"])
    unix_timestamp = timestamp_to_unix(timestamp_str)

    post_body = {
        "timestamp": unix_timestamp,
        "killers": [{
            "name": own_cmdr_name,
            "ship": current_ship,
            "rank": own_rank
        }],
        "victim": {
            "name": cmdr_name,
            "rank": combat_rank
        }
    }

    _http_handler.push_new_message("/kill", post_body)
