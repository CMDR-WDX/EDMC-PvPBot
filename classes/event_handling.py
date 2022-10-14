import datetime
import queue
import threading
import time
from dataclasses import dataclass
import requests
from classes.plugin_settings import configuration
from classes.logger_factory import logger
from typing import Callable, Optional
from classes.data import create_kill_from_died_event, create_pvpkill_event, PvpKillEventData

__PVP_BOT_SERVER_URL = "http://134.209.21.33"


@dataclass
class _HttpCommand:
    endpoint: str
    body: dict
    method: str = "post"
    extra: Optional[dict] = None


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
            headers = {"Authorization": "Bearer "+configuration.api_key,
                       "Accept": "application/json"}
            try:
                logger.info(f"Sending Request to {entry.endpoint}")
                response = None
                if entry.method == "post":
                    response = requests.post(entry.endpoint, json=entry.body, headers=headers)
                if entry.method == "get":
                    response = requests.get(entry.endpoint, headers=headers)
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
                elif status_code == 404:
                    HttpThread.__write_ui_message("PvpBot doesnt know this API Endpoint. This should not happen.")
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
                ui.notify_about_new_warning(f"Pvp Bot Plugin Failed with the following Error:\n{error_str}")

    def __init__(self, baseurl: str = "http://localhost:8080"):
        self.__baseurl = baseurl
        self.__message_queue: queue.Queue[_HttpCommand] = queue.Queue()

        self.__thread = threading.Thread(name="pvpbot-http-sender-thread", target=self.__thread_loop)
        self.__thread.start()

    def push_new_post_message(self, endpoint: str, post_body: dict):
        command = _HttpCommand(endpoint, post_body)
        self.push_raw(command)

    def push_raw(self, cmd: _HttpCommand):
        cmd.endpoint = f"{self.__baseurl}{cmd.endpoint}"
        self.__message_queue.put(cmd)


_http_handler = HttpThread(__PVP_BOT_SERVER_URL)


def handle_died_event(own_cmdr_name: str, own_rank: int, event: dict[str, any], current_ship: str | None):
    post_body = create_kill_from_died_event(event, own_cmdr_name, current_ship, own_rank)
    push_kill_event(post_body)


def handle_kill_event(own_cmdr_name: str, own_rank: int, event: dict[str, any], current_ship: str | None):
    post_body = create_pvpkill_event(event, own_cmdr_name, current_ship, own_rank)
    push_kill_event(post_body)


def push_kill_event(data: PvpKillEventData):
    _http_handler.push_new_post_message("/api/killboard/add/kill", data.as_dict())


def check_api_key():
    cmd = _HttpCommand("/api/user", {}, "get")
    _http_handler.push_raw(cmd)


def push_kill_event_batch(data: list[PvpKillEventData]):
    # TODO Implement
    pass
