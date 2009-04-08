import string, cgi, time, urllib
from threading import Thread
import thread
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import libtorrent as lt
from urlparse import urlparse
import re
import json
import ConfigParser



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

    handle = self.torrent_server.find(name)

    if handle:
      try:    
        status = self.torrent_server.handle_status(handle)
      except:
        status = { 'code': 400, 'error_message': 'No active torrent was found with that name.' }
    elif args.has_key('url'):
      try:    
        status = self.torrent_server.torrent_at_url(args['url'])
      except Exception as e:
        print 'Bad URL:', e 
        status = { 'code': 400, 'error_message': 'The torrent at that URL could not be loaded.' }
    else:
      status = self.torrent_server.status()

    self.respond(status)


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
        response['code'] = 201
        response['message'] = 'The torrent was successfully added.'
        response['name'] = name
      else:
        response['code'] = 404
        response['error_message'] = 'No torrent found.'
    except TorrentExistsException as e:
      response['code'] = 409
      response['error_message'] = 'The server is already running that torrent.'
      response['name'] = e.handle.name()
    except Exception as e:
      response['code'] = 500
      response['error_message'] = e.message

    self.respond(response)


  # Remove the given torrent from the server.
  def do_DELETE(self):
    (name, args) = self.parse_query()

    if self.torrent_server.remove(name):
      response = { 'code': 200, 'message': 'The torrent was successfully removed.' }
    else:
      response = { 'code': 404, 'error_message': 'That torrent was not found.' }

    self.respond(response)


  # Updates configuration settings.
  def do_PUT(self):
    (name, args) = self.parse_query()

    handle = self.torrent_server.find(name)

    if handle:
      if args.has_key('path') and args.has_key('priority'):
        self.torrent_server.set_file_priority(name, args['path'], int(args['priority']))
    else:
      for key, value in args.items():
        self.torrent_server.set(key, value)

    self.respond({ 'code': 200 })


  # Parses a URL query field into a request name and an argument hash.
  def parse_query(self):
    (name, argstr) = re.search('^/*([^?]*)\\?*([^?]*?)$', self.path).groups()
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


  # Dispatch the given response to the client.
  def respond(self, response):
    if response.has_key('code'):
      code = response['code']
    else:
      code = 200

    self.send_response(code)
    self.end_headers()
    self.wfile.write(json.dumps(response))



