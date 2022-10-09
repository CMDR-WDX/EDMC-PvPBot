"""
A wrapper around EDMCs Configuration. The pattern seen here has been taken from the EDMC-Massacre plugin
See https://github.com/CMDR-WDX/EDMC-Massacres/blob/master/classes/massacre_settings.py
"""
import os.path
import tkinter as tk
import myNotebook as nb
import string

from config import config
from ttkHyperlinkLabel import HyperlinkLabel


class Configuration:
    """
    Abstraction around the config store
    """
    @property
    def check_updates(self):
        return config.get_bool(f"{self.plugin_name}.check_updates", default=True)

    @check_updates.setter
    def check_updates(self, value: bool):
        config.set(f"{self.plugin_name}.check_updates", value)

    @property
    def allowed_cmdrs(self):
        as_str = config.get_str(f"{self.plugin_name}.allowed_cmdrs", default="")
        names = [f.strip() for f in as_str.split(",") if len(f.strip()) > 0]
        return names

    @allowed_cmdrs.setter
    def allowed_cmdrs(self, new_list: list[str]):
        as_str = ",".join(new_list)
        config.set(f"{self.plugin_name}.allowed_cmdrs", as_str)

    @property
    def has_commander_filter_enabled(self):
        return len(self.allowed_cmdrs) > 0

    @property
    def api_key(self):
        key = str.strip(config.get_str(f"{self.plugin_name}.api_key", default=""))
        if len(key) == 0:
            return None
        return key

    @api_key.setter
    def api_key(self, val: str):
        stripped = str.strip(val)
        config.set(f"{self.plugin_name}.api_key", stripped)

    def __init__(self):
        self.plugin_name = os.path.basename(os.path.dirname(__file__))
        self.config_changed_listeners: list[Callable[[Configuration], None]] = []

    def notify_about_changes(self, data: dict[str, tk.Variable]):
        keys = data.keys()

        if "check_updates" in keys:
            self.check_updates = data["check_updates"].get()
        if "allowed_cmdrs" in keys:
            as_str = data["allowed_cmdrs"].get()
            new_list = [f.strip() for f in as_str.split(",") if len(f.strip()) > 0]
            self.allowed_cmdrs = new_list
        if "api_key" in keys:
            self.api_key = data["api_key"].get()


# Quasi Singleton Pattern-ish
configuration = Configuration()

__settings_changes: dict[str, tk.Variable] = {}


def push_new_changes():
    """Invoked by the Settings Window when the user is done changing settings"""
    configuration.notify_about_changes(__settings_changes)
    __settings_changes.clear()


download_url = "https://github.com/CMDR-WDX/EDMC-PvPBot/releases"


def build_settings_ui(root: nb.Notebook) -> tk.Frame:
    title_offset = 20
    input_offset = 10

    frame = nb.Frame(root)
    #frame.columnconfigure(1, weight=1)

    __settings_changes.clear()
    __settings_changes["check_updates"] = tk.BooleanVar(value=configuration.check_updates)
    __settings_changes["allowed_cmdrs"] = tk.StringVar(value=",".join(configuration.allowed_cmdrs))
    __settings_changes["api_key"] = tk.StringVar(value=configuration.api_key)

    nb.Label(frame, text="PVP Bot Settings", pady=10, padx=title_offset).grid(sticky=tk.W)
    nb.Checkbutton(frame, text="Look for Updates on Startup", variable=__settings_changes["check_updates"])\
        .grid(columnspan=2, padx=input_offset, sticky=tk.W)
    nb.Label(frame, justify=tk.LEFT, text="Enter which CMDRs you want to upload to the PVP Bot. This will ignore all other CMDRs. \n"
                         "If you leave this blank, all CMDRs will be uploaded. Your CMDRs should be comma-separated.\n"
                         "For example: 'WDX, Schitt Staynes' will match CMDR WDX and CMDR Schitt Staynes\n")\
        .grid(columnspan=2, padx=input_offset, sticky=tk.SW, pady=0)
    nb.Label(frame, justify=tk.LEFT, text="Allowed CMDRs:").grid(column=0, padx=input_offset, sticky=tk.W)
    allowed_cmdrs_edit_text = nb.Entry(frame, textvariable=__settings_changes["allowed_cmdrs"])
    allowed_cmdrs_edit_text.grid(columnspan=2, padx=input_offset, sticky=tk.EW)
    nb.Label(frame, justify=tk.LEFT, text="API Key:").grid(column=0, padx=input_offset, sticky=tk.W)

    api_key_edit_text = nb.Entry(frame, textvariable=__settings_changes["api_key"])
    api_key_edit_text.grid(columnspan=2, padx=input_offset, sticky=tk.EW)


    nb.Label(frame, text="", pady=10).grid()
    nb.Label(frame, text="Made by Harry Potter and WDX").grid(sticky=tk.W, padx=input_offset)
    HyperlinkLabel(frame, text="View the Code on Github", background=nb.Label().cget("background"),
                   url=download_url, underline=True).grid(columnspan=2, sticky=tk.W, padx=input_offset)
    return frame
