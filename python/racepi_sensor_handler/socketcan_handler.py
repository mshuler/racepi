#!/usr/bin/env python3
# Copyright 2016 Donour Sizemore
#
# This file is part of RacePi
#
# RacePi is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2.
#
# RacePi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with RacePi.  If not, see <http://www.gnu.org/licenses/>.

import socket
import time
import struct

from sensor_handler import SensorHandler

if not hasattr(socket, "PF_CAN"):
    raise RuntimeError("No SocketCAN support found: please use Python3.3+")

DEFAULT_CAN_DEVICE = "vcan0"

# Basic data frame format: https://en.wikipedia.org/wiki/CAN_bus#Data_frame
CAN_MESSAGE_FMT = "<IB3x8B"


class SocketCanSensorHandler(SensorHandler):

    def __init__(self, device_name=DEFAULT_CAN_DEVICE, can_filters=[]):
        SensorHandler.__init__(self, self.__record_from_can)
        self.dev_name = device_name
        self.cansocket = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        self.cansocket.bind((self.dev_name,))

    def __record_from_can(self):

        if not self.pipe_out:
            raise ValueError("Illegal argument, no queue specified")

        message_size = struct.calcsize(CAN_MESSAGE_FMT)

        print("Starting SIMULATED CAN reader")
        while not self.doneEvent.is_set():
            data = self.cansocket.recv(message_size)
            now = time.time()
            if data:
                data = struct.unpack(CAN_MESSAGE_FMT, data)
                # TODO, standarize the message here so multiple
                # can handlers can deliver the data to the sensor
                # logger
                self.pipe_out.send((now, data))
            time.sleep(0.1)
        print("Shutting down CAN reader")

if __name__ == "__main__":
    h = SocketCanSensorHandler()
    h.start()
    while True:
        data = h.get_all_data()
        if data:
            print(data)
        else:
            time.sleep(0.1)
