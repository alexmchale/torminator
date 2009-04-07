import string, cgi, time, urllib
from threading import Thread
import thread
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import libtorrent as lt
from urlparse import urlparse
import re
import json
import ConfigParser
import os



def search(func, list):
  searchfunc = lambda z, x: z or (func(x) and x) or None
  return reduce(searchfunc, list, None)


def search_with_index(func, list):
  for i in range(len(list)):
    if func(list[i]):
      return (list[i], i)
  return None



class TorrentServer:
  def __init__(self, config_file):
    self.DEFAULT_SETTINGS = {
      'first_torrent_port': 6881,
      'last_torrent_port':  6891,
      'save_path':          '/tmp',
      'complete_path':      '/media/MediaCenter/Downloads',
      'torrents':           []
    }

    self.config_file = config_file
    self.read_settings()

    self.session = lt.session()
    self.session.listen_on(self.settings['first_torrent_port'], self.settings['last_torrent_port'])

    self.apply_settings()


  # Add the torrent at the given URL and return its name.
  # If files_to_include is not empty, all files not in that 
  # array will be prioritized to 0.
  def add(self, torrent_url, files_to_include = []):  
    torrent_raw = urllib.urlopen(torrent_url).read()
    ti = lt.torrent_info(torrent_raw, len(torrent_raw))

    h = self.find(ti.name())
    if h: raise TorrentExistsException(h)

    torrent_params = {
      'ti':        ti,
      'save_path': str(self.settings['save_path'])
    }

    h = self.session.add_torrent(torrent_params)

    if len(files_to_include) > 0:
      priorities = [files_to_include.count(f.path) and 1 or 0 for f in ti.files()]
      h.prioritize_files(priorities)

    if not search(lambda t: t['name'] == ti.name(), self.settings['torrents']):
      self.settings['torrents'].append({ 'name': ti.name(), 'url': torrent_url, 'files': files_to_include })
    self.write_settings()

    return ti.name()


  # Returns information about the torrent at the given URL.
  def torrent_at_url(self, torrent_url):
    torrent_raw = urllib.urlopen(torrent_url).read()
    ti = lt.torrent_info(torrent_raw, len(torrent_raw))

    return { 
      'name': ti.name(), 
      'size': ti.total_size(), 
      'files': [ { 'path': f.path, 'size': f.size } for f in ti.files()]
    }


  # Remove the torrent with the given name from the server.
  def remove(self, torrent_name):
    t = search(lambda t: t['name'] == ti.name(), self.settings['torrents'])
    if t:
      self.settings['torrents'].remove(t)
    self.write_settings()

    h = self.find(torrent_name)
    if h:
      self.session.remove_torrent(h)
      return True

    return False


  # Prepare a hash with the current status of this server.
  def status(self):
    ss = self.session.status()

    return {
      'session': {
        'has_incoming_connections': ss.has_incoming_connections,

        'upload_rate': ss.upload_rate,
        'download_rate': ss.download_rate,

        'payload_upload_rate': ss.payload_upload_rate,
        'payload_download_rate': ss.payload_download_rate,

        'total_upload': ss.total_upload,
        'total_download': ss.total_download,

        'total_payload_download': ss.total_payload_download,
        'total_payload_upload': ss.total_payload_upload,

        'num_peers': ss.num_peers
      },

      'settings': self.settings,
      'torrents': [self.handle_status(h) for h in self.session.get_torrents()]
    }

    return status


  # Prepare a hash with the current status of the given torrent handle.
  def handle_status(self, h):
    hs = h.status()
    ti = h.get_torrent_info() 

    status = { 
      'name': h.name(), 
      'size': ti.total_size(),

      'state': str(hs.state),
      'paused': hs.paused,
      'progress': hs.progress,
      'error': hs.error,

      'current_tracker': hs.current_tracker,

      'total_download': hs.total_download,
      'total_upload': hs.total_upload,

      'total_payload_download': hs.total_payload_download,
      'total_payload_upload': hs.total_payload_upload,

      'total_failed_bytes': hs.total_failed_bytes,
      'total_redundant_bytes': hs.total_redundant_bytes,

      'download_rate': hs.download_rate,
      'upload_rate': hs.upload_rate,

      'download_payload_rate': hs.download_payload_rate,
      'upload_payload_rate': hs.upload_payload_rate,

      'num_peers': hs.num_peers,

      'files': [] 
    }

    for (file, progress, prio) in self.handle_files(h):
      status['files'].append({
        'path': file.path,
        'size': file.size,
        'progress': progress,
        'priority': prio
      })

    return status


  # Returns an array of tuples about this handle's files (Name, Progress, Priority).
  def handle_files(self, h):
    ti = h.get_torrent_info()
    return zip(ti.files(), h.file_progress(), h.file_priorities())


  def set_file_priority(self, torrent_name, file_path, priority):
    h = self.find(torrent_name)
    if h:
      (file, index) = search_with_index(lambda f: f.path == file_path, h.get_torrent_info().files())
      priorities = h.file_priorities()
      priorities[index] = priority
      h.prioritize_files(priorities)
      return True

    return False


  # Search the active handles for a torrent with the given name.
  def find(self, torrent_name):
    return search(lambda h: h.name() == torrent_name, self.session.get_torrents())


  # Applies the values in the settings hash to the current session.
  def apply_settings(self):
    self.if_set(self.session.set_upload_rate_limit, int, 'upload_rate_limit')
    self.if_set(self.session.set_download_rate_limit, int, 'download_rate_limit')


  # Reads the settings in the current session into the settings hash.
  def read_settings(self):
    if os.path.isfile(self.config_file):
      with open(self.config_file, 'r') as file:
        self.settings = json.loads(file.read())
    else:
      self.settings = {}

    for key, value in self.DEFAULT_SETTINGS:
      if not self.settings.has_key(key):
        self.settings[key] = value

    for t in self.settings['torrents']:
      h = self.find(t['name'])
      if not h: self.add(t['url'], t['files'])


  # Write the current settings in memory out to disk.
  def write_settings(self):
    with open(self.config_file, 'wb') as file:
      file.write(json.dumps(self.settings))

    self.apply_settings()


  # Applies the new key/value if specified, then applies the current settings to the torrent session.
  # Returns the old key value.
  def set(self, key = None, value = None):
    return_value = None

    if key:
      if self.settings.has_key(key): return_value = self.settings[key]
      self.settings[key] = value

    self.write_settings()

    return return_value


  # If the given field is set in the settings hash, call the given method on it.
  def if_set(self, func, cast, key):
    if self.settings.has_key(key):
      func(cast(self.settings[key]))



class TorrentExistsException(Exception):
  def __init__(self, handle):
    self.handle = handle


    

