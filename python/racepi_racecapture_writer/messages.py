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

import struct

TIMESTAMP_MESSAGE_ID = 0x9
GPS_POS_MESSAGE_ID = 0x10
GPS_SPEED_MESSAGE_ID = 0x11

TIMESTAMP_FMT = "!BI"    # header, time
GPS_POS_FMT = "!BIIIB"   # header, latitude, longitude, accuracy, filler byte
GPS_SPEED_FMT = "!BIIB"  # header, speed, accuracy, filler byte


def get_timestamp_message_bytes(time_millis):
    # careful here, python3 ints are 64 bits wide when they need to be
    return struct.pack(TIMESTAMP_FMT, TIMESTAMP_MESSAGE_ID, int(time_millis))


def get_gps_pos_message_bytes(gps_lat_xe7, gps_long_xe7):
    """
    :param gps_lat_xe7: latitude value, scaled by 1e7
    :param gps_long_xe7: longitude value, scale by 1e7
    :return:
    """
    return struct.pack(GPS_POS_FMT, GPS_POS_MESSAGE_ID, int(gps_lat_xe7), int(gps_long_xe7), 0, 0)


def get_gps_speed_message_bytes(gps_speed_x100):
    """
    :param gps_speed_x100: speed (m/s), scaled by 100
    :return:
    """
    return struct.pack(GPS_SPEED_FMT, GPS_SPEED_MESSAGE_ID, int(gps_speed_x100), 0, 0)
