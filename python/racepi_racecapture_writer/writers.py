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
from .messages import *


class RaceCaptureFeedWriter:

    def __init__(self, output):
        self.output = output
        self.__earliest_time_seen = time.time()

    def __send_mesg(self, msg):
        print(msg)
        #self.output.write(msg)

    def send_timestamp(self, timestamp_seconds):
        time_delta = timestamp_seconds - self.__earliest_time_seen
        msg = get_timestamp_message_bytes(time_delta * 1000.0)
        self.__send_mesg(msg)

    def send_gps_speed(self, speed):
        msg = get_gps_speed_message_bytes(speed*100.0)
        self.__send_mesg(msg)

    def send_gps_pos(self, lat, lon):
        msg = get_gps_pos_message_bytes(lat * float(1e7), lon * float(1e7))
        self.__send_mesg(msg)