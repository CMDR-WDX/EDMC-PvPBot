import datetime
from dataclasses import dataclass
import requests
from classes.plugin_settings import configuration
from classes.logger_factory import logger

__PVP_BOT_SERVER_URL = "http://localhost:8080"


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


def send_to_server(endpoint: str, data: dict, on_fail_callback=None):
    # FIXME: This throws errors, breaking the catchAll-Exception if an Error occurs in the request (e.g. Port Closed)
    try:
        requests.post(f"{__PVP_BOT_SERVER_URL}{endpoint}", json=data, headers={"Authorization": configuration.api_key})
    except Exception as e:
        logger.exception(e)
        if on_fail_callback is not None:
            on_fail_callback(str(e))


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

    send_to_server("/died", post_body)


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

    print("sending post")
    send_to_server("/kill", post_body)

