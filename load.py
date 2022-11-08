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

czLocation = ""
superCruise = ""
bodyName = ""
taxiDestination = ""
stationGuess = ""
srvName = ""

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
        if "OnFoot" in entry:
            if entry['OnFoot'] == True:
                if entry['BodyType'] == "Station":
                    presence_details = 'On foot at ' + entry["Body"]
                elif entry['BodyType'] == "Planet":
                    presence_details = 'On foot on ' + entry["Body"]
        else:
            if entry['Docked'] == True:
                    presence_details = 'Docked at ' + entry["StationName"]
            elif entry['Docked'] == False:
                if entry['Taxi'] == True:
                    if state['Dropship'] == True:
                        presence_details = 'Taking a dropship back to ' + taxiDestination
                    else:
                        if taxiDestination != "":
                            presence_details = 'Taking a taxi to ' + taxiDestination
                        else:
                            presence_details = 'Taking a taxi'
                elif entry['BodyType'] == "Planet":
                    presence_details = 'On ' + entry["Body"]
                else:
                    presence_details = 'Flying in normal space'
        presence_state = 'In ' + entry['StarSystem']

    elif entry['event'] == 'Embark':
        if entry['Taxi'] == True and state['Dropship'] != True:
            if taxiDestination != "":
                presence_details = 'Taking a taxi to ' + taxiDestination
            else:
                presence_details = 'Taking a taxi'
        elif state['Dropship'] == True:
            if czLocation != "":
                presence_details = 'Taking a dropship to ' + czLocation
            else:
                presence_details = 'Taking a dropship'
        elif entry['OnStation'] == True:
            presence_details = 'Docked at ' + entry['StationName']
        elif entry['SRV'] == True:
            if srvName != "":
                presence_details = 'Driving ' + srvName + ' On ' + entry['Body']
            else:
                presence_details = 'Driving SRV On ' + entry['Body'] 
        elif entry['OnPlanet'] == True:
            if station is not None:
                presence_details = 'Docked at ' + station
            elif stationGuess != "":
                presence_details = 'Docked at ' + stationGuess
            else:
                presence_details = 'On ' + entry['Body']
        presence_state = 'In ' + entry['StarSystem']
            
    elif entry['event'] == 'Disembark':
        if station is not None:
            presence_details = 'On foot at ' + station
        elif stationGuess != "":
            presence_details = 'On foot at ' + stationGuess
        elif entry['OnStation'] == True:
            presence_details = 'On foot at ' + entry['StationName']
        elif entry['OnPlanet'] == True:
            presence_details = 'On foot on ' + entry['Body']
            bodyName = entry['Body']
        presence_state = 'In ' + entry['StarSystem']
        taxiDestination = ""
        
    elif entry['event'] == 'LaunchSRV':
        if entry['PlayerControlled'] == True:
            if bodyName != "":
                presence_details = 'Driving ' + entry['SRVType_Localised'][4:] + ' on ' + bodyName
            else:
                presence_details = 'Driving ' + entry['SRVType_Localised'][4:]
            srvName = entry['SRVType_Localised'][4:]
                
    elif entry['event'] == 'DockSRV':
        if bodyName != "":
            presence_details = 'On ' + bodyName
        else:
            presence_details = 'In ship on planet surface'
        srvName = ""
            
    elif entry['event'] == "Touchdown":
        if entry['PlayerControlled'] == True:
            presence_details = 'Landed On ' + entry['Body']
            presence_state = 'In ' + entry['StarSystem']
            bodyName = entry['Body']
        
    elif entry['event'] == "Liftoff":
        if state['Taxi'] != True and entry['PlayerControlled'] == True:
            presence_details = 'Flying On ' + entry['Body']
            presence_state = 'In ' + entry['StarSystem']
 
    elif entry['event'] == "ApproachBody":
        if state['Taxi'] != True and state['Dropship'] != True and superCruise != "Y":
            presence_details = 'Flying On ' + entry['Body']
        presence_state = 'In ' + entry['StarSystem']  
        bodyName = entry['Body']
        
    elif entry['event'] == "LeaveBody":
        if state['Taxi'] != True and state['Dropship'] != True and superCruise != "Y":
            presence_details = 'Flying in normal space'
        presence_state = 'In ' + entry['StarSystem']
        bodyName = ""
        
    elif entry['event'] == "Docked":
        presence_details = 'Docked at ' + entry['StationName']
        presence_state = 'In ' + entry['StarSystem']
        stationGuess = entry['StationName']
        
    elif entry['event'] == "Undocked":
        if entry['Taxi'] != True and state['Dropship'] != True:
            if entry['StationType'] == "OnFootSettlement" or entry['StationType'] == "CraterOutpost":
                if bodyName == "":
                    presence_details = 'Leaving ' + entry['StationName']
                else:
                    presence_details = 'Flying on ' + bodyName
            else:
                presence_details = 'Flying in normal space'
        presence_state = 'In ' + system 
        stationGuess = ""
        
    elif entry['event'] == 'StartJump':
        if state['Taxi'] != True and state['Dropship'] != True:
            if entry['JumpType'] == 'Hyperspace':
                presence_details = 'Jumping to ' + entry['StarSystem']
                presence_state = 'From ' + system
            elif entry['JumpType'] == 'Supercruise':
                presence_details = 'Preparing for supercruise'
                presence_state = 'In ' + system
                superCruise = "Y"
            
    elif entry['event'] == 'SupercruiseEntry':
        if state['Taxi'] != True and state['Dropship'] != True:
            presence_details = 'Supercruising'
        presence_state = "In " + entry['StarSystem']
        superCruise = "Y"
        
    elif entry['event'] == 'SupercruiseExit':
        if state['Taxi'] != True and state['Dropship'] != True:
            if entry['BodyType'] == "Planet":
                presence_details = 'Flying On ' + entry['Body']
            else:
                presence_details = 'Flying in normal space'
        presence_state = 'In ' + entry['StarSystem']
        superCruise = ""
        
    elif entry['event'] == 'FSDJump':
        if state['Taxi'] != True and state['Dropship'] != True:
            presence_details = 'Supercruising'
        presence_state = 'In ' + entry['StarSystem']
        superCruise = "Y"
    
    elif entry['event'] == 'BookDropship':
        if entry['Retreat'] == False:
            czLocation = entry['DestinationLocation']
        elif entry['Retreat'] == True:
            taxiDestination = entry['DestinationLocation']

    elif entry['event'] == 'CancelDropship':
        czLocation = ""
    
    elif entry['event'] == 'DropshipDeploy':
        if czLocation == "":
           presence_details = 'Combat zone on ' + entry['Body']
        else:
            presence_details = 'Combat zone at ' + czLocation
        presence_state = 'In ' + system
        
    elif entry['event'] == 'BookTaxi':
        taxiDestination = entry['DestinationLocation']
    
    elif entry['event'] == 'CancelTaxi':
        taxiDestination = ""
        
    elif entry['event'] == 'Shutdown':
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
