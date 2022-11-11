#
# KodeBlox Copyright 2019 Sayak Mukhopadhyay
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http: //www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import functools
import logging
import threading
import tkinter as tk
from os.path import dirname, join

import semantic_version
import sys
import time

import l10n
import myNotebook as nb
from config import config, appname, appversion
from py_discord_sdk import discordsdk as dsdk

plugin_name = "DiscordPresence"

logger = logging.getLogger(f'{appname}.{plugin_name}')

_ = functools.partial(l10n.Translations.translate, context=__file__)

CLIENT_ID = 386149818227097610

VERSION = '3.1.0'

this = sys.modules[__name__]  # For holding module globals

czLocation = "" # To hold combat zone location
superCruise = "" # To hold flag for supercruising
bodyName = "" # To hold body name
taxiDestination = "" # To hold taxi destination
stationGuess = "" # To hold station name if EDMC does not detect a station
srvName = "" # To hold name of SRV model

def callback(result):
    logger.info(f'Callback: {result}')
    if result == dsdk.Result.ok:
        logger.info("Successfully set the activity!")
    elif result == dsdk.Result.transaction_aborted:
        logger.warning(f'Transaction aborted due to SDK shutting down: {result}')
    else:
        logger.error(f'Error in callback: {result}')
        raise Exception(result)


def update_presence():
    if isinstance(appversion, str):
        core_version = semantic_version.Version(appversion)

    elif callable(appversion):
        core_version = appversion()

    logger.info(f'Core EDMC version: {core_version}')
    if core_version < semantic_version.Version('5.0.0-beta1'):
        logger.info('EDMC core version is before 5.0.0-beta1')
        if config.getint("disable_presence") == 0:
            this.activity.state = this.presence_state
            this.activity.details = this.presence_details
            
    else:
        logger.info('EDMC core version is at least 5.0.0-beta1')
        if config.get_int("disable_presence") == 0:
            this.activity.state = this.presence_state
            this.activity.details = this.presence_details

    this.activity.timestamps.start = int(this.time_start)
    this.activity_manager.update_activity(this.activity, callback)


def plugin_prefs(parent, cmdr, is_beta):
    """
    Return a TK Frame for adding to the EDMC settings dialog.
    """
    if isinstance(appversion, str):
        core_version = semantic_version.Version(appversion)

    elif callable(appversion):
        core_version = appversion()

    logger.info(f'Core EDMC version: {core_version}')
    if core_version < semantic_version.Version('5.0.0-beta1'):
        logger.info('EDMC core version is before 5.0.0-beta1')
        this.disablePresence = tk.IntVar(value=config.getint("disable_presence"))
    else:
        logger.info('EDMC core version is at least 5.0.0-beta1')
        this.disablePresence = tk.IntVar(value=config.get_int("disable_presence"))

    frame = nb.Frame(parent)
    nb.Checkbutton(frame, text="Disable Presence", variable=this.disablePresence).grid()
    nb.Label(frame, text='Version %s' % VERSION).grid(padx=10, pady=10, sticky=tk.W)

    return frame


def prefs_changed(cmdr, is_beta):
    """
    Save settings.
    """
    config.set('disable_presence', this.disablePresence.get())
    update_presence()


def plugin_start3(plugin_dir):
    this.plugin_dir = plugin_dir
    this.discord_thread = threading.Thread(target=check_run, args=(plugin_dir,))
    this.discord_thread.setDaemon(True)
    this.discord_thread.start()
    return 'DiscordPresence'


def plugin_stop():
    this.activity_manager.clear_activity(callback)
    this.call_back_thread = None


