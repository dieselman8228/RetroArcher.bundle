#imports
import argparse
import hashlib
import json
import logging
import os
import random
import re
import shutil
import socket
import sys
import time
import uuid

from multiprocessing.pool import ThreadPool as Pool
from datetime import datetime


def config_to_dict(configFile):
    def splitter(line):
        return line.split('=', 1)

    with open(configFile, 'r') as f:
        text = f.read().rstrip('\n')
        header, *data_lines = text.split('\n')

    data = dict(map(splitter, data_lines))
    
    return header, data


def config_rewrite(configFile, header, data):
    with open(configFile, 'w') as f:
        data_lines = list(map('='.join, data.items()))
        text = '\n'.join([header] + data_lines)
        f.write(text)


def convertXMLtoJSON(filepath):
    inputFile = open (filepath, 'rb')
    j = xmltodict.parse(inputFile)
    return j


def get_ip(): #https://stackoverflow.com/a/28950776/11214013
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def getJson_fromXML(url):
    headers = {
            'Accept': 'application/xml'
        }
    
    xml = requests.get(url=url, headers=headers).text
    
    result = xmltodict.parse(xml)
    
    return result


def getPlex():
    from plexapi.server import PlexServer, CONFIG #this was used to get the settings previously... there could be other uses in the future
    PLEX_URL = Prefs['url_PlexServer']
    PLEX_TOKEN = Prefs['str_PlexToken']


    # ## CODE BELOW ## ... could use the CONFIG option from PlexAPI if user knows what they are doing
    if not PLEX_URL:
        PLEX_URL = CONFIG.data['auth'].get('server_baseurl')
    if not PLEX_TOKEN:
        PLEX_TOKEN = CONFIG.data['auth'].get('server_token')

    sess = requests.Session()
    # Ignore verifying the SSL certificate
    sess.verify = False  # '/path/to/certfile'
    # If verify is set to a path to a directory,
    # the directory must have been processed using the c_rehash utility supplied
    # with OpenSSL.
    if sess.verify is False:
        # Disable the warning that the request is insecure, we know that...
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    #create the plexapi server
    plex = PlexServer(PLEX_URL, PLEX_TOKEN, session=sess)
    account = plex.myPlexAccount()
    
    return plex, account


def getPaths():
    #build_directories
    paths = {}
    script = os.path.realpath(__file__) #get current script directory
    
    paths_to_get = {
                0: 'script',
                1: 'scriptDir',
                2: 'codeDir',
                3: 'contentsDir',
                4: 'pluginDir',
                5: 'pluginsDir',
                6: 'plexDir',
                7: 'appDir'
                }
    for key in paths_to_get:
        if key == 0:
            paths['script'] = script
        else:
            path = os.path.dirname(paths[paths_to_get[key-1]])
            paths[paths_to_get[key]] = path
    
    paths['agentModulesDir'] = os.path.join(paths['contentsDir'], 'Libraries', 'Shared')
    paths['retroarcherModulesDir'] = os.path.join(paths['contentsDir'], 'Libraries', 'Modules')
    paths['retroarcherStartVideosDir'] = os.path.join(paths['contentsDir'], 'Resources', 'StartVideos')
    paths['retroarcherFontDir'] = os.path.join(paths['contentsDir'], 'Resources', 'Fonts')
    paths['retroarcherFFMPEGDir'] = os.path.join(paths['contentsDir'], 'Resources', 'ffmpeg')
    
    logging.debug('Paths: %s' % (paths))
    return paths


def getPluginDir():
    def pluginsDir(plex): #alternate methods to get directory... not needed as long as this script doesn't get moved
        if sys.platform == 'win32':
            #settings = plex.settings.all()
            appdata = plex.settings.LocalAppDataPath
            logging.debug('appdata: %s' % (appdata))
            pluginsDir = os.path.join(appdata, 'Plex Media Server', 'Plug-ins')
            
        else:
            logDir = str(uuid.uuid4())

            logs = plex.downloadLogs(savepath=logDir, unpack=True) #https://discord.com/channels/183396325142822912/283629564087762945/795820408766988308
            logging.debug('logs: %s' % (logs))

            os.rename(os.path.join(logDir, 'Plex Media Server.log'), os.path.join(logDir, 'Plex Media Server.0.log'))

            x = 0
            y = 0
            for root, dir, files in os.walk(logDir): #https://stackoverflow.com/a/35703223
                for f in files:

                    i = os.path.join(logDir, f)

                    if f.startswith('Plex Media Server.'):
                        if x < 6 and y < 2:
                            logging.debug('f: %s' % (f))
                            
                            inputFile = open (i, 'rb')
                            data = inputFile.readlines()
                            inputFile.close()
                            
                            #for line in data: #https://thispointer.com/5-different-ways-to-read-a-file-line-by-line-in-python/
                            for line in data: #https://thispointer.com/5-different-ways-to-read-a-file-line-by-line-in-python/
                                if 'Scanning for plug-ins in' in line.decode('UTF-8'):
                                    pluginsDir = os.path.abspath(line.decode('UTF-8').split('"')[-2])
                                    y += 1
                            x += 1
                    os.remove(i)
            os.rmdir(logDir)

        logging.debug('pluginDir: %s' % (pluginsDir))
        return(pluginsDir)


def getSettings(directory, agent):
    settingsFile = os.path.join(directory, 'Plug-in Support', 'Preferences', agent + str('.xml'))
    return settingsFile


def getDataFolders(directory, agent):
    dataFolders = {}
    dataFolders['dataFolder'] = os.path.join(directory, 'Plug-in Support', 'Data', agent)
    dataFolders['mediaFolder'] = os.path.join(directory, 'Plug-in Support', 'Data', agent, 'media')
    dataFolders['dbFolder'] = os.path.join(directory, 'Plug-in Support', 'Data', agent, 'database')
    return dataFolders


