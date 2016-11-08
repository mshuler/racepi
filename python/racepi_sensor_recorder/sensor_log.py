#!/usr/bin/env python2
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
"""
This is a tool for recording autocross performance data
from multiple sensor sources. Each sensor source implements
a get_data() api runs in its own system process to allow
for pre-emptive scheduling and to limit contention for
system resources.
"""

import time
from collections import defaultdict
from pi_sense_hat_imu import RpiImuSensorHandler
from gps_handler import GpsSensorHandler
from sqlite_handler import DbHandler
from can_handler import CanSensorHandler
from pi_sense_hat_display import RacePiStatusDisplay, SenseHat

DEFAULT_DB_LOCATION = "/home/donour/test.db"
ACTIVATE_RECORDING_M_PER_S = 6.0
MOVEMENT_THRESHOLD_M_PER_S = 1.0
DEFAULT_DATA_BUFFER_TIME_SECONDS = 10.0


class DataBuffer:
    """
    Simple collection of buffers for sensor data
    """
    def __init__(self):
        self.data = defaultdict(list)

    def add_sample(self, source_name, values):
        self.data[source_name].extend(values)

    def expire_old_samples(self, expire_time):
        """
        Expire (remove) all samples older than specified time
        :param expire_time: expiration age timestamp
        """
        for k in self.data:
            while self.data[k] and self.data[k][0][0] < expire_time:
                self.data[k].pop(0)

    def get_available_sources(self):
        return self.data.keys()

    def get_sensor_data(self, sensor_source):
        """
        Get data for specified source and clear buffer
        :param sensor_source: name of sensor source
        :return: data for specified sensor source
        """
        # fail early if an invalid source is requested
        if sensor_source not in self.data:
            raise ValueError("Invalid source specified")

        return self.data[sensor_source]

    def clear(self):
        self.data.clear()


class SensorLogger:
    """
    Main control logic for logging and writing to database

    The logger relies on GPS speed data for activating and deactivating
    sessions. Without GPS speed data, a manual triggering is required.
    """

    def __init__(self, database_location=DEFAULT_DB_LOCATION, can_ids=[]):

        self.data = DataBuffer()
        self.display = None
        if SenseHat:
            self.display = RacePiStatusDisplay()

        print("Opening Database")
        # TODO: look at opening DB as needed
        # to avoid corruption of tables
        self.db_handler = DbHandler(database_location)

        print("Opening sensor handlers")
        self.handlers = {
            'gps': GpsSensorHandler(),
            'imu': RpiImuSensorHandler(),
            'can': CanSensorHandler(can_ids),
        }

    def start(self):

        for h in self.handlers.values():
            h.start()

        recording_active = False
        update_times = defaultdict(int)
        session_id = None

        try:
            while True:
                new_data = defaultdict(list)
                for h in self.handlers:
                    new_data[h] = self.handlers[h].get_all_data()
                    self.data.add_sample(h, new_data[h])

                if new_data['gps']:
                    is_moving = True in \
                                [s[1].get('speed') > ACTIVATE_RECORDING_M_PER_S for s in new_data['gps']]

                    if is_moving:
                        if not recording_active:  # activate recording
                            session_id = self.db_handler.get_new_session()
                            print("New session: %s" % str(session_id))
                            # look for last sample before car moved, clear samples before that
                            gps_history = self.data.get_sensor_data('gps')
                            self.data.expire_old_samples(
                                max(
                                    [s[0] if s[1]['speed'] < MOVEMENT_THRESHOLD_M_PER_S else 0 for s in gps_history]
                                ))
                            recording_active = True
                    else:
                        if recording_active:  # deactivate recording
                            self.db_handler.populate_session_info(session_id)
                            recording_active = False
                if recording_active:
                    try:
                        # TODO: insert all in one call so we can do only one commit
                        self.db_handler.insert_gps_updates(self.data.get_sensor_data('gps'), session_id)
                        self.db_handler.insert_imu_updates(self.data.get_sensor_data('imu'), session_id)
                        self.db_handler.insert_can_updates(self.data.get_sensor_data('can'), session_id)
                        self.data.clear()
                    except TypeError as te:
                        print("Failed to insert data: %s" % te)
                else:
                    # clear old data in buffer                    
                    self.data.expire_old_samples(time.time() - 10.0)

                # display update logic
                for h in self.handlers:
                    if new_data[h]:
                        update_times[h] = new_data[h][-1][0]

                if self.display:
                    self.display.refresh_display(update_times['gps'],
                                                 update_times['imu'],
                                                 update_times['can'],
                                                 recording_active)

                time.sleep(0.25)  # there is no reason to ever poll faster than this

        finally:
            for h in self.handlers.values():
                h.stop()


if __name__ == "__main__":
    sl = SensorLogger()
    sl.start()
