import classes.plugin_settings as settings
import classes.event_handling as events
from classes.plugin_settings import configuration
from classes.logger_factory import logger
from classes.version_check import build_worker as build_version_check_logger
from classes.ui import GenericUiMessage, GenericUiMessageType, ui
from classes.historic_data import HistoricDataManager
from os.path import basename, dirname
import tkinter

from typing import Any


def plugin_app(parent: tkinter.Frame) -> tkinter.Frame:
    ui.set_frame(parent)

    if configuration.run_historic_aggregation_on_next_startup:
        HistoricDataManager(configuration.allowed_cmdrs, None, None, ui.get_historic_ui())

    if len(configuration.api_key or "") == 0:
        no_api_key_error = GenericUiMessage("PvpBot requires an API Key\nHead to the Settings Panel and enter an API Key", GenericUiMessageType.ERROR, 5000)
        ui.notify_about_new_message(no_api_key_error, False) # This must be false, followed by an .update_ui() because we 
        ui.update_ui()                                       # cannot generate an Event from the main thread!
    else:
        events.check_api_key()

    return parent


def plugin_start3(_path: str) -> str:
    logger.info("Starting PVP Bot Plugin")

    if configuration.check_updates:
        logger.info("Starting Update Check in new Thread...")

        def notify_ui_on_outdated(is_outdated: bool):
            if is_outdated:
                ui.notify_version_outdated()

        thread = build_version_check_logger(notify_ui_on_outdated)
        thread.start()
    else:
        logger.info("Skipping Update Check. Disabled in Settings")

    return basename(dirname(__file__))


def plugin_prefs(parent: Any, _cmdr: str, _is_beta: bool):
    return settings.build_settings_ui(parent)


def prefs_changed(_cmdr: str, _is_beta: bool):
    settings.push_new_changes()


def _is_cmdr_valid(cmdr: str) -> bool:
    if not configuration.has_commander_filter_enabled:
        return True
    return cmdr.upper() in map(str.upper, configuration.allowed_cmdrs)


def journal_entry(cmdr: str, _is_beta: bool, _system: str,
                  _station: str, entry: dict[str, Any], state: dict[str, Any]):

    # First Check if this is a PVPKill or Died event
    if entry["event"] not in ["Died", "PVPKill"]:
        return
    # Now check if the CMDR should be skipped due to settings
    if not _is_cmdr_valid(cmdr):
        return
    # Aggregate some additional data
    ship_current_flying: str | None = state["ShipType"]
    own_rank, _ = state["Rank"]["Combat"]
    # At this point only "valid" CMDRs are remaining.
    try:
        if entry["event"] == "Died":
            events.handle_died_event(cmdr, own_rank, entry, ship_current_flying)
        elif entry["event"] == "PVPKill":
            events.handle_kill_event(cmdr, own_rank, entry, ship_current_flying)
    except Exception as e:
        # Catchall just in Case
        logger.exception(e)
        ui.notify_about_new_message(GenericUiMessage(str(e), GenericUiMessageType.ERROR, 10_000))




