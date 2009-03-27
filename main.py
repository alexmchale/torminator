import string, cgi, time, urllib
from threading import Thread
import thread
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import libtorrent as lt
from urlparse import urlparse
import re
import json
import ConfigParser



def main():
  try:
    torrent_server = TorrentServer("/home/amchale/.torminator.conf")

    restful_server = HTTPServer(('', 3001), RestfulHandler)
    restful_server.torrent_server = torrent_server

    restful_server.serve_forever()
    
  except KeyboardInterrupt:
    print '^C received, shutting down server.'
    server.socket.close()



# GET - Get the current status of the server.
# POST - Add a new torrent file to the server.
# PUT - Set a server setting.
# DELETE - Remove the given torrent from the server.
class RestfulHandler(BaseHTTPRequestHandler):
  def __init__(self, request, client_address, server):
    self.torrent_server = server.torrent_server
    BaseHTTPRequestHandler.__init__(self, request, client_address, server)


  # Get prompts for the status of the server.
  def do_GET(self):
    (name, args) = self.parse_query()
    status = self.torrent_server.status()

    self.send_response(200)
    self.end_headers()
    self.wfile.write(json.dumps(status))


  # Post sends a new torrent file.
  # The content of the post is the URL of the torrent file.
  def do_POST(self):
    (name, args) = self.parse_query()
    response = {}

    try:
      files = self.parse_body()
      if len(files) > 0:
        (torrent_url, files_to_include) = (files[0], files[1:])
        name = self.torrent_server.add(torrent_url, files_to_include)
        response['code'] = 200
        response['message'] = 'The torrent was successfully added.'
        response['name'] = name
      else:
        response['code'] = 404
        response['message'] = 'No torrent found.'
    except TorrentExistsException as e:
      response['code'] = 409
      response['error_message'] = 'The server is already running that torrent.'
      response['name'] = e.handle.name()
    except Exception as e:
      response['code'] = 400
      response['error_message'] = e.message

    self.send_response(response['code'])
    self.end_headers()
    self.wfile.write(json.dumps(response))


  # Remove the given torrent from the server.
  def do_DELETE(self):
    (name, args) = self.parse_query()

    self.torrent_server.remove(name)

    self.send_response(200)
    self.end_headers()


  # Updates configuration settings.
  def do_PUT(self):
    (name, args) = self.parse_query()

    for key, value in args:
      self.torrent_server.set(key, value)


  # Parses a URL query field into a request name and an argument hash.
  def parse_query(self):
    (name, argstr) = re.search('^([^?]*)\\?*([^?]*?)$', self.path).groups()
    args = {}

    for pairs in argstr.split('&'):
      a = pairs.split('=')
      if len(a) == 1: args[a[0]] = True
      if len(a) == 2: args[a[0]] = urllib.unquote(a[1])

    return (name, args)


  # Breaks the input into an array of lines.
  def parse_body(self):
    body = self.read_data()

    lines = []

    for line in re.split("[\n\r]+", body):
      if not re.match("^\s*$", line):
        lines.append(line)

    return lines


  # Read the data sent by the client.
  def read_data(self):
    return self.rfile.read(int(self.headers["content-length"]))



class TorrentExistsException(Exception):
  def __init__(self, handle):
    self.handle = handle



class TorrentServer:
  def __init__(self, config_file):
    FIRST_TORRENT_PORT = 6881
    LAST_TORRENT_PORT  = 6891

    self.session = lt.session()
    self.session.listen_on(FIRST_TORRENT_PORT, LAST_TORRENT_PORT)

    self.config_file = config_file
    self.read_settings()


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
      'save_path': '.'
    }

    h = self.session.add_torrent(torrent_params)

    if len(files_to_include) > 0:
      priorities = [files_to_include.count(f) and 1 or 0 for f in ti.files()]
      h.prioritize_files(priorities)

    return ti.name()

  # Remove the torrent with the given name from the server.
  def remove(self, torrent_name):
    h = self.find(torrent_name)
    if h: self.session.remove_torrent(h)

  # Prepare a hash with the current status of this server.
  def status(self):
    return {
      'settings': self.settings,
      'torrents': [self.handle_status(h) for h in self.session.get_torrents()]
    }

    return status

  # Prepare a hash with the current status of the given torrent handle.
  def handle_status(self, h):
    status = { 
      'name': h.name(), 
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
    return zip(ti.files(), h.file_progress(), h.file_priorities)

  # Search the active handles for a torrent with the given name.
  def find(self, torrent_name):
    if torrent_name:
      for h in self.session.get_torrents():
        if h.name() == torrent_name:
          return h

    return None

  # Applies the values in the settings hash to the current session.
  def apply_settings(self):
    self.if_set(self.session.set_upload_rate_limit, int, 'upload_rate_limit')
    self.if_set(self.session.set_download_rate_limit, int, 'download_rate_limit')

  # Reads the settings in the current session into the settings hash.
  def read_settings(self):
    self.settings = {}

    config = ConfigParser.SafeConfigParser()
    config.read(self.config_file)
    for key, value in config.items('Torminator'):
      self.settings[key] = value

    self.apply_settings()

  # Applies the new key/value if specified, then applies the current settings to the torrent session.
  def set(self, key = None, value = None):
    if key: self.settings[key] = value

    config = ConfigParser.SafeConfigParser()
    config.add_section('Torminator')
    for key, value in self.settings:
      config.set('Torminator', key, value)

    with open(self.config_file, 'wb') as configfile:
      config.write(configfile)

    self.apply_settings()

  # If the given field is set in the settings hash, call the given method on it.
  def if_set(self, func, cast, key):
    if self.settings.has_key(key):
      func(cast(self.settings[key]))

  # Fill the given field with the result of the given method unless it's already set.
  def set_unless(self, key, func):
    if not self.settings.has_key(key):
      self.settings[key] = func()


    
if __name__ == '__main__':
  main()