def launcher(clientIP, clientPlatform, clientDevice, clientProduct, clientPlayer, clientUser, clientUserId, movieName, dataFolders):
    if Prefs['str_MoonlightPcUuid'] == '' or Prefs['str_MoonlightPcUuid'] == None:
        serverInfo = getJson_fromXML(Prefs['url_GameStreamServerAddress'])
        logging.debug('serverInfo: %s' % (json.dumps(serverInfo, indent=4)))
        moonlightPcUuid = serverInfo['root']['uniqueid']
    else:
        moonlightPcUuid = Prefs['str_MoonlightPcUuid']
    logging.info('moonlightPcUuid: %s' % (moonlightPcUuid))
    
    moonlightAppName = Prefs['str_MoonlightAppName']

    if Prefs['str_MoonlightAppId'] == '' or Prefs['str_MoonlightAppId'] == None:
        logging.info('GameStreamHost: %s' % (Prefs['enum_GameStreamHost']))
        if Prefs['enum_GameStreamHost'] == 'GeForce Experience':
            nvstreamsvc_path = os.path.join(os.path.expandvars('$programdata'), 'NVIDIA Corporation', 'nvstreamsvc')
            
            nvsstreamsvrLogs = ['nvstreamsvcCurrent.log', 'nvstreamsvcOld.log']
            
            appIdFound = False
            for log in nvsstreamsvrLogs:
                if appIdFound == False:
                    NVlogFile = os.path.join(nvstreamsvc_path, log)
                    if os.path.isfile(NVlogFile):
                        with open(NVlogFile, 'r') as f:
                            logContents = f.read()
                        #find titles
                        titleSplit = logContents.split('Title=')
                        titleCounter = 0
                        
                        while titleCounter < len(titleSplit):
                            if titleSplit[titleCounter].splitlines()[0].lower() == moonlightAppName.lower():
                                moonlightAppId = titleSplit[titleCounter].split('AppId=', 1)[-1].splitlines()[0]
                                appIdFound = True
                                break
                            titleCounter += 1
            
        else:
            moonlightAppId = '1'

    else:
        moonlightAppId = Prefs['str_MoonlightAppId']
    logging.info('moonlightAppId: %s' % (moonlightAppId))
    
    #convert movieName to romName
    game_name_full = os.path.basename(movieName) #the file name
    system = platformPath(movieName)
    
    #key = os.path.join(system, game_name_full)
    videoKey = game_name_full
    logging.info('videoKey: %s' % (videoKey))
    
    jsonDir = dataFolders['dbFolder']
    jsonFile = os.path.join(jsonDir, 'database.json')
    with open(jsonFile) as f:
        database = json.load(f)
    
    secretsFile = os.path.join(jsonDir, 'secrets.json')
    try:
        with open(secretsFile) as f:
            secrets = json.load(f)
    except FileNotFoundError:
        pass
    
    romFolder = database['romMapping']['platforms'][system]['videos'][videoKey]['romFolder']
    romFile = database['romMapping']['platforms'][system]['videos'][videoKey]['romFile']
    
    romName = os.path.join(romFolder, romFile)
    
    logging.info('romName: %s' % (romName))
    
    systemKey = system.lower().replace(' ', '_')

    emulator = archer_dict.dPlatformMapping[system]['emulators'][Prefs['emulator_' + systemKey]]
    logging.debug('emulator: %s' % (emulator))
    
    applicationDirectory = Prefs['dir_app_' + emulator]
    binaryCommand = Prefs['str_binary_' + emulator]
    
    if emulator == 'retroarch':
        core = archer_dict.dPlatformMapping[system]['emulators'][emulator]['cores'][Prefs['core_' + systemKey]]
        logging.info('core: %s' % (core))
        emulatorCore = os.path.join('cores', core)
        logging.info('emulatorCore: %s' % (emulatorCore))
    else:
        emulatorCore = ''
    
    fullRomPath = os.path.join(SourceRomDir, romName)
    logging.info('fullRomPath: %s' % (fullRomPath))
    
    logging.info('clientPlatform: %s' % (clientPlatform))

    launch = False
    if clientPlatform.lower() == 'android':
        launch = launchADB(clientIP, moonlightPcUuid, moonlightAppId)
    elif clientProduct.lower() == 'plex for windows' and clientPlatform.lower() == 'windows':
        launch = launchWindows(clientIP, moonlightPcUuid, moonlightAppName, clientUser, secrets)
    elif clientProduct.lower() == 'plex web' and clientDevice.lower() == 'windows':
        launch = launchWindows(clientIP, moonlightPcUuid, moonlightAppName, clientUser, secrets)
    elif clientPlatform.lower() == 'kodi': #disable for now
        launch = False
    elif clientPlatform.lower() == 'ios': #disable for now
        launch = False
    else:
        launch = False
    
    if launch == True:
        UserId_rpcs3 = clientUserId
        UserId_cemu = UserId_rpcs3
        UserId_length = len(UserId_rpcs3)
        try:
            int(clientUserId)
            while UserId_length != 8:
                if UserId_length < 8:
                    UserId_rpcs3 = '0%s' % (UserId_rpcs3)
                else:
                    UserId_rpcs3 = UserId_rpcs3[1:]
                UserId_cemu = str(int(UserId_rpcs3) + 80000000)
                UserId_length = len(UserId_rpcs3)
        except:
            logging.error('User ID is not an integer: %s' % (clientUserId))

        dSystemPlatformMapping = {
        'win64' : {
            'emulators' : {
                'cemu' : {
                    'dir' : applicationDirectory,
                    'command' : 'start "RetroArcher" "%s" --fullscreen --game "%s" --account %s' % (binaryCommand, fullRomPath, UserId_cemu)
                    },
                'retroarch' : {
                    'dir' : applicationDirectory,
                    'command' : 'start "RetroArcher" "%s" -L "%s" "%s"' % (binaryCommand, emulatorCore, fullRomPath)
                    },
                'rpcs3' : {
                    'dir' : applicationDirectory,
                    'command' : 'start "RetroArcher" "%s" --no-gui "%s" --user-id %s' % (binaryCommand, fullRomPath, UserId_rpcs3)
                    }
                },
            'stream_host' : {
                'GeForce Experience' : {
                    'process' : 'nvstreamer.exe',
                    },
                'OpenStream' : {
                    'process' : 'openstream.exe'
                    },
                'Sunshine' : {
                    'process' : 'sunshine.exe'
                    }
                },
            'kill_command' : 'taskkill /F /IM'
            },
        'win32' : {
            'emulators' : {
                'cemu' : {
                    'dir' : applicationDirectory,
                    'command' : 'start "RetroArcher" "%s" --fullscreen --game "%s" --account %s' % (binaryCommand, fullRomPath, UserId_cemu)
                    },
                'retroarch' : {
                    'dir' : applicationDirectory,
                    'command' : 'start "RetroArcher" "%s" -L "%s" "%s"' % (binaryCommand, emulatorCore, fullRomPath)
                    },
                'rpcs3' : {
                    'dir' : applicationDirectory,
                    'command' : 'start "RetroArcher" "%s" --no-gui "%s" --user-id %s' % (binaryCommand, fullRomPath, UserId_rpcs3)
                    }
                },
            'stream_host' : {
                'GeForce Experience' : {
                    'process' : 'nvstreamer.exe',
                    },
                'Open-Stream' : {
                    'process' : 'openstream.exe'
                    },
                'Sunshine' : {
                    'process' : 'sunshine.exe'
                    }
                },
            'kill_command' : 'taskkill /f /im'
            }
        #'linux' : 'tbd',
        #'macOS' : 'tbd'
        }
        
        if sys.platform == 'win32': #if windows determine if 32 bit or 64 bit
            import struct
            architecture = struct.calcsize("P")*8 #https://stackoverflow.com/a/1406849
            if architecture == 64:
                platform = 'win64'
            elif architecture ==32:
                platform = 'win32'
        logging.info('architecture: %s' % (architecture))
        logging.info('platform: %s' % (platform))
        
        emulatorPath = dSystemPlatformMapping[platform]['emulators'][emulator]['dir']
        logging.info('emulatorPath: %s' % (emulatorPath))
        os.chdir(emulatorPath)
        
        #verify/create user profile folder and file for cemu
        if emulator == 'cemu':
            userProfilePath_cemu = os.path.join(emulatorPath, 'mlc01', 'usr', 'save', 'system', 'act', UserId_cemu)
            userProfileFile_cemu = os.path.join(userProfilePath_cemu, 'account.dat')
            
            userProfilePathExists_cemu = os.path.isdir(userProfilePath_cemu)
            userProfileFileExists_cemu = os.path.isfile(userProfileFile_cemu)
            
            if userProfilePathExists_cemu == False or userProfileFileExists_cemu == False: #we need to create the user profile
                default_cemu_account_file = os.path.join(emulatorPath, 'mlc01', 'usr', 'save', 'system', 'act', '80000001', 'account.dat')
                if os.path.isfile(default_cemu_account_file) == True:
                    make_dir(userProfilePath_cemu)
                    copy_file(default_cemu_account_file, userProfileFile_cemu)
                userProfileFileExists_cemu = os.path.isfile(userProfileFile_cemu)
                if userProfileFileExists_cemu == True:
                    #need to parse and replace some stuff in the file
                    header, data = config_to_dict(userProfileFile_cemu)
                    
                    data['PersistentId'] = UserId_cemu
                    data['Uuid'] = str(uuid.uuid1()).replace('-', '')
                    data['TransferableIdBase'] = '2000004%s' % (data['Uuid'][-8:])
                    
                    config_rewrite(userProfileFile_cemu, header, data)
                else:
                    logging.critial('Failed to create cemu user profile. Exiting.')
                    sys.exit()
        
        command = dSystemPlatformMapping[platform]['emulators'][emulator]['command']
        logging.debug('command: %s' % (command))
        os.system(command)
        
        #kill the stream once the emulator is killed
        '''
        #this is trying to kill streamer process before it's even started... we need to run after retroarch.exe exits
        process = dSystemPlatformMapping[platform]['stream_host'][gamestreamhost]['process']
        print(process)
        command = '%s %s' % (dSystemPlatformMapping[platform]['kill_command'], process)
        print(command)
        print(os.system(command))
        '''
        
        '''
        import psutil
        for proc in psutil.process_iter():
            if proc.name == process:
                p = psutil.Process(proc.pid)
                proc.kill()
        '''


