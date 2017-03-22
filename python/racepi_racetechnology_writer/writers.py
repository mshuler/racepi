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

DL1_ANALOG_MAX_VOLTAGE = 5.0
MAX_BRAKE_PRESSURE = float(1e-6)  # TODO determine proper unit


class RaceTechnologyDL1FeedWriter:

    def __init__(self):
        self.__socket_listener_done = Event()
        self.__active_connections = []
        self.pending_messages = []

        # open and bind RFCOMM listener
        self.__socket_listener_thread = \
            Thread(target=RaceTechnologyDL1FeedWriter.__bind_rfcomm_socket,
                   args=(self.__socket_listener_done, self.__active_connections))
        self.__socket_listener_thread.setDaemon(True)
        self.__socket_listener_thread.start()

        self.__earliest_time_seen = time.time()

    def close(self):
        self.__socket_listener_done.set()

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

    def __queue_mesg(self, msg):
        self.pending_messages.append(msg)

    def flush_queued_messages(self):
        if not self.pending_messages:
            return

        # join each message with its checksum, then
        # join all data together into a bulk message
        msg = b"".join(
            [b"".join([x, get_message_checksum(x)]) for x in self.pending_messages])
        
        self.pending_messages = []

        # write to all open RFCOMM connections
        for client in self.__active_connections:
            try:
                client.send(msg)
            except ConnectionResetError:
                # connection terminated
                self.__active_connections.remove(client)
                client.close()

    def send_timestamp(self, timestamp_seconds):
        if not timestamp_seconds:
            return

        time_delta = timestamp_seconds - self.__earliest_time_seen
        msg = get_timestamp_message_bytes(time_delta * 1000.0)
        self.__queue_mesg(msg)

    def send_gps_speed(self, speed):
        if not speed:
            return

        msg = get_gps_speed_message_bytes(speed*100.0)
        self.__queue_mesg(msg)

    def send_gps_pos(self, lat, lon):
        if not lat or not lon:
            return

        msg = get_gps_pos_message_bytes(float(lat) * float(1e7), float(lon) * float(1e7))
        self.__queue_mesg(msg)

    def send_xyz_accel(self, x_accel, y_accel, z_accel):

        msg = get_xy_accel_message_bytes(x_accel, y_accel)
        self.__queue_mesg(msg)
        # TODO, implement z accel

    def send_rpm(self, rpm):
        msg = get_rpm_message_bytes(rpm)
        self.__queue_mesg(msg)

    def send_tps(self, tps_percentage):
        msg = get_tps_message_bytes(tps_percentage/100.0*DL1_ANALOG_MAX_VOLTAGE)
        self.__queue_mesg(msg)

    def send_brake_pressure(self, brake_pressure):
        val = brake_pressure / MAX_BRAKE_PRESSURE
        val *= DL1_ANALOG_MAX_VOLTAGE
        msg = get_brake_pressure_message_bytes(val)
        self.__queue_mesg(msg)