def journal_entry(cmdr, is_beta, system, station, entry, state):
    global bodyName 
    global czLocation 
    global superCruise
    global taxiDestination
    global stationGuess
    global srvName
    
    presence_state = this.presence_state
    presence_details = this.presence_details
    
    if entry['event'] == 'Location':
        if "OnFoot" in entry: # Check If the entry contains the OnFoot boolean
            if entry['OnFoot'] == True: # If player is on foot
                if entry['BodyType'] == "Station": # If the player is at a station
                    presence_details = 'On foot at ' + entry["Body"]
                elif entry['BodyType'] == "Planet": # If the player is on a planet surface
                    presence_details = 'On foot on ' + entry["Body"]
        else: # If player is not on foot
            if entry['Docked'] == True: # If ship is docked
                    presence_details = 'Docked at ' + entry["StationName"]
            elif entry['Docked'] == False: # If ship is not docked
                if entry['Taxi'] == True: # If player is in a taxi
                    if state['Dropship'] == True: # If Frontline Solutions
                        presence_details = 'Taking a dropship back to ' + taxiDestination
                    else: # If Apex Interstellar
                        if taxiDestination != "": # If taxi destination is stored
                            presence_details = 'Taking a taxi to ' + taxiDestination
                        else:
                            presence_details = 'Taking a taxi'
                elif entry['BodyType'] == "Planet": # If ship is on a planet but not docked
                    presence_details = 'On ' + entry["Body"]
                else: # If ship is not docked or on a planet
                    presence_details = 'Flying in normal space'
        presence_state = 'In ' + entry['StarSystem']
    
    elif entry['event'] == 'Embark': # Getting into ship or SRV
        if entry['Taxi'] == True and state['Dropship'] != True: # If Apex Interstellar
            if taxiDestination != "": # If there is a destination stored
                presence_details = 'Taking a taxi to ' + taxiDestination
            else:
                presence_details = 'Taking a taxi'
        elif state['Dropship'] == True: # If Frontline Solutions
            if czLocation != "": # If there is a combat zone location stored
                presence_details = 'Taking a dropship to ' + czLocation
            else:
                presence_details = 'Taking a dropship'
        elif entry['OnStation'] == True: # If ship is at a station but not a taxi or dropship
            presence_details = 'Docked at ' + entry['StationName']
        elif entry['SRV'] == True: # If entering SRV
            if srvName != "": # If SRV name is stored
                presence_details = 'Driving ' + srvName + ' On ' + entry['Body']
            else:
                presence_details = 'Driving SRV On ' + entry['Body'] 
        elif entry['OnPlanet'] == True: #If on a planet
            if station is not None: # If EDMC detects the station
                presence_details = 'Docked at ' + station
            elif stationGuess != "": # If station name was stored
                presence_details = 'Docked at ' + stationGuess
            else: # If station name is unknown or not at a station/settlement
                presence_details = 'On ' + entry['Body']
        presence_state = 'In ' + entry['StarSystem']
                
    elif entry['event'] == 'Disembark': # Getting out of ship or SRV
        if station is not None: # If EDMC detects the station
            presence_details = 'On foot at ' + station
        elif stationGuess != "": # If station name was stored
            presence_details = 'On foot at ' + stationGuess
        elif entry['OnStation'] == True: # If event entry has a station
            presence_details = 'On foot at ' + entry['StationName']
        elif entry['OnPlanet'] == True: # If on a planet, but not at a station/settlement
            presence_details = 'On foot on ' + entry['Body']
            bodyName = entry['Body'] # Store body name
        presence_state = 'In ' + entry['StarSystem']
        taxiDestination = "" # Clear taxi destination in case player is exiting taxi
        
    elif entry['event'] == 'LaunchSRV': # Deploying SRV from ship
        if entry['PlayerControlled'] == True: # If this action was done by the player
            if bodyName != "": # If a body name was stored
                # Strip the first 4 charcaters from the SRV name so instead of "SRV Scarab" we get "Scarab"
                presence_details = 'Driving ' + entry['SRVType_Localised'][4:] + ' on ' + bodyName
            else:
                presence_details = 'Driving ' + entry['SRVType_Localised'][4:]
            srvName = entry['SRVType_Localised'][4:] # Store the SRV name
                
    elif entry['event'] == 'DockSRV': # Putting SRV back into ship
        if bodyName != "": # If body name was stored
            presence_details = 'On ' + bodyName
        else:
            presence_details = 'In ship on planet surface'
        srvName = "" # Clear SRV name
            
    elif entry['event'] == "Touchdown": # Landing on a planet
        if entry['PlayerControlled'] == True: # If player and not recalling ship
            presence_details = 'Landed On ' + entry['Body']
            presence_state = 'In ' + entry['StarSystem']
            bodyName = entry['Body']
        
    elif entry['event'] == "Liftoff": # Lifting off planet surface
        # If not a taxi and not dismissing ship
        if state['Taxi'] != True and entry['PlayerControlled'] == True:
            presence_details = 'Flying On ' + entry['Body']
            presence_state = 'In ' + entry['StarSystem']
 
    elif entry['event'] == "ApproachBody": # Entering orbital cruise
        # Presence Details are not updated here so "Taking a taxi" or "Taking a dropship" persists
        # Until the player reaches the destination. The system is updated to show progress towards destination.
        # The superCruise variable is checked so that the supercrusing status is not overwritten if the ship
        # is still supercruising.
        # If not a taxi or dropship and not supercruising
        if state['Taxi'] != True and state['Dropship'] != True and superCruise != "Y":
            presence_details = 'Flying On ' + entry['Body']
        presence_state = 'In ' + entry['StarSystem']  
        bodyName = entry['Body'] # Save body name to use for events while on planet
        
    elif entry['event'] == "LeaveBody": # Leaving orbital cruise
        # Presence Details are not updated here so "Taking a taxi" or "Taking a dropship" persists
        # Until the player reaches the destination. The system is updated to show progress towards destination.
        # The superCruise variable is checked so that the supercrusing status is not overwritten if the ship
        # is still supercruising.
        # If not a taxi or dropship and not supercruising
        if state['Taxi'] != True and state['Dropship'] != True and superCruise != "Y":
            presence_details = 'Flying in normal space'
        presence_state = 'In ' + entry['StarSystem']
        bodyName = "" # Clear body name because player is no longer on the planet
        
    elif entry['event'] == "Docked": # Docking at a station
        presence_details = 'Docked at ' + entry['StationName']
        presence_state = 'In ' + entry['StarSystem']
        # Store station name, solves issue with planetary station name not showing when boarding ship
        stationGuess = entry['StationName']
        
    elif entry['event'] == "Undocked": # Launching from station
        # Presence Details are not updated on undocking so "Taking a taxi" or "Taking a dropship" persists
        # Until the player reaches the destination. The system is updated to show progress towards destination.
        if entry['Taxi'] != True and state['Dropship'] != True: # If not a taxi or dropship
            # If planetary station
            if entry['StationType'] == "OnFootSettlement" or entry['StationType'] == "CraterOutpost" or entry['StationType'] == "CraterPort":
                if bodyName == "": # If body name is not stored
                    presence_details = 'Leaving ' + entry['StationName']
                else: # If body name was stored
                    presence_details = 'Flying on ' + bodyName
            else: # If space station
                presence_details = 'Flying in normal space'
        presence_state = 'In ' + system 
        stationGuess = "" # Clear station name since player is leaving station
        
    elif entry['event'] == 'StartJump': # Hyperspace jump or supercruise
        # Presence Details are not updated on jumping/supercruise so "Taking a taxi" or "Taking a dropship" persists
        # Until the player reaches the destination. The system is updated to show progress towards destination.
        if state['Taxi'] != True and state['Dropship'] != True: # If not taxi or dropship
            if entry['JumpType'] == 'Hyperspace': # If hyperspace jump
                presence_details = 'Jumping to ' + entry['StarSystem'] # This entry shows destination system
                presence_state = 'From ' + system
            elif entry['JumpType'] == 'Supercruise': # If supercruise
                presence_details = 'Preparing for supercruise'
                presence_state = 'In ' + system
                superCruise = "Y" # Update superCruise variable
            
    elif entry['event'] == 'SupercruiseEntry': # Entering supercruise
        # Presence Details are not updated on supercruise so "Taking a taxi" or "Taking a dropship" persists
        # Until the player reaches the destination. The system is updated to show progress towards destination.
        if state['Taxi'] != True and state['Dropship'] != True: # If not taxi or dropship
            presence_details = 'Supercruising'
        presence_state = "In " + entry['StarSystem']
        superCruise = "Y" # Update superCruise variable
        
    elif entry['event'] == 'SupercruiseExit': # Exiting supercruise
        # Presence Details are not updated on supercruise so "Taking a taxi" or "Taking a dropship" persists
        # Until the player reaches the destination. The system is updated to show progress towards destination.
        if state['Taxi'] != True and state['Dropship'] != True: # If not taxi or dropship
            if entry['BodyType'] == "Planet": # If ship is flying over planet surface / in orbital cruise
                presence_details = 'Flying On ' + entry['Body']
            else:
                presence_details = 'Flying in normal space'
        presence_state = 'In ' + entry['StarSystem']
        superCruise = "" # clear superCruise variable since player is no longer supercruising
        
    elif entry['event'] == 'FSDJump': # Supercruising
        # Presence Details are not updated on supercruise so "Taking a taxi" or "Taking a dropship" persists
        # Until the player reaches the destination. The system is updated to show progress towards destination.
        if state['Taxi'] != True and state['Dropship'] != True: # If not taxi or dropship
            presence_details = 'Supercruising'
        presence_state = 'In ' + entry['StarSystem']
        superCruise = "Y" # Update superCruise variable
    
    elif entry['event'] == 'BookDropship': # Dropship coming to pick player up
        if entry['Retreat'] == False: # Signing up for combat zone at Frontline Solutions desk
            czLocation = entry['DestinationLocation'] # Store combat zone location (Settlement)
        elif entry['Retreat'] == True: # End of ground combat zone if dropship was taken
            taxiDestination = entry['DestinationLocation'] # Store destination (Station name)

    elif entry['event'] == 'CancelDropship': # Canceling deployment at Frontline Solutions
        czLocation = "" # Clear combat zone location since deployment canceled
    
    elif entry['event'] == 'DropshipDeploy': # Exiting dropship
        if czLocation == "": # If combat zone location was stored
           presence_details = 'Combat zone on ' + entry['Body']
        else: # If combat zone location was not stored
            presence_details = 'Combat zone at ' + czLocation
        presence_state = 'In ' + system
        
    elif entry['event'] == 'BookTaxi': # Requesting transport from Apex Interstellar
        taxiDestination = entry['DestinationLocation'] # Store destination
    
    elif entry['event'] == 'CancelTaxi': # Canceling transport from Apex Interstellar
        taxiDestination = "" # Clear destination since transport is canceled
        
    elif entry['event'] == 'Shutdown': # Exiting game to desktop or main menu
        this.presence_state = _('Connecting CMDR Interface')
        this.presence_details = ''
        stationName = ""
        czLocation = ""
        superCruise = ""
        bodyName = ""
        taxiDestination = ""
              
    if presence_state != this.presence_state or presence_details != this.presence_details:
        this.presence_state = presence_state
        this.presence_details = presence_details
        update_presence()


def check_run(plugin_dir):
    plugin_path = join(dirname(plugin_dir), plugin_name)
    retry = True
    while retry:
        time.sleep(1 / 10)
        try:
            this.app = dsdk.Discord(CLIENT_ID, dsdk.CreateFlags.no_require_discord, plugin_path)
            retry = False
        except Exception:
            pass

    this.activity_manager = this.app.get_activity_manager()
    this.activity = dsdk.Activity()

    this.call_back_thread = threading.Thread(target=run_callbacks)
    this.call_back_thread.setDaemon(True)
    this.call_back_thread.start()
    this.presence_state = _('Connecting CMDR Interface')
    this.presence_details = ''
    this.time_start = time.time()

    this.disablePresence = None

    update_presence()


def run_callbacks():
    try:
        while True:
            time.sleep(1 / 10)
            this.app.run_callbacks()
    except Exception:
        check_run(this.plugin_dir)
