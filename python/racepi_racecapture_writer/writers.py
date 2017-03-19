# Copyright 2017 Donour Sizemore
#
# This file is part of RacePi
#
# RacePi is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# RacePi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with RacePi.  If not, see <http://www.gnu.org/licenses/>.

import time
import socket
from threading import Event, Thread

from .messages import *


class RaceCaptureFeedWriter:

    def __init__(self, output):
        self.__socket_listener_done = Event()
        self.__active_connections = []

        # open and bind RFCOMM listener
        self.__socket_listener_thread = \
            Thread(target=RaceCaptureFeedWriter.__bind_rfcomm_socket,
                   args=(self.__socket_listener_done, self.__active_connections))
        self.__socket_listener_thread.start();

        self.output = output
        self.__test_file = open("/external/testfile", "wb")
        print("Writing RC testfile: /external/testfile")
        self.__earliest_time_seen = time.time()

    @staticmethod
    def __bind_rfcomm_socket(done_event, clients):

        mac = '0:0:0:0:0:0'
        port = 1
        backlog = 1
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        s.bind((mac, port))
        s.listen(backlog)
        while not done_event.is_set():
            client, addr = s.accept()
            print("Registering: %s" % str(addr))
            clients.append(client)

        for c in clients:
            c.close()
        s.close()

    def __send_mesg(self, msg):

        # write to all open RFCOMM connections
        # send message content
        self.__test_file.write(msg)
        # send checksum
        self.__test_file.write(get_message_checksum(msg))

    def send_timestamp(self, timestamp_seconds):
        if not timestamp_seconds:
            return

        time_delta = timestamp_seconds - self.__earliest_time_seen
        msg = get_timestamp_message_bytes(time_delta * 1000.0)
        self.__send_mesg(msg)

    def send_gps_speed(self, speed):
        if not speed:
            return

        msg = get_gps_speed_message_bytes(speed*100.0)
        self.__send_mesg(msg)

    def send_gps_pos(self, lat, lon):
        if not lat or not lon:
            return

        msg = get_gps_pos_message_bytes(float(lat) * float(1e7), float(lon) * float(1e7))
        self.__send_mesg(msg)
