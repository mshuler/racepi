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

XYACCEL_MESSAGE_ID = 8
TIMESTAMP_MESSAGE_ID = 9
GPS_POS_MESSAGE_ID = 10
GPS_SPEED_MESSAGE_ID = 11
RPM_MESSAGE_ID = 18
TPS_MESSAGE_ID = 20  # Analog 1
BRAKE_PRESSURE_MESSAGE_ID = 20  # Analog 2


XYACCEL_FMT = ">5B"
TIMESTAMP_FMT = ">4B"    # header, time
GPS_POS_FMT = "!BiiI"   # header, latitude, longitude, accuracy
GPS_SPEED_FMT = "!BII"  # header, speed, accuracy
RPM_FMT = ">4B"  # header, engine speed as frequency
ANALOG_FMT = ">3B"  # header, value as voltage (5v)

DL1_PERIOD_CONSTANT = 6e6


def get_message_checksum(msg):
    cs = 0
    for d in msg:
        cs += d & 0xFF
    return bytes([cs & 0xFF])


def get_timestamp_message_bytes(time_millis):
    """
    :param time_millis: time since service start, in milliseconds
    :return:
    """
    # careful here, python3 ints are 64 bits wide when they need to be
    t = int(time_millis)
    t1 = (t >> 16) & 0xFF
    t2 = (t >> 8) & 0xFF
    t3 = t & 0xFF
    return struct.pack(TIMESTAMP_FMT, TIMESTAMP_MESSAGE_ID, t1, t2, t3)


def __get_accel_bytes(accel_value):
    """
    Encode a single accel value
    :param accel_value: accelerometer value, in G
    :return: two bytes of race-tech encoded accel data
    """
    b1 = 0

    tmp_accel = accel_value

    if accel_value > 0.0:
        b1 |= 0x80
    else:
        tmp_accel *= -1
    b1 |= (int(tmp_accel) & 0x7F)
    b2 = (int((tmp_accel - float(b1)) * 0x100) & 0xFF)
    return b1, b2


def get_xy_accel_message_bytes(x_accel, y_accel):
    x1, x2 = __get_accel_bytes(x_accel)
    y1, y2 = __get_accel_bytes(y_accel)
    return struct.pack(XYACCEL_FMT, XYACCEL_MESSAGE_ID, x1, x2, y1, y2)


def get_gps_pos_message_bytes(gps_lat_xe7, gps_long_xe7):
    """
    :param gps_lat_xe7: latitude value, scaled by 1e7
    :param gps_long_xe7: longitude value, scale by 1e7
    :return:
    """
    return struct.pack(GPS_POS_FMT, GPS_POS_MESSAGE_ID, int(gps_lat_xe7), int(gps_long_xe7), 0)


def get_gps_speed_message_bytes(gps_speed_x100):
    """
    :param gps_speed_x100: speed (m/s), scaled by 100
    :return:
    """
    return struct.pack(GPS_SPEED_FMT, GPS_SPEED_MESSAGE_ID, int(gps_speed_x100), 0)


def get_rpm_message_bytes(rpm):
    """
    :param rpm:
    :return:
    """
    rpm /= 60  # convert to frequency
    if rpm > 0.0:
        rpm = 1/rpm
    rpm *= DL1_PERIOD_CONSTANT
    val = int(rpm)
    b1 = (val >> 16) & 0xFF
    b2 = (val >> 8) & 0xFF
    b3 = val & 0xFF
    return struct.pack(RPM_FMT, RPM_MESSAGE_ID, b1, b2, b3)


def get_analog_message_bytes(voltage, message_id):
    val = int(voltage * 1000.0)
    b1 = (val >> 8) & 0xFF
    b2 = val & 0xFF
    return struct.pack(ANALOG_FMT, message_id, b1, b2)


def get_tps_message_bytes(voltage):
    return get_analog_message_bytes(voltage, TPS_MESSAGE_ID)


def get_brake_pressure_message_bytes(voltage):
    return get_analog_message_bytes(voltage, BRAKE_PRESSURE_MESSAGE_ID)