def launchADB(clientIP, moonlightPcUuid, moonlightAppId):
    #https://stackoverflow.com/a/37327094/11214013
    
    global scannerIP
    scannerIP = clientIP
    
    adbRanges = [ [5555, 5585], [30000 , 50000] ] #https://www.reddit.com/r/tasker/comments/jbzeg5/adb_wifi_and_android_11_wireless_debugging/
    for adbRange in adbRanges:
        adbThreadedScan(adbRange)
        logging.info('adbPortsFound: %s' % (adbPortsFound))
        adbAddress = adbConnect(clientIP, adbPortsFound)
        logging.info('adbAddress: %s' % (adbAddress))
        if adbAddress != None:
            device = adb.device(serial=adbAddress)
            break

    #possible apps that can be useful
    packages = {
            'Moonlight': {
                'package' : 'com.limelight'
                }
            }

    for key in packages:
        if device.shell('pm list packages | grep ' + packages[key]['package']) != '':
            packages[key]['installed'] = True
            logging.info('%s is installed on client device: %s' % (key, packages[key]['package']))
        else:
            packages[key]['installed'] = False
            logging.info('%s is NOT installed on client device: %s' % (key, packages[key]['package']))
            #try:
            #    if packages[key][1] != '':
            #        installAPK(packages[key]['download'])
            #except:
            #    pass
            #maybe we want to auto install some apks?
    
    #add -W for more silent starting https://developer.android.com/studio/command-line/adb
    #why did -W stop working after a server reboot?
    if packages[Prefs['enum_GameStreamApp']]['installed'] == True:
        device.shell('am start -W -n com.limelight/com.limelight.ShortcutTrampoline --es "UUID" "' + moonlightPcUuid + '" --es "AppId" "' + str(moonlightAppId) + '"') #open moonlight on client device streaming to server desktop
        return True
    else:
        return False


def adbConnect(clientIP, adbPortsFound):
    for adbPort in adbPortsFound:
        adbAddress = clientIP + ':' + str(adbPort)
        adbConnectOutput = adb.connect(adbAddress)
        logging.debug('adbConnectOutput: %s' % (adbConnectOutput))
        message = adbConnectOutput.split(clientIP + ':' + str(adbPort), 1)[0].strip()
        if message == 'cannot connect to':
            logging.debug('adb connection unsuccessful, trying next port if available')
        elif message == 'failed to connect to':
            logging.debug('adb connection failed, device is probably not paired... Android 11+ ???, trying next available port anyway')
        elif message == 'connected to' or message == 'already connected to':
            logging.info('adb connected on port: %s' % (adbPort))
            return adbAddress
        else:
            logging.debug('unknown connection status, trying next available port')


def adbThreadedScan(adbRange):
    from threading import Thread
    from queue import Queue
    
    # number of threads, feel free to tune this parameter as you wish
    rangeThreads = adbRange[-1] - adbRange[0]
    logging.info('rangeThreads: %s' % (rangeThreads))
    prefThreads = Prefs['int_PortScanThreads']
    logging.info('prefThreads: %s' % (prefThreads))
    if rangeThreads < prefThreads:
        N_THREADS = rangeThreads
    else:
        N_THREADS = prefThreads
    # thread queue
    global q
    q = Queue()
    
    global adbPortsFound
    adbPortsFound = []
    for t in range(N_THREADS):
        try:
            #for each thread, start it
            t = Thread(target=port_scan_thread)
            #when we set daemon to true, that thread will end when the main thread ends
            t.daemon = True
            #start the daemon thread
            t.start()
        except RuntimeError as e:
            logging.error(e)
            break

    for port in range(adbRange[0], adbRange[-1]):
        if (port % 2) != 0: #if port is an odd number
            #for each port, put that port into the queue
            #to start scanning
            q.put(port)
            
            #if port_scan(clientIP, port):
            #    print('port is open: ' + str(port))
            #    adbPortsFound.append(port)
    q.join() #wait for all ports to finish being scanned


def port_scan(host, port): #determine whether `host` has the `port` open
    try:
        # creates a new socket
        s = socket.socket()
        # tries to connect to host using that port
        s.connect((host, port))
        # make timeout if you want it a little faster ( less accuracy )
        # s.settimeout(0.2)
    except:
        # cannot connect, port is closed
        # return false
        pass
    else:
        # the connection was established, port is open!
        #return True
        adbPortsFound.append(port)
    finally:
        s.close()


def port_scan_thread():
    while True:
        # get the port number from the queue
        port = q.get()
        # scan that port number
        port_scan(scannerIP, port)
        # tells the queue that the scanning for that port 
        # is done
        q.task_done()


def launchWindows(clientIP, moonlightPcUuid, moonlightAppName, clientUser, secrets):
    u = secrets[clientUser]['win']['u']
    p = secrets[clientUser]['win']['p']
    
    batFile = os.path.join(paths['contentsDir'], 'bin', 'Moonlight-qt', 'win', 'launcher.bat')
    command = '"%s" %s %s %s %s %s' % (batFile, clientIP, moonlightPcUuid, moonlightAppName, u, p)
    os.system(command)
    
    #schtasks /create /TN "\RetroArcher launcher" /s "192.168.1.13" /sc onlogon /tr "C:\Program Files\Moonlight Game Streaming\Moonlight.exe stream Archer RetroArcher" /f /u "" /p ""
    
    #schtasks /run /TN "\RetroArcher launcher" /s "192.168.1.13" /u "" /p ""
    
    #schtasks /delete /TN "\RetroArcher launcher" /s "192.168.1.13" /u "" /p "" /f
    
    #create = 'schtasks /create /TN "\\RetroArcher launcher" /s "%s" /sc onlogon /tr "C:\\Program Files\\Moonlight Game Streaming\\Moonlight.exe stream %s %s" /f /u "%s" /p "%s"' % (clientIP, moonlightPcUuid, moonlightAppName, u, p)
    #print(create)
    #os.system(create)
    
    #run = 'schtasks /run /TN "\\RetroArcher launcher" /s "%s" /u "%s" /p "%s"' % (clientIP, u, p)
    #print(run)
    #os.system(run)
    
    #delete = 'schtasks /delete /TN "\\RetroArcher launcher" /s "%s" /u "%s" /p "%s" /f' % (clientIP, u, p)
    #print(delete)
    #os.system(delete)
    
    return True


def list_hash(fileList):
    logging.debug('fileList: %s' % (fileList))

    bufferSize = Prefs['int_BufferSize']
    
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    
    md5List = []
    sha1List = []
    
    for x in fileList:
        with open(x, 'rb') as f:
            while True:
                data = f.read(bufferSize)
                if not data:
                    break
                md5.update(data)
                sha1.update(data)
        md5List.append(md5.hexdigest())
        sha1List.append(sha1.hexdigest())
    
    return sorted(md5List), sorted(sha1List)


def list_videos(directory):
    videoExtensions = ['.mp4', '.mkv']
    list = []
    if os.path.exists(directory):
        for file in os.listdir(directory):
            for extension in videoExtensions:
                if file.endswith(extension):
                    list.append(os.path.join(directory, file))
    return list


def lockServer():
    if sys.platform == 'win32':
        os.system('rundll32.exe user32.dll,LockWorkStation')    


def make_dir(directory):
    try:
        os.mkdir(directory, mode=0o777)
    except:
        pass


def copy_file(src, dst):
    try:
        shutil.copy2(src, dst)
    except:
        pass


def make_link(src, dst, system, romName):
    if sys.platform == 'win32':
        ffmpegPath = 'ffmpeg\\ffmpeg'
    else:
        ffmpegPath = 'ffmpeg'
    logging.debug('ffmpegPath: %s' % (ffmpegPath))
    
    fontFolder = paths['retroarcherFontDir']
    fontFile = os.path.join(fontFolder, 'OpenSans', 'OpenSans-Light.ttf').replace('\\', '\\\\')
    
    illegal_characters = [',']
    
    title = romName
    time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    
    if os.path.isfile(dst) == True:
        os.remove(dst) #remove destination if it exists already
    for x in illegal_characters:
        romName = romName.replace(x, '\%s' % (x))
    
    command = "%s -ss 0 -i \"%s\" -t %s -vf \"drawtext=text='%s': fontfile='fonts/%s': fontcolor=%s: fontsize=%s: box=%s: boxcolor=%s: boxborderw=%s: x=%s: y=%s\" -codec:v %s -codec:a copy -map_metadata -1 -metadata title=\"%s\" -metadata creation_time=%s -map_chapters -1 \"%s\"" % (ffmpegPath, src, str(Prefs['int_FfmpegLength']), romName, fontFile, Prefs['str_FfmpegTextColor'], str(Prefs['int_FfmpegTextSize']), border, Prefs['str_FfmpegTextBoxColor'], Prefs['str_FfmpegTextBoxBorder'], Prefs['str_FfmpegTextX'], Prefs['str_FfmpegTextY'], Prefs['enum_FfmpegEncoder'], title, time, dst)
    logging.debug('command: %s' % (command))
    os.system(command)
    
    #os.symlink(src[0], dst) #symlinks not picked up by Plex :( ... hence the workaround with ffmpeg
    '''
    try:
        os.link(src, dst) #Plex sucks with hardlinks all pointing to the same file :(
    except FileExistsError:
        print('FileExistsError')
        os.remove(dst)
        make_link(src, dst)
    except OSError as e:
        print('OSError' + str(e))
        if str(e).startswith('[WinError 1142] An attempt was made to create more links on a file than the file system supports:'):
            print(src)
            os.remove(src)
            #fix src[1] if we end up making hardlinks again
            os.system('copy "' + src[1] +'" "' +src + '"') #we will not link to a new file (although with the same name) according to this https://unix.stackexchange.com/a/50188, explains why when we delete the original source the links still work
            make_link(src, dst)
    '''


def platformPath(fullpath):
    dirLength = len(splitall(fullpath))
    dirPath = os.path.dirname(fullpath)
    dirName = os.path.basename(dirPath)
    
    x =  0
    while x < dirLength:
        for key, value in archer_dict.dPlatformMapping.items():
            
            if dirName == key:
                x = dirLength
                game_platform = dirName
                break
        dirPath = os.path.dirname(dirPath)
        dirName = os.path.basename(dirPath)
        x += 1
    return game_platform


