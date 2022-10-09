# EDMC-PvpBot

## What is this
This is a plugin for [Elite Dangerous Market Connector](https://github.com/EDCD/EDMarketConnector).

Its purpose is to communicate with the new Gank Bot. If you get killed, or kill someone, 
this plugin will send that information to the Gank Bot Server.
Your kills can then be queried with the new Discord Bot.

## Usage
Put the plugin in EDMC's Plugin Directory, then start the game and go out there and gank ;)

## File Access
The only times this plugin reads from the Filesystem directly (as opposed to via EDMC) is to read the `version`-File
to compare with the same file on GitHub to see if a new Version can be downloaded.  
Said file access happens in `classes/version_check.py::__get_current_version_string`

Additionally, the Filesystem is accessed when the User has chosen to upload old Died/PVPKill events - as in this
instance the Plugin will manually load old data. This functionality is disabled by default and 
needs to be turned on in the Settings.
## Network Access
This plugin downloads the `version`-File on startup to see if a new version is present.
This feature can be turned off in the Settings. You can look up the implementation in 
`classes/version_check.py::__is_current_version_outdated` 

This plugin will also make POST-Requests to the Gank Bot Backend. 
The implementation can be found in `classes/event_handling.py::HttpThread::__thread_loop`

### What type of Data does the Backend Receive?
`Died`- and `PVPKill`-Events are the only events this Plugin cares about.
The Backend will receive the **CMDR Name**, **Ship** and **Combat Rank** for both Killer and Victim. That is all.

Below you can see some example POST-Bodies:
```json
// /kill Endpoint
{
  "timestamp": 1584017394,
  "killers": [
    {
      "name": "WDX",
      "ship": "anaconda",
      "rank": 3
    }
  ],
  "victim": {
    "name": "Name of Victim Cmdr",
    "rank": 4
  }
}

// /died Endpoint
{
  "timestamp": 1648501269,
  "victim": {
    "name": "WDX",
    "ship": "TestShip",
    "rank": 4
  },
  "killers": [
    {
      "name": "Attacker1",
      "ship": "diamondback",
      "rank": 2
    }
  ]
}

// /died Endpoint with multiple Killers
{
  "timestamp": 1648412088,
  "victim": {
    "name": "WDX",
    "ship": "TestShip",
    "rank": 4
  },
  "killers": [
    {
      "name": "Attacker1",
      "ship": "anaconda",
      "rank": 8
    },
    {
      "name": "Attacker2",
      "ship": "anaconda",
      "rank": 4
    }
  ]
}
```