"""
This Module is used to create Dataclasses for PVPKill and Died Events
"""
from dataclasses import dataclass
import datetime
from typing import Optional

from classes.plugin_settings import configuration


@dataclass
class CommanderEntry:
    name: str
    ship: Optional[str]
    rank: int

    def as_dict(self):
        if self.ship is None:
            self.ship = "unknown"
        elif len(self.ship) == 0:
            self.ship = "unknown"
        if self.ship is None:
            return {
                "name": self.name,
                "rank": self.rank
            }
        return {
            "name": self.name,
            "ship": self.ship,
            "rank": self.rank
        }


@dataclass
class PvpKillEventData:
    timestamp: int
    victim: CommanderEntry
    killer: CommanderEntry
    location: Optional[str] = None
    log_origin: Optional[str] = None

    def as_dict(self):
        dictionary =  {
            "timestamp": self.timestamp,
            "victim": self.victim.as_dict(),
            "killer": self.killer.as_dict()
        }
        if self.location is not None and configuration.send_location:
            dictionary["location"] = self.location
        return dictionary


__rank_lookup = {
    "harmless": 0,
    "mostly harmless": 1,
    "novice": 2,
    "competent": 3,
    "expert": 4,
    "master": 5,
    "dangerous": 6,
    "deadly": 7,
    "elite": 8,
}


def __convert_rank_string_to_int(rank: str) -> int:
    keys = __rank_lookup.keys()
    rank = rank.lower()
    if rank not in keys:
        return -1
    return __rank_lookup[rank]


def __timestamp_to_unix(stamp: str) -> int:
    # e.g: "2020-03-12T12:49:54Z"
    date_time_obj = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    unix_stamp = int(date_time_obj.timestamp())
    return unix_stamp


def create_kill_from_died_event(event: dict, self_cmdr: Optional[str], self_ship: Optional[str], self_rank: Optional[int], location: Optional[str]) -> Optional[PvpKillEventData]:
    event_dict_keys = event.keys()
    if "KillerName" not in event_dict_keys and "Killers" not in event_dict_keys:
        # There was no Killer, self-inflicted death. No need to log
        return None
    
    if self_cmdr is None:
        return None

    if self_ship is None:
        self_ship = "unknown"

    if self_rank is None:
        self_rank = -1;

    killers: list[CommanderEntry] = []

    if "KillerName" in event_dict_keys:
        # There is just one Killer
        if not str(event["KillerName"]).upper().startswith("CMDR "):
            # We died to an NPC, Station, or something like that. Not a CMDR. ignore.
            return None
        only_killer = CommanderEntry(
            str(event["KillerName"]),
            str(event["KillerShip"]),
            __convert_rank_string_to_int(str(event["KillerRank"]))
        )
        killers.append(only_killer)
    elif "Killers" in event_dict_keys:
        # There are multiple killers in a wing
        killers_array = event["Killers"]
        for killer in killers_array:
            if not str(killer["Name"]).upper().startswith("CMDR "):
                # This killer an NPC. Ignore.
                continue
            this_killer = CommanderEntry(
                str(killer["Name"]),
                str(killer["Ship"]),
                __convert_rank_string_to_int(str(killer["Rank"]))
            )

            killers.append(this_killer)

    # At this Point all Killers are aggregated.
    if len(killers) <= 0:
        # No player killers. Drop event
        return None

    # Go through all Killers and strip their Cmdr Prefix
    for entry in killers:
        name_without_cmdr_prefix = entry.name.split(" ", 1)[1]
        entry.name = name_without_cmdr_prefix

    unix_timestamp = __timestamp_to_unix(event["timestamp"])

    victim = CommanderEntry(self_cmdr, self_ship, self_rank)

    return PvpKillEventData(unix_timestamp, victim, killers[0], location)


def create_pvpkill_event(event: dict, self_cmdr: Optional[str], self_ship: Optional[str], self_rank: Optional[int], location: Optional[str]):
    if self_cmdr is None or self_ship is None or self_rank is None:
        return None

    victim_name = str(event["Victim"])
    combat_rank = int(event["CombatRank"])
    timestamp_str = str(event["timestamp"])
    unix_timestamp = __timestamp_to_unix(timestamp_str)

    victim = CommanderEntry(victim_name, None, combat_rank)
    killer = CommanderEntry(self_cmdr, self_ship, self_rank)

    return PvpKillEventData(unix_timestamp, victim, killer, location)

