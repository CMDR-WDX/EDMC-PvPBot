"""
This Module contains logic to create and update the UI. Note that plugin usually provides an empty
UI.
The user will see UI elements generated by this plugin in the following cases:
* a new Version is available
* the API key is invalid
* any other basic Error messages

Parts of the code here are taken from https://github.com/CMDR-WDX/EDMC-Massacres/blob/master/classes/ui.py, mainly
the pattern around the UI class.
"""
from dataclasses import dataclass
from enum import Enum
import threading
import time

from classes.logger_factory import logger
from classes.version_check import open_download_page
from typing import Optional
import tkinter as tk
from theme import theme
from typing import Callable


class GenericUiMessageType(Enum):
    INFO = 1
    WARNING = 2
    ERROR = 3
    TEST = 4


    
@dataclass
class GenericUiMessage:
    """
    This is a generic UI Message. It contains a text message,
    a type (which determines the colour used), and a duration for
    how long the Message should stay up.
    """
    message: str
    messageType: GenericUiMessageType
    messageDurationMillis: int = 0
    """
    How long should the message stay up (in ms). If value is 0 or negative, it stays on until replaced by a new message.
    """
    emitRefreshEvent = False
    """
    If a Refresh-Event needs to be emitted.
    """



def _display_outdated_version(frame: tk.Frame, row_counter: int) -> int:
    sub_frame = tk.Frame(frame)
    sub_frame.grid(row=row_counter, sticky=tk.EW)
    sub_frame.config(pady=10)
    tk.Label(sub_frame, text="PvpBot Plugin is Outdated").grid(row=0, column=0, columnspan=2)
    btn_github = tk.Button(sub_frame, text="Go to Download", command=open_download_page)
    btn_dismiss = tk.Button(sub_frame, text="Dismiss", command=ui.notify_version_button_dismiss_clicked)

    for i, item in enumerate([btn_github, btn_dismiss]):
        item.grid(row=1, column=i)
    theme.update(sub_frame)

    return row_counter+1


class _ResettableTimer:
    def __init__(self, callback: Callable):
        self.__current_valid_thread = 0
        self.__callback = callback
        self.__thread : Optional[threading.Thread] = None
        self.__mutex = threading.Lock()

    def reset_timer(self):
        """
        This "invalidates" the Thread as it does a check if its own ID is still the active one.
        Is also used to stop the current thread without a re-emit - which is useful if you want for a message to stay indefinetely.
        """
        self.__current_valid_thread += 1

    def emit_after_millis(self, millis: int):
        self.__mutex.acquire()
        try:
            self.reset_timer()

            thread_id = self.__current_valid_thread

            def thread_loop():
                time.sleep(millis / 1000)
                self.__mutex.acquire()
                try:
                    if thread_id == self.__current_valid_thread:
                        if self.__callback is not None:
                            self.__callback()
                finally:
                    self.__mutex.release()

            self.__thread = threading.Thread(target=thread_loop, daemon=True, name=f"edmc-pvpbot-timer-{thread_id}")
            self.__thread.start()
        finally:
            self.__mutex.release()



class HistoryAggregatorUI:
    """
    This class is responsible for handling the UI during the historic aggregation process
    Its main purpose is to show a progress, and, if there were any Errros, notify the user
    that they can read the broken files in the logs.
    """
    class __State(Enum):
        """
        This UI will go through these States
        IDLE -> FINDING LOGS -> READING LOGS -> SENDING TO SERVER -> FAILED | FINISHED -> IDLE
        """
        IDLE = 0
        FINDING_LOGS = 1
        READING_LOGS = 2
        SENDING_TO_SERVER = 3
        FAILED = 4
        FINISHED = 5


    def __init__(self, refreshCallback: Callable) -> None:
        """
        @param refreshCallback - Callback to be invoked to make the UI rerender its state.
        """
        self.__errored_logs: list[str] = []
        self.__status: HistoryAggregatorUI.__State = HistoryAggregatorUI.__State.IDLE
        self.__current_parsed: int = -1
        self.__total_logs: int = -1
        self.__refreshCallback = refreshCallback
 
    def __build_progress_string(self) -> str:
        if self.__total_logs <= 0 or self.__current_parsed < 0:
            return ""
        bar_length = 50
        completed_segments = int((self.__current_parsed / self.__total_logs) * bar_length)
        todo_segments = bar_length - completed_segments

        progressbar = ":"*completed_segments+"."*todo_segments

        return f"{progressbar} ({self.__current_parsed}/{self.__total_logs})"

    ### The Methods below are in order of when they are invoked
    def notify_start(self):
        self.__status = HistoryAggregatorUI.__State.FINDING_LOGS
        self.__refreshCallback()

    def notify_progress(self, current: int, total: int):
        self.__status = HistoryAggregatorUI.__State.READING_LOGS
        self.__current_parsed = current
        self.__total_logs = total
        self.__refreshCallback()

    def notify_failed_log_file(self, filename: str):
        self.__errored_logs.append(filename)


    def notify_submitting(self):
        self.__status = HistoryAggregatorUI.__State.SENDING_TO_SERVER


    def notify_finished(self, was_succesful: bool):
        """
        This is expected to be run from the Historic Data Thread.
        This call does a sleep and blocks
        """
        if not was_succesful:
            self.__status = HistoryAggregatorUI.__State.FAILED
            self.__refreshCallback()
            time.sleep(10.0)
            self.__status = HistoryAggregatorUI.__State.IDLE
            self.__refreshCallback()
        else:
            self.__status = HistoryAggregatorUI.__State.FINISHED
            self.__refreshCallback()
                    
    ###


    def is_running(self):
        return self.__State != HistoryAggregatorUI.__State.IDLE

    def update_ui(self, frame:tk.Frame, current_counter: int) -> int:
        """
        This method should only be invoked by the Parent UI class during the rebuild
        This method is to be invoked from the main thread only!
        """
        if not self.is_running:
            return current_counter

        if self.__status == HistoryAggregatorUI.__State.FAILED:
            tk.Label(frame, text="The Server could not parse the response. You can find more information in the EDMC Logs", fg="red")\
                .grid(column=0, columnspan=1, row=current_counter)
            def close_callback():
                self.__status = HistoryAggregatorUI.__State.IDLE
                self.__refreshCallback()
            tk.Button(frame, text="Close Error", fg="red", command=lambda : close_callback())\
                .grid(column=0, columnspan=1, row=current_counter+1)
            return current_counter+2
        else:
            message: str = ""
            colour: str = "yellow"
            if self.__status == HistoryAggregatorUI.__State.FINDING_LOGS:
                message = "PvpBot: Finding Journal Files to read.."
            elif self.__status == HistoryAggregatorUI.__State.READING_LOGS:
                message = self.__build_progress_string()
            elif self.__status == HistoryAggregatorUI.__State.SENDING_TO_SERVER:
                message = "Uploading Logs to Server..."
            elif self.__status == HistoryAggregatorUI.__State.FINISHED:
                message = "Uploaded Logs to Server successfully."
                colour = "green"
            # TODO: Add Statements here
            tk.Label(frame, text=message, fg=colour)\
                .grid(column=0, columnspan=1, row=current_counter)
            return current_counter+1

        
      


        
        