def scanner(paths, SourceRomDir, dataFolders):
    logging.info('paths: %s' % (paths))
    logging.info('SourceRomDir: %s' % (SourceRomDir))
    logging.info('dataFolders: %s' % (dataFolders))
    
    videoExtensions = ['.mp4', '.mkv']
    multi_disk_search = [ '(cd', '(disk', '(disc', '(part', '(pt', '(prt' ] #what else do we need in this list?
    SourceRomDirLength = len(splitall(SourceRomDir))
    
    startVideoDirectory = os.path.join(paths['retroarcherStartVideosDir']) #map to start video directory
    mainVideoDirectory = os.path.join(startVideoDirectory, 'Main') #map the main videos directory
    
    #compare these later
    mainVideoList = list_videos(mainVideoDirectory)
    logging.info('mainVideoList: %s' % (mainVideoList))
    mainMD5List, mainSHA1List = list_hash(mainVideoList)
    logging.info('mainMD5List: %s' % (mainMD5List))
    logging.info('mainSHA1List: %s' % (mainSHA1List))
    
    '''set these as global'''
    global border
    
    if Prefs['bool_FfmpegTextBox'].lower() == 'true':
        border = str(1)
    else:
        border = str(0)
    
    #compare this to existing settings later
    ffmpegOverlay = {
        'videoLength' : str(Prefs['int_FfmpegLength']),
        'fontSize' : str(Prefs['int_FfmpegTextSize']),
        'fontColor' : Prefs['str_FfmpegTextColor'],
        'fontX' : Prefs['str_FfmpegTextX'],
        'fontY' : Prefs['str_FfmpegTextY'],
        'border' : border,
        'borderColor' : Prefs['str_FfmpegTextBoxColor'],
        'borderSize' : Prefs['str_FfmpegTextBoxBorder']
        }
    
    '''get the existing json file'''
    #create data folders
    jsonDir = dataFolders['dbFolder']
    mediaDir = dataFolders['mediaFolder']
    make_dir(jsonDir)
    make_dir(mediaDir)

    #try to read the existing jsonFile
    jsonFile = os.path.join(jsonDir, 'database.json')
    try:
        with open(jsonFile) as f:
            database = json.load(f)
        useExisting = True
    except:
        useExisting = False
    
    if useExisting == True:
        try:
            if ffmpegOverlay == database['ffmpegOverlay']:
                logging.info('ffmpegOverlay settings did not change')
                ffmpeg_changed = 0 #no changes
            else:
                database['ffmpegOverlay'] = ffmpegOverlay
                logging.info('ffmpegOverlay settings changed, re-encoding everything')
                ffmpeg_changed = 1 #settings changed, re-encode ALL
        except KeyError as e:
            logging.error('KeyError: %s' % (str(e)))
            logging.error('database corruption detected... database will be re-created')
            useExisting = False
        if mainMD5List == database['mainVideoHash']:
            logging.info('main videos are the same as before')
            mainVideos = 0 #don't use a new video
        else:
            database['mainVideoHash'] = mainMD5List
            logging.info('main videos have changed')
            mainVideos = 1 #possibly use a new video
    
    if useExisting == False: #do not make this an elif statement becuase we may set useExisting to be false in the above if statement!
        print('use existing is false... something wrong with the json file?')
        logging.info('cannot use existing database.json... maybe it does not exist yet... maybe it is corrupted...')
        database = {'ffmpegOverlay' : ffmpegOverlay }
        ffmpeg_changed = 1 #settings changed, re-encode ALL, not really but database is messed up, need to re-make everything.
        database['mainVideoHash'] = mainMD5List
        mainVideos = 1 #possibly use a new video
        database['romMapping'] = {}
        database['romMapping']['platforms'] = {}
    
    for root, directories, files in os.walk(SourceRomDir): #https://stackoverflow.com/a/35703223
        ffmpegPool = Pool(Prefs['int_FfmpegThreads'])
        for d in directories:
            if root == SourceRomDir:
                for key, value in archer_dict.dPlatformMapping.items(): #https://stackoverflow.com/a/51446563
                    #print(value)
                    #print(value['systemNames'])
                    
                    x = 0
                    while x < len(value['systemNames']):
                    
                        if d.lower() == value['systemNames'][x].lower():
                            x = len(value['systemNames'])
                            system = key
                            logging.info('system: %s' % (system))
                            
                            try:
                                getSystem = Prefs['scanner_' + system.replace(' ', '_').lower()].lower() #this is a string not bool... lowercase the system name, and the value
                                logging.info('getSystem for %s: %s' % (system, getSystem))
                            except KeyError:
                                getSystem = '' #In case user has folder that is not supported by RetroArcher yet
                                logging.info('System (%s) is not supported yet.' % (system))
                            
                            if getSystem == 'true':
                                #probably pre-mature until we know if a rom was found, but this should be faster... from here to next for loop
                                platformVideoDirectory = os.path.join(startVideoDirectory, 'Platforms', system)
                                
                                platformVideoList = list_videos(platformVideoDirectory)
                                platformMD5List, platformSHA1List = list_hash(platformVideoList)
                                
                                try:
                                    database['romMapping']['platforms'][system]
                                except KeyError:
                                    database['romMapping']['platforms'][system] = {}
                                try:
                                    database['romMapping']['platforms'][system]['platformVideoHash']
                                except KeyError:
                                    database['romMapping']['platforms'][system]['platformVideoHash'] = {}
                                if platformMD5List != database['romMapping']['platforms'][system]['platformVideoHash']:
                                    database['romMapping']['platforms'][system]['platformVideoHash'] = platformMD5List
                                    platformVideos = 1 #possibly use a new platform video
                                else:
                                    platformVideos = 0 #don't use a new platform video
                                #print(database)
                                
                                #rom extensions allowed
                                #print(value['romExtensions'])
                                #print(value['multiDisk'])
                                
                                checks = [value['romExtensions']]
                                if value['multiDisk'] == True:
                                    checks.append(['m3u'])
                                
                                libraryType = value['libraryType']
                                libPath = os.path.join(dataFolders['mediaFolder'], libraryType)
                                make_dir(libPath)
                                logging.info('libPath: %s' % (libPath))
                                dstPath = os.path.join(dataFolders['mediaFolder'], libraryType, system)
                                make_dir(dstPath)
                                logging.info('dstPath: %s' % (dstPath))
                                
                                multi_disk_game_list = {}
                                keys_to_delete = []
                                
                                for root1, directories1, files1 in os.walk(os.path.join(root, d)):
                                    relativePath = os.path.join(*splitall(root1)[SourceRomDirLength:]) #https://blog.finxter.com/python-join-list-as-path/#:~:text=path.join()%20method%20takes%20one%20or%20more%20path%20arguments,to%20unpack%20the%20list%20into%20the%20argument%20list.
                                    
                                    iteration = 0
                                    for check in checks:
                                        #if iteration == 1:
                                        #    print('starting m3u files now')
                                        #    time.sleep(2)
                                        #else:
                                        #    print('starting normal roms now')
                                        #    time.sleep(2)
                                        for f in files1:
                                            splitFile = f.rsplit('.',1)
                                            romExtension = splitFile[-1].lower()
                                            #print(romExtension)

                                            #custom system game naming conventions
                                            if system.lower() == 'sony playstation 3': #rpcs3... can't they just be normal and load an iso?
                                                ps3Path = os.path.join('ps3_game', 'usrdir')
                                                if ps3Path in root1.lower():
                                                    if f.lower() == 'eboot.bin':
                                                        gameFolder = os.path.split(os.path.join(*splitall(relativePath)[:-2]))[-1]
                                                        romName = gameFolder.rsplit(' ', 1)[0] #title id separates game name... no brackets?
                                                        #print(romName)
                                                        #print(f.lower())
                                                    else:
                                                        continue
                                                else:
                                                    continue
                                            elif system.lower() == 'nintendo wii u': #cemu... need to get the folder name
                                                y = 0
                                                while y < len(check):
                                                    if romExtension == check[y].lower() and romExtension == 'rpx':
                                                        gameFolder = os.path.split(os.path.join(*splitall(relativePath)[:-1]))[-1]
                                                        romName = gameFolder.rsplit(' [', 1)[0]
                                                        #print(romName)
                                                        #print(f.lower())
                                                        print(gameFolder)
                                                        print(romName)
                                                    elif romExtension == check[y].lower() and romExtension == 'wud':
                                                        gameFolder = os.path.split(os.path.join(*splitall(relativePath)))[-1]
                                                        romName = gameFolder.rsplit(' [', 1)[0]
                                                        print(gameFolder)
                                                        print(romName)
                                                    y += 1
                                            else:
                                                romName = splitFile[0]

                                            
                                            #figure out which video to use
                                            src = None
                                            isGame = False
                                            skipRom = False
                                            
                                            y = 0
                                            #while y < len(value['romExtensions']):
                                            while y < len(check):
                                                if romExtension == check[y].lower():
                                                    #print(system + ' true')
                                                    #need to adjust multi disk m3u generation
                                                    if any(mds in romName.lower() for mds in multi_disk_search): #https://stackoverflow.com/a/3389611
                                                        for mds in multi_disk_search:
                                                            if mds in romName.lower():
                                                                #print(mds)
                                                                break
                                                        
                                                        if value['multiDisk'] == True:
                                                            index0 = romName.lower().find(mds)
                                                            #print(index0)
                                                            temp = romName[index0:]
                                                            #print(romName)
                                                            #print(temp)
                                                            index1 = temp.lower().find(')')
                                                            #print(index1)
                                                            gameName = (romName[0:index0].rstrip() + ' ' + temp[index1+1:].strip()).strip() #probably adjust game name
                                                            logging.info('gameName: %s' % (gameName))
                                                                
                                                            try:
                                                                multi_disk_game_list[gameName]
                                                                multi_disk_game_list[gameName][len(multi_disk_game_list[gameName])] = f
                                                                logging.info('MultiDisk game already in list: %s' % (f))
                                                            except KeyError:
                                                                matched = 0
                                                                for title in multi_disk_game_list:
                                                                    logging.debug('MultiDisk game title: %s' % (title))
                                                                    splitExisting = title.split('(')
                                                                    splitGame = gameName.split('(')
                                                                    
                                                                    lengthExisting = len(splitExisting)
                                                                    lengthGame = len(splitGame)
                                                                    
                                                                    tempExisting = title.rsplit('(', 1)[0].strip()
                                                                    tempGame = gameName.rsplit('(', 1)[0].strip()
                                                                    
                                                                    if tempExisting == tempGame and lengthGame > 2:
                                                                        #print('these are the same?')
                                                                        keys_to_delete.append(title)
                                                                        #print(multi_disk_game_list[title])
                                                                        #print(tempExisting)
                                                                        #print(tempGame)
                                                                        gameName = tempGame
                                                                        multi_disk_game_list[gameName] = multi_disk_game_list[title]
                                                                        multi_disk_game_list[gameName][len(multi_disk_game_list[gameName])] = f
                                                                        matched = 1
                                                                        time.sleep(2)
                                                                        break
                                                                
                                                                if matched == 0:
                                                                    multi_disk_game_list[gameName] = { 0 : f }
                                                                    logging.info('MultiDisk game being added to the list: %s' % (f))
                                                                
                                                            skipRom = True
                                                        else:
                                                            isGame = True
                                                    else:
                                                        isGame = True
                                                    
                                                    if isGame == True and skipRom == False:
                                                        #try to find a game specific start video
                                                        for extension in videoExtensions:
                                                            tempFile = os.path.join(startVideoDirectory, 'Games', system, romName + extension)
                                                            if os.path.isfile(tempFile):
                                                                src = tempFile
                                                                videoType = 'game'
                                                                
                                                                videoHash, junk = list_hash([src])
                                                                #print(videoHash[0])
                                                                #print(database['romMapping']['platforms'][system]['videos'][romName + extension]['videoHash'])
                                                                try:
                                                                    if videoHash[0] == database['romMapping']['platforms'][system]['videos'][romName + extension]['videoHash']:
                                                                        logging.debug('videoHash is equal hash in database: %s' % (videoHash[0]))
                                                                        makeLink = False
                                                                    else:
                                                                        logging.debug('videoHash is not equal hash in database: %s' % (videoHash[0]))
                                                                        makeLink = True
                                                                except KeyError:
                                                                    makeLink = True
                                                                break
                                                        
                                                        #try to find a find a random platform start video, then try to find a random non platform start video
                                                        if src == None:
                                                            startVidDir = [ platformVideoDirectory, mainVideoDirectory ]
                                                            video_type = ['platform', 'main']
                                                            typeHashList = [platformMD5List, mainMD5List]
                                                            typeMakeNew = [platformVideos, mainVideos]
                                                            t = 0
                                                            for videoDir in startVidDir:
                                                                videoList = list_videos(videoDir)
                                                                if len(videoList) > 0:
                                                                    src = os.path.join(videoDir, random.choice(videoList))
                                                                    videoType = video_type[t]
                                                                    
                                                                    found = 0
                                                                    for extension in videoExtensions:
                                                                        if found == 0:
                                                                            try:
                                                                                oldHash = database['romMapping']['platforms'][system]['videos'][romName + extension]['videoHash']
                                                                                if typeMakeNew[t] == 1 and oldHash in typeHashList[t]:
                                                                                    makeLink = random.choice([True, False])
                                                                                else:
                                                                                    makeLink = False
                                                                            except KeyError:
                                                                                pass
                                                                            try:
                                                                                if videoType != database['romMapping']['platforms'][system]['videos'][romName + extension]['videoType']:
                                                                                    logging.info('video type has changed')
                                                                                    makeLink = True
                                                                                    found = 1
                                                                                else:
                                                                                    logging.info('video type has not changed')
                                                                                    found = 1
                                                                            except KeyError:
                                                                                logging.info('video type not found')
                                                                    
                                                                    if found == 0:
                                                                        makeLink = True
                                                                    
                                                                    if makeLink == True:
                                                                        videoHash, junk = list_hash([src])
                                                                    
                                                                    break
                                                                t += 1
                                                    
                                                    if ffmpeg_changed == 1:
                                                        makeLink = True
                                                    
                                                    if makeLink == True and skipRom == False:
                                                        destinationPath = os.path.join(libraryType, system, romName + '.' + src.rsplit('.', 1)[-1])
                                                        
                                                        videoKey = os.path.join(romName + '.' + src.rsplit('.', 1)[-1])
                                                        
                                                        try:
                                                            database['romMapping']['platforms'][system]['videos']
                                                        except KeyError:
                                                            database['romMapping']['platforms'][system]['videos'] = {}
                                                        try:
                                                            database['romMapping']['platforms'][system]['videos'][videoKey]
                                                        except KeyError:
                                                            database['romMapping']['platforms'][system]['videos'][videoKey] = {}
                                                        
                                                        database['romMapping']['platforms'][system]['videos'][videoKey]['romFolder'] = relativePath
                                                        database['romMapping']['platforms'][system]['videos'][videoKey]['romFile'] = f
                                                        database['romMapping']['platforms'][system]['videos'][videoKey]['videoType'] = videoType
                                                        database['romMapping']['platforms'][system]['videos'][videoKey]['videoHash'] = videoHash[0] #just a single item, so don't need whole list
                                                        
                                                        #print(database)
                                                        jsonFile = os.path.join(jsonDir, 'database.json')
                                                        with open(jsonFile, 'w') as f:
                                                            json.dump(database, f)
                                                        
                                                        dst = os.path.join(dataFolders['mediaFolder'], destinationPath)
                                                        #print(dst)
                                                        
                                                        make_link(src, dst, system, romName) #enable for testing
                                                        #ffmpegPool.apply_async(make_link, (src, dst, system, romName,)) #disable for testing
                                                    elif skipRom == True:
                                                        logging.info('Skipping MultiDisk game image: %s' % (f))
                                                    elif makeLink == False:
                                                        logging.info('No update needed for this rom: %s' % (f))
                                                y += 1
                                        if iteration == 0:
                                            #multi disk m3u maker AND ffmpeg generator (so we don't have to scan again).
                                            for keyX, valueX in multi_disk_game_list.items():
                                                make_m3u = 1
                                                
                                                romName = keyX
                                                
                                                for titles in keys_to_delete:
                                                    if titles == keyX:
                                                        make_m3u = 0
                                                        break
                                                
                                                if make_m3u == 1:
                                                    f = romName + '.m3u'
                                                    fileContents = ''
                                                    #print(romName)
                                                    m3uPath = os.path.join(root, d, f)
                                                    for keyY, valueY in valueX.items():
                                                        diskNumber = keyY
                                                        fileContents += valueY + '\n'
                                                        #print(diskNumber)
                                                    #print(fileContents)
                                                
                                                #write the m3u
                                                if fileContents != '':
                                                    with open(m3uPath, 'w', encoding='utf-8') as m3u: #https://stackoverflow.com/a/35086151/11214013
                                                        m3u.write(fileContents)
                                        
                                        iteration += 1
                                        
                            elif getSystem == 'false':
                                logging.info('Skipping disabled system: %s' % (system))
                            elif getSystem == '':
                                logging.info('Skipping system not found in agent settings: %s' % (system))
                            else:
                                logging.error('Skipping system for unknown reason: %s' % (system))
                        x +=1
    
        ffmpegPool.close()
        ffmpegPool.join()
    
    #print(database)
    
    #add some stuff here to remove video files that the rom doesn't exist anymore
    for key in database['romMapping']['platforms']:
        pass


