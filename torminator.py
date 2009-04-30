#!/usr/bin/python

import string, cgi, time, urllib
from threading import Thread
import thread
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import libtorrent as lt
from urlparse import urlparse
import re
import json
import ConfigParser
from restful import RestfulHandler
from torrentserver import TorrentServer



def main():
  try:
    torrent_server = TorrentServer("/home/amchale/.torminator.conf")
    restful_server = HTTPServer(('', 3001), RestfulHandler)

    torrent_server.restful_server = restful_server
    restful_server.torrent_server = torrent_server

    restful_server.serve_forever()
  except KeyboardInterrupt as e:
    print "Keyboard interrupt.  Exiting."
    quit()


    
if __name__ == '__main__':
  main()

