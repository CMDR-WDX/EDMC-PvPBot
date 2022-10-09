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

from typing import Optional
import tkinter as tk



class UI:
    def __init__(self):
        self.__frame: Optional[tk.Frame] = None
        self.__display_outdated_version = False

    def update_ui(self):
        pass

    def set_frame(self, frame: tk.Frame):
        self.__frame = tk.Frame(frame)
        self.__frame.grid(column=0, columnspan=frame.grid_size()[1], sticky=tk.W)
        self.__frame.bind("<<Refresh>>", lambda _: self.update_ui())

    # call from thread
    def notify_version_outdated(self):
        self.__display_outdated_version = True
        # Note that it is not allowed to update the UI from any Thread that is not main.
        # One has to use an Event instead. In the next UI cycle, tkinter will call self.update_ui() on the
        # main thread as it was bound to this event in the set_frame-Method.
        self.__frame.event_generate("<<Refresh>>")

    # call from Button
    def notify_version_button_dismiss_clicked(self):
        self.__display_outdated_version = False
        self.update_ui()