def splitall(path): #https://www.oreilly.com/library/view/python-cookbook/0596001673/ch04s16.html
    allparts = []
    while 1:
        parts = os.path.split(path)
        if parts[0] == path:  # sentinel for absolute paths
            allparts.insert(0, parts[0])
            break
        elif parts[1] == path: # sentinel for relative paths
            allparts.insert(0, parts[1])
            break
        else:
            path = parts[0]
            allparts.insert(0, parts[1])
    return allparts


def quote_remover(string):
    if string.startswith('"') and string.endswith('"'):
        string = string[1:-1]
    elif string.startswith("'") and string.endswith("'"):
        string = string[1:-1]
    else:
        string = string
    return string


if __name__ == '__main__':
    logDir = os.path.join(os.path.expanduser('~'), 'RetroArcher')
    make_dir(logDir)
    logFile = os.path.join(logDir, 'retroarcher.log')

    logging.basicConfig(filename=logFile,level=logging.DEBUG,format='%(asctime)s :  %(levelname)s - %(message)s') #change the logging level after reading the settings

    logging.info('----retroarcher.py script started----')
    
    paths = getPaths() #get the paths
    logging.info('paths: %s' % (paths))
    
    #hack for cleaner folder structure and relative imports
    sys.path.append(paths['retroarcherModulesDir'])
    sys.path.append(paths['agentModulesDir'])
    sys.path.append(paths['codeDir'])
    
    #agent imports
    import archer_dict
    
    #module imports (user doesn't need to install)
    import requests
    import xmltodict
    
    #from module imports
    from adbutils import adb #https://github.com/openatx/adbutils

    #argparse
    parser = argparse.ArgumentParser(description="Script to stream desktop to Android using Moonlight and then launches emulator and rom on PC.", formatter_class=argparse.RawTextHelpFormatter)
    
    #arguments for launcher
    parser.add_argument('--launch', action='store_true', required=False, help='Launch the rom from Tautulli.')
    parser.add_argument('--ip_address', type=str, nargs='?', required=False, default='', help='IP address of client device.')
    parser.add_argument('--platform', type=str, nargs='?', required=False, default='', help='Platform type passed in from Tautulli. Example: Android')
    parser.add_argument('--device', type=str, nargs='?', required=False, default='', help='Device type passed in from Tautulli.')
    parser.add_argument('--product', type=str, nargs='?', required=False, default='', help='Product type passed in from Tautulli.')
    parser.add_argument('--player', type=str, nargs='?', required=False, default='', help='Player type passed in from Tautulli.')
    parser.add_argument('--file', type=str, nargs='?', required=False, default='', help='Full file path passed in from Tautulli.') #need to parse the filename and match it in the json file to the matching rom file
    parser.add_argument('--user', type=str, nargs='?', required=False, default='', help='Plex User passed in from Tautulli.')
    parser.add_argument('--user_id', type=str, nargs='?', required=False, default='', help='Plex UserID passed in from Tautulli.')
    
    #arguments for scanner
    parser.add_argument('--scan', action='store_true', required=False, help='Scan the library, update media, and rom mapping.')
    
    #arguments for automatic update
    parser.add_argument('--update', action='store_true', required=False, help='Update plug-in from github.')

    #testing args from tautulli
    parser.add_argument('--username', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--user_email', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--user_thumb', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--initial_stream', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--stream_local', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--stream_location', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--machine_id', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--media_type', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--title', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--library_name', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--year', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--release_date', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--updated_date', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--last_viewed_date', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--studio', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--content_rating', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--directors', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--writers', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--actors', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--genres', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--labels', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--collections', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--summary', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--tagline', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--rating', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--critic_rating', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--audience_rating', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--user_rating', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--duration', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--poster_url', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--plex_id', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--plex_url', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--filename', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--file_size', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--section_id', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--rating_key', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--art', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--thumb', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--poster_thumb', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--poster_title', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--indexes', type=str, nargs='?', required=False, default='', help='Dev')
    parser.add_argument('--remaining_time', type=str, nargs='?', required=False, default='', help='Dev')

    #--user {user} --username {username} --user_email {user_email} --user_thumb {user_thumb} --device {device} --platform {platform} --product {product} --player {player} --initial_stream {initial_stream} --ip_address {ip_address} --remaining_time {remaining_time} --stream_local {stream_local} --stream_location {stream_location} --user_id {user_id} --machine_id {machine_id} --media_type {media_type} --title {title} --library_name {library_name} --year {year} --release_date {release_date} --updated_date {updated_date} --last_viewed_date {last_viewed_date} --studio {studio} --content_rating {content_rating} --directors {directors} --writers {writers} --actors {actors} --genres {genres} --labels {labels} --collections {collections} --summary {summary} --tagline {tagline} --rating {rating} --critic_rating {critic_rating} --audience_rating {audience_rating} --user_rating {user_rating} --duration {duration} --poster_url {poster_url} --plex_id {plex_id} --plex_url {plex_url} --file {file} --filename {filename} --file_size {file_size} --section_id {section_id} --rating_key {rating_key} --art {art} --thumb {thumb} --poster_thumb {poster_thumb} --poster_title {poster_title} --indexes {indexes} --remote_access_mapping_state {remote_access_mapping_state} --remote_access_mapping_error {remote_access_mapping_error} --remote_access_public_address {remote_access_public_address} --remote_access_public_port {remote_access_public_port} --remote_access_private_address {remote_access_private_address} --remote_access_private_port {remote_access_private_port} --update_platform {update_platform}

    opts = parser.parse_args()

    #bool arguments... switches
    scan = opts.scan
    launch = opts.launch
    update = opts.update
    
    #get the plugin identifier from Plex
    infoFile = os.path.join(os.path.abspath(paths['contentsDir']), 'Info.plist')
    #print(infoFile)
    info = convertXMLtoJSON(infoFile)
    #print(json.dumps(info, indent=4))
    x = 0
    for key in info['plist']['dict']['key']: #get the agent name (maybe useful for if users want to switch and try different branches while keeping original settings)
        if key == 'CFBundleIdentifier':
            agent = info['plist']['dict']['string'][x]
            #print(agent)
            break
        x += 1
    
    '''settings from agent'''
    #get the agent settings (use it for this script as well)
    settingsFile = getSettings(paths['plexDir'], agent)
    #print(settingsFile)
    settings = convertXMLtoJSON(settingsFile)
    #print('original settings')
    #print(json.dumps(settings, indent=4))
    
    Prefs = {}
    for key, value in archer_dict.dDefaultSettings.items():
        try:
            Prefs[key] = settings['PluginPreferences'][key]
        except KeyError as e:
            Prefs[key] = value
        if Prefs[key] == None:
            Prefs[key] = value
        settingSplit = key.split('_', 1)
        if settingSplit[0] == 'enum':
            try:
                Prefs[key] = archer_dict.dict_enum_settings_map[settingSplit[-1]][Prefs[key]]
            except KeyError as e:
                pass
            if settingSplit[1] == 'LogLevel':
                logLevel = Prefs[key]
                logging.basicConfig(filename='retroarcher.log',level=logLevel) #log level should now be whatever is set in the agent or default
                logging.info('Numeric logging level set to: %s' % (logLevel))
        elif settingSplit[0] == 'int':
            Prefs[key] = int(Prefs[key])
        elif settingSplit[0] == 'list':
            Prefs[key] = Prefs[key].split(',')
        elif settingSplit[0] == 'dir':
            if os.path.isdir(Prefs[key]):
                pass
            else:
                Prefs[key] = None
                #print('%s directory does not exist: %s' % (key, value))
                logging.warning('%s directory does not exist: %s' % (key, value))
    
    #emulator and core settings... not in dDefaultSettings
    for key, value in settings['PluginPreferences'].items():
        keySplit = key.split('_')
        if keySplit[0] == 'emulator' or keySplit[0] == 'core':
            try:
                if value == None:
                    Prefs[key] = 0
                else:
                    Prefs[key] = int(value)
            except KeyError as e:
                Prefs[key] = 0
            except TypeError as e: #probably won't ever have this scenario...
                Prefs[key] = 0
    
    #print('Prefs:')
    #print(json.dumps(Prefs, indent=4))
    
    if Prefs['dir_SourceRomDirectory'] == None:
        logging.critical('Source Rom Directory does not exist or is not set in agent settings.')
        sys.exit(1)
    SourceRomDir = os.path.abspath(Prefs['dir_SourceRomDirectory'])
    
    
    '''get data folders'''
    dataFolders = getDataFolders(paths['plexDir'], agent)
    logging.info('dataFolders: %s' % (dataFolders))

    '''script arguments'''
    if scan:
        scanner(paths, SourceRomDir, dataFolders)
    
    elif launch:
        #string agruments
        clientPlatform = opts.platform #from tautulli (Android or Firefox for example)
        clientIP = opts.ip_address #from tautulli
        clientDevice = opts.device #from tautulli (Windows for example)
        clientProduct = opts.product #from tautulli (PlexWeb for example)
        clientPlayer = opts.player #from tautulli (Firefox for example)
        clientUser = opts.user #from tautulli (Firefox for example)
        clientUserId = opts.user_id
        movieName = opts.file #from tautulli

        #integer arguments
        timeRemaining = opts.remaining_time.split(':') #from tautulli... why returning 00:00:00 ?
        try:
            countdown = (int(timeRemaining[0]) * 3600) + (int(timeRemaining[1]) * 60) + (int(timeRemaining[2])) #seconds remaining
        except:
            countdown = 0
        
        '''
        #test arguments
        log = 'user: ' + str(opts.user)
        log += '\n' + 'user: ' + str(opts.username)
        log += '\n' + 'user_email: ' + str(opts.user_email)
        log += '\n' + 'user_thumb: ' + str(opts.user_thumb)
        log += '\n' + 'device: ' + str(opts.device)
        log += '\n' + 'platform: ' + str(opts.platform)
        log += '\n' + 'product: ' + str(opts.product)
        log += '\n' + 'player: ' + str(opts.player)
        log += '\n' + 'initial_stream: ' + str(opts.initial_stream)
        log += '\n' + 'ip_address: ' + str(opts.ip_address)
        log += '\n' + 'remaining_time: ' + str(opts.remaining_time)
        log += '\n' + 'stream_local: ' + str(opts.stream_local)
        log += '\n' + 'stream_location: ' + str(opts.stream_location)
        log += '\n' + 'user_id: ' + str(opts.user_id)
        log += '\n' + 'machine_id: ' + str(opts.machine_id)
        log += '\n' + 'media_type: ' + str(opts.media_type)
        log += '\n' + 'title: ' + str(opts.title)
        log += '\n' + 'library_name: ' + str(opts.library_name)
        log += '\n' + 'year: ' + str(opts.year)
        log += '\n' + 'release_date: ' + str(opts.release_date)
        log += '\n' + 'updated_date: ' + str(opts.updated_date)
        log += '\n' + 'last_viewed_date: ' + str(opts.last_viewed_date)
        log += '\n' + 'studio: ' + str(opts.studio)
        log += '\n' + 'content_rating: ' + str(opts.content_rating)
        log += '\n' + 'directors: ' + str(opts.directors)
        log += '\n' + 'writers: ' + str(opts.writers)
        log += '\n' + 'actors: ' + str(opts.actors)
        log += '\n' + 'genres: ' + str(opts.genres)
        log += '\n' + 'labels: ' + str(opts.labels)
        log += '\n' + 'collections: ' + str(opts.collections)
        log += '\n' + 'summary: ' + str(opts.summary)
        log += '\n' + 'tagline: ' + str(opts.tagline)
        log += '\n' + 'rating: ' + str(opts.rating)
        log += '\n' + 'critic_rating: ' + str(opts.critic_rating)
        log += '\n' + 'audience_rating: ' + str(opts.audience_rating)
        log += '\n' + 'user_rating: ' + str(opts.user_rating)
        log += '\n' + 'duration: ' + str(opts.duration)
        log += '\n' + 'poster_url: ' + str(opts.poster_url)
        log += '\n' + 'plex_id: ' + str(opts.plex_id)
        log += '\n' + 'plex_url: ' + str(opts.plex_url)
        log += '\n' + 'file: ' + str(opts.file)
        log += '\n' + 'filename: ' + str(opts.filename)
        log += '\n' + 'file_size: ' + str(opts.file_size)
        log += '\n' + 'section_id: ' + str(opts.section_id)
        log += '\n' + 'rating_key: ' + str(opts.rating_key)
        log += '\n' + 'art: ' + str(opts.art)
        log += '\n' + 'thumb: ' + str(opts.thumb)
        log += '\n' + 'poster_thumb: ' + str(opts.poster_thumb)
        log += '\n' + 'poster_title: ' + str(opts.poster_title)
        log += '\n' + 'indexes: ' + str(opts.indexes)
        #log += '\n' + 'remote_access_mapping_state: ' + str(opts.remote_access_mapping_state)
        #log += '\n' + 'remote_access_mapping_error: ' + str(opts.remote_access_mapping_error)
        #log += '\n' + 'remote_access_public_address: ' + str(opts.remote_access_public_address)
        #log += '\n' + 'remote_access_public_port: ' + str(opts.remote_access_public_port)
        #log += '\n' + 'remote_access_private_address: ' + str(opts.remote_access_private_address)
        #log += '\n' + 'remote_access_private_port: ' + str(opts.remote_access_private_port)
        #log += '\n' + 'update_platform: ' + str(opts.update_platform)
        log += '\n' + 'clientIP: ' + str(clientIP)
        
        with open('test.log', 'w', encoding='utf-8') as f: #https://stackoverflow.com/a/35086151/11214013
                f.write(log)
        '''
        serverIP = get_ip()
        logging.info('serverIP: %s' % (serverIP))
        
        if serverIP.rsplit('.',1)[0] == clientIP.rsplit('.',1)[0]: #this is only checking the very first part of the IP... should we check the next 2 as well?
            launcher(clientIP, clientPlatform, clientDevice, clientProduct, clientPlayer, clientUser, clientUserId, movieName, dataFolders)
        else:
            logging.error('Client appears to be a remote client. RetroArcher cannot execute scripts on a remote client yet. If the client really is local to the server, try accessing your Plex server at "http://x.x.x.x:32400/web" instead of "https://app.plex.tv"')
            sys.exit(1)