class UI:
    def __init__(self):
        self.__frame: Optional[tk.Frame] = None
        self.__display_outdated_version = False
        self.__current_message: Optional[GenericUiMessage] = None
        self.__timer = _ResettableTimer(lambda: self.notify_about_new_message(None, True))
        self.__historic_data_ui: Optional[HistoryAggregatorUI] = None

    def update_ui(self):
        if self.__frame is None:
            logger.warning("UI Frame is not yet set up. The UI was not updated.")
            return
        logger.info("Updating UI...")
        # Remove all Children of Frame and rebuild
        for child in self.__frame.winfo_children():
            child.destroy()
        
        row_pointer = 0
        historic_ui = self.get_historic_ui()
        if historic_ui is not None:
            row_pointer = historic_ui.update_ui(self.__frame, 0)
        if self.__display_outdated_version:
            row_pointer = _display_outdated_version(self.__frame, row_pointer)
        if self.__current_message is not None:
            # Display the message
            color = "yellow"
            if self.__current_message.messageType == GenericUiMessageType.INFO:
                color = "white"
            elif self.__current_message.messageType == GenericUiMessageType.WARNING:
                color = "yellow"
            elif self.__current_message.messageType == GenericUiMessageType.ERROR:
                color = "red"
            elif self.__current_message.messageType == GenericUiMessageType.TEST:
                color = "blue"

            tk.Label(self.__frame, text=self.__current_message.message, fg=color)\
                .grid(column=0, columnspan=1, row=row_pointer)
            row_pointer += 1


        if len(self.__frame.winfo_children()) == 0:
            # Put in one Empty child to update size
            empty_child = tk.Frame(self.__frame)
            empty_child.pack()

        theme.update(self.__frame)
        logger.info("UI Update Complete")

    def set_frame(self, frame: tk.Frame):
        self.__frame = tk.Frame(frame)
        self.__frame.grid(column=0, columnspan=frame.grid_size()[1], sticky=tk.W)
        self.__frame.bind("<<Refresh>>", lambda _: self.update_ui())
        self.__historic_data_ui = HistoryAggregatorUI(lambda : self.notify_about_new_message(None))

    def get_historic_ui(self):
        return self.__historic_data_ui
    
    # is thread-safe
    def notify_about_new_message(self, message: Optional[GenericUiMessage], send = True):
        self.__current_message = message
        if message is not None: 
            if message.messageDurationMillis <= 0:
                # Resets the Message without sending out a new timed event to clear. 
                # This way the message stays on until a new message overrides it.
                self.__timer.reset_timer()
            else:
                self.__timer.emit_after_millis(message.messageDurationMillis)
        if self.__frame is not None and send:
            self.__frame.event_generate("<<Refresh>>")

    # is thread-safe
    def notify_version_outdated(self):
        self.__display_outdated_version = True
        # Note that it is not allowed to update the UI from any Thread that is not main.
        # One has to use an Event instead. In the next UI cycle, tkinter will call self.update_ui() on the
        # main thread as it was bound to this event in the set_frame-Method.
        if self.__frame is not None:
            self.__frame.event_generate("<<Refresh>>")

    # call from Button
    def notify_version_button_dismiss_clicked(self):
        self.__display_outdated_version = False
        self.update_ui()


ui = UI()
