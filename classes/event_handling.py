from enum import Enum
import queue
import threading
import time
from dataclasses import dataclass
import requests
from classes.plugin_settings import configuration
from classes.logger_factory import logger
from typing import Callable, Optional
from classes.data import create_kill_from_died_event, create_pvpkill_event, PvpKillEventData
from config import Any

__PVP_BOT_SERVER_URL = "http://api.gankers.org"


class MessageIntent(Enum):
    CHECK_API_KEY = 0
    SEND_NEW_EVENT = 1



@dataclass
class _HttpCommand:
    endpoint: str
    body: dict | list[dict]
    intent: MessageIntent
    method: str = "post"
    extra: Optional[dict] = None

def build_headers():
    auth = configuration.api_key
    import classes.version_check
    version = classes.version_check.get_current_version_string()
    return {
        "Authorization": f"Bearer {auth}",
        "X-PvpBot-Version": version,
        "Accept": "application/json"
    }

class HttpThread:
    """
    Messages to the Backend are done here to not block the Main Thread. If there was an issue here,
    the listeners (self.__callbacks) will get invoked - one of these Callbacks should be the UI. It can
    then display the error on the UI.
    """

    @staticmethod
    def __write_ui_error_message(msg: str, duration_millis = 5000):
        from classes.ui import ui, GenericUiMessage, GenericUiMessageType
        message = GenericUiMessage(msg, GenericUiMessageType.ERROR, duration_millis)
        ui.notify_about_new_message(message, True)

    @staticmethod
    def __write_ui_warning_message(msg: str, duration_millis = 5000):
        from classes.ui import ui, GenericUiMessage, GenericUiMessageType
        message = GenericUiMessage(msg, GenericUiMessageType.WARNING ,duration_millis)
        ui.notify_about_new_message(message, True)

    @staticmethod
    def __write_ui_info_message(msg: str, duration_millis = 5000):
        from classes.ui import ui, GenericUiMessage, GenericUiMessageType
        message = GenericUiMessage(msg, GenericUiMessageType.INFO, duration_millis)
        ui.notify_about_new_message(message, True)

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
                response = None
                if entry.method == "post":
                    response = requests.post(entry.endpoint, json=entry.body, headers=build_headers())
                if entry.method == "get":
                    response = requests.get(entry.endpoint, headers=build_headers())
                if response is None:
                    return

                status_code = response.status_code
                
                if status_code == 200:
                    if entry.intent == MessageIntent.CHECK_API_KEY:
                        HttpThread.__write_ui_info_message("PvpBot: API Key is valid")
                    elif entry.intent == MessageIntent.SEND_NEW_EVENT:
                        HttpThread.__write_ui_info_message("PvpBot: Server acknowledged Event.")
                    continue  # Server is Happy w/ Response. New Kill/Died-Entry has been created
                elif status_code == 400:
                    # Server complains about something where the client is at fault.
                    error_message = f"PvpBot Backend rejected an event for the following reason:\n{response.text}" # type: ignore
                    HttpThread.__write_ui_error_message(error_message)
                elif status_code == 401:
                    # Server complains about bad Auth
                    HttpThread.__write_ui_error_message("PvpBot rejected your API Key. Make sure it is correct.", -1)
                elif status_code == 404:
                    HttpThread.__write_ui_error_message("PvpBot doesnt know this API Endpoint. This should not happen.")
                elif status_code == 429:
                    # Too many requests. Block this thread for a minute and retry
                    HttpThread.__write_ui_warning_message("PvpBot complains about too many requests. "
                                                  "Waiting a minute and retrying.")
                    self.__message_queue.put(entry)
                    wait_next_loop_because_of_timeout = True
                elif status_code == 500:
                    # Internal Server Error
                    HttpThread.__write_ui_error_message("PvpBots Backend shit the bed :). Your Request is dropped.")
                else:
                    HttpThread.__write_ui_warning_message(f"PvpBot Responded w/ {str(status_code)} unexpectedly.")

            except requests.exceptions.ConnectionError as ex:
                logger.exception(ex)
                HttpThread.__write_ui_error_message("Error connecting to Server. See logs for more infos.")
            except Exception as ex:
                error_str = str(ex)
                logger.exception(ex)
                HttpThread.__write_ui_error_message(f"Pvp Bot Plugin Failed with the following Error:\n{error_str}")

    def __init__(self, baseurl: str):
        self.__baseurl = baseurl
        self.__message_queue: queue.Queue[_HttpCommand] = queue.Queue()

        self.__thread = threading.Thread(
            name="pvpbot-http-sender-thread", target=self.__thread_loop, daemon=True)
        self.__thread.start()
    

    def push_new_post_message(self, endpoint: str, post_body: list[dict] | dict, intent: MessageIntent):
        command = _HttpCommand(endpoint, post_body, intent)
        self.push_raw(command)

    def push_raw(self, cmd: _HttpCommand):
        cmd.endpoint = f"{self.__baseurl}{cmd.endpoint}"
        self.__message_queue.put(cmd)


_http_handler = HttpThread(__PVP_BOT_SERVER_URL)


def handle_died_event(own_cmdr_name: str, own_rank: int, event: dict[str, Any], current_ship: str | None):
    post_body = create_kill_from_died_event(event, own_cmdr_name, current_ship, own_rank)
    if post_body is not None:
        push_kill_event(post_body)


def handle_kill_event(own_cmdr_name: str, own_rank: int, event: dict[str, Any], current_ship: str | None):
    post_body = create_pvpkill_event(event, own_cmdr_name, current_ship or "unknown", own_rank)
    if post_body is not None:
        push_kill_event(post_body)


def push_kill_event(data: PvpKillEventData):
    _http_handler.push_new_post_message("/api/killboard/add/kill", data.as_dict(), MessageIntent.SEND_NEW_EVENT)


def check_api_key():
    cmd = _HttpCommand("/api/user", {}, MessageIntent.CHECK_API_KEY, "get" )
    _http_handler.push_raw(cmd)


def handle_historic_data(data: list[PvpKillEventData], callback: Callable[[bool], None]):
    """
    NOTE: This is supposed to run from the Event Aggregation Thread.
    DO NOT RUN THIS FROM ANOTHER THREAD.
    This call is blocking.
    """
    import json
    as_list = list(map(lambda x: x.as_dict(), data))
    post_body = {
        "kills": as_list
    }
    logger.info("Next Line contains Post Body sent as the Aggregate event. POST_BODY_AGGREGATE")
    logger.info(json.dumps(post_body))
    #_http_handler.push_new_post_message("/api/killboard/add/kill/bulk", post_body)

    # Used for debugging to not spam the Server
    DEBUG_REDIRECT_COMMAND = False

    if DEBUG_REDIRECT_COMMAND:
        time.sleep(1)
        callback(True)
        return


    # vvv Blocking vvv
    response = requests.post(f"{__PVP_BOT_SERVER_URL}/api/killboard/add/kill/bulk", json=post_body, headers=build_headers())
    if not response.ok:
        # Bad Status Code
        logger.error(response.raw)
        callback(False)
        return
    logger.info(f"Historic Data was accepted by {__PVP_BOT_SERVER_URL}")
    logger.info(response.raw)
    callback(True)
