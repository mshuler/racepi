#!/usr/bin/env python3
# Copyright 2016-7 Donour Sizemore
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
from enum import Enum
from collections import defaultdict

from racepi_racecapture_writer.writers import RaceCaptureFeedWriter
from .pi_sense_hat_display import RacePiStatusDisplay, SenseHat
from .data_buffer import DataBuffer

ACTIVATE_RECORDING_M_PER_S = 3.5
MOVEMENT_THRESHOLD_M_PER_S = 2.0
DEFAULT_DATA_BUFFER_TIME_SECONDS = 10.0


class LoggerState(Enum):
    initialized = 1
    ready = 2
    logging = 3
    done = 4


class SensorLogger:
    """
    Main control logic for logging and writing to database

    The logger relies on GPS speed data for activating and deactivating
    sessions. Without GPS speed data, a manual trigger is required.

    The logger can be in the following states:

    initialized: configured sensors are ready for logging
    ready: sensor ready and actively buffered
    logging: actively logging data to the database
    done: logging is no longer possible
    """

    def __init__(self, db_handler, sensor_handlers={}):
        """
        Create new logger instance with specified handlers. Input and output
        handlers are required.

        :param db_handler: output handler for writing sensor data to a database
        :param sensor_handlers: input data handlers, these should be racepi sensor_handlers
        """
        self.data = DataBuffer()
        self.display = None
        if SenseHat:
            self.display = RacePiStatusDisplay()        

        self.handlers = sensor_handlers
        self.db_handler = db_handler
        try:
            self.db_handler.connect()
        except Exception as e:
            print(e)
            print("No database handler available, recording disabled")
            self.db_handler = None

        self.session_id = None
        self.rc_writer = RaceCaptureFeedWriter(None)
        self.state = LoggerState.initialized

    @staticmethod
    def safe_speed_to_float(v):
        """
        convert speed value to float in typesafe way
        :param v:
        :return: float value of v, 0.0 if conversion fails
        """
        if not v:
            return 0.0
        try:
            return float(v)
        except ValueError:
            return 0.0

    def get_new_data(self):
        """
        Get dictionary of new data from all handlers and
        add all data to the current buffer
        :return: data dictionary
        """
        new_data = defaultdict(list)
        for h in self.handlers:
            new_data[h] = self.handlers[h].get_all_data()
            self.data.add_sample(h, new_data[h])
        return new_data

    def activate_conditions(self, data):
        """
        Determine whether recording should be activated based on this
        sample of data
        :param data:
        :return: true if activation conditions exist else false
        """

        # we cannot record without a DB destination
        if not self.db_handler:
            return False

        if not data or 'gps' not in data:
            return False

        # look for any sample above the speed threshold
        return True in \
            [SensorLogger.safe_speed_to_float(s[1].get('speed')) > ACTIVATE_RECORDING_M_PER_S
             for s in data['gps']]

    def deactivate_conditions(self, data):
        """
        Determine whether recording should be de-activated based on this
        sample of data
        :param data:
        :return: true if de-activation conditions exist else false
        """
        if not data or 'gps' not in data:
            return False

        # loop for any sample above threshold, true only if there are none
        return True not in \
            [SensorLogger.safe_speed_to_float(s[1].get('speed')) > MOVEMENT_THRESHOLD_M_PER_S
             for s in data['gps']]

    def write_data_rc_feed(self, data):
        if 'gps' in data:
            for s in data.get('gps'):
                self.rc_writer.send_timestamp(s[0])
                self.rc_writer.send_gps_speed(SensorLogger.safe_speed_to_float(s[1].get('speed')))
                self.rc_writer.send_gps_pos(s[1].get('lat'), s[1].get('lon'))

    def process_new_data(self, data):
        """
        Process dictionary of new data, change recording state if necessary
        and manage recording buffers.

        :param data: dict of sample lists from different SensorHandlers
        """
        if not data:
            return  # no-op

        # send all data to RaceCapture recorder if available
        #self.write_data_rc_feed(data)

        # if necessary, transition state
        if self.state == LoggerState.ready:
            if self.activate_conditions(data):
                # ready -> logging
                self.session_id = self.db_handler.get_new_session()
                print("New session: %s" % str(self.session_id))
                self.state = LoggerState.logging
        elif self.state == LoggerState.logging:
            if self.deactivate_conditions(data):
                # logging -> ready
                self.state = LoggerState.ready
                # populate metadata for recently ended session
                if self.session_id:
                    self.db_handler.populate_session_info(self.session_id)
                    self.session_id = None
        else:
            raise RuntimeError("Invalid logger state:" + str(self.state))

        # process data based on current state

        if self.state == LoggerState.ready:
            self.data.expire_old_samples(time.time() - 10.0)

        elif self.state == LoggerState.logging:
            # write all buffered data to the db
            # TODO: change do a single insert/transaction
            if self.db_handler:
                try:
                    self.db_handler.insert_gps_updates(self.data.get_sensor_data('gps'), self.session_id)
                    self.db_handler.insert_imu_updates(self.data.get_sensor_data('imu'), self.session_id)
                    self.db_handler.insert_can_updates(self.data.get_sensor_data('can'), self.session_id)
                except TypeError as te:
                    print("Failed to insert data: %s" % te)
            self.data.clear()

    def start(self):
        """
        Start handlers and begin recording. The function does not
        normally terminate. New sessions are created as needed.
        """
        for h in self.handlers.values():
            h.start()

        update_times = defaultdict(int)
        self.state = LoggerState.ready

        try:
            while True:
                # read new data
                new_data = self.get_new_data()
                # process data
                self.process_new_data(new_data)

                # update display
                for h in self.handlers:
                    if new_data[h]:
                        update_times[h] = new_data[h][-1][0]

                if self.display:
                    self.display.refresh_display(time.time() if self.db_handler else 0,
                                                 gps_time=update_times['gps'],
                                                 imu_time=update_times['imu'],
                                                 can_time=update_times['can'],
                                                 recording=(self.state == LoggerState.logging))

                time.sleep(0.2)  # there is no reason to ever poll faster than this
        finally:
            for h in self.handlers.values():
                h.stop()

    # def start_old(self):
    #     for h in self.handlers.values():
    #         h.start()
    #
    #     self.state = LoggerState.ready
    #     recording_active = False
    #     update_times = defaultdict(int)
    #     session_id = None
    #
    #     try:
    #         # TODO: this code makes a lot of assumptions about
    #         # what handlers are available. cleanup.
    #
    #         while True:
    #             new_data = self.get_new_data()
    #
    #             # motion is only detected via GPS speed
    #             if new_data['gps'] and self.db_handler:
    #                 is_moving = True in \
    #                             [safe_speed_to_float(s[1].get('speed')) > ACTIVATE_RECORDING_M_PER_S for s in new_data['gps']]
    #
    #                 if is_moving:
    #                     if not recording_active:  # activate recording
    #                         session_id = self.db_handler.get_new_session()
    #                         print("New session: %s" % str(session_id))
    #
    #                         # TODO: enable this
    #                         # look for last sample before car moved, clear samples before that
    #                         #gps_history = self.data.get_sensor_data('gps')
    #                         #self.data.expire_old_samples(
    #                         #    max(
    #                         #        [s[0] if s[1]['speed'] < MOVEMENT_THRESHOLD_M_PER_S else 0 for s in gps_history]
    #                         #    ))
    #                         recording_active = True
    #                 else:
    #                     if recording_active:  # deactivate recording
    #                         self.db_handler.populate_session_info(session_id)
    #                         recording_active = False
    #             if recording_active:
    #                 try:
    #                     # TODO: insert all in one call so we can do only one commit
    #                     self.db_handler.insert_gps_updates(self.data.get_sensor_data('gps'), session_id)
    #                     self.db_handler.insert_imu_updates(self.data.get_sensor_data('imu'), session_id)
    #                     self.db_handler.insert_can_updates(self.data.get_sensor_data('can'), session_id)
    #                     self.data.clear()
    #                 except TypeError as te:
    #                     print("Failed to insert data: %s" % te)
    #             else:
    #                 # clear old data in buffer
    #                 self.data.expire_old_samples(time.time() - 10.0)
    #
    #             # display update logic
    #             for h in self.handlers:
    #                 if new_data[h]:
    #                     update_times[h] = new_data[h][-1][0]
    #
    #             if self.display:
    #                 self.display.refresh_display(time.time() if self.db_handler else 0,
    #                                              gps_time=update_times['gps'],
    #                                              imu_time=update_times['imu'],
    #                                              can_time=update_times['can'],
    #                                              recording=recording_active)
    #
    #             time.sleep(0.2)  # there is no reason to ever poll faster than this
    #
    #     finally:
    #         for h in self.handlers.values():
    #             h.stop()

