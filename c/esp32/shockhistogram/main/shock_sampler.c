/*
    Copyright 2018 Donour Sizemore

    This file is part of RacePi

    RacePi is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, version 2.

    RacePi is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with RacePi.  If not, see <http://www.gnu.org/licenses/>.
*/

#include <string.h>
#include <sys/time.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_task_wdt.h"
#include "esp_log.h"
#include "driver/adc.h"
#include "shock_sampler.h"

// This code calculates histogram for shock (suspension damper) velocities by
// reading four (4) ADC channels. It samples around ~1 khz, so a large number of
// samples are collected per lap/run/session. We care about the distribution of 
// the samples, generally, and not their exact values. We expect off-by-one 
// errors in the count to be well below the noise of the system. Therefore, we 
// don't both to implement the sample counters as atomics. Given infinite time 
// We would replace all the counter increments with hardware atomic compare and 
// swap, but it just isn't needed. 

// TODO: we may want to also keep track of the sample counts when displaying results
uint64_t            histogram[CORNER_COUNT][CONFIG_NUM_HISTOGRAM_BUCKETS];
uint32_t normalized_histogram[CORNER_COUNT][CONFIG_NUM_HISTOGRAM_BUCKETS];

volatile bool recording_active = true;

static const char *LOGGER_TAG = "[shock sampler]";

static const adc_atten_t atten = ADC_ATTEN_DB_11; // full 3.9v range
static const adc_unit_t   unit = ADC_UNIT_1;
static volatile int32_t last_shock_position[CORNER_COUNT];
static int64_t last_shock_time[CORNER_COUNT];
static uint32_t sample_delay_ticks = TICKS_PER_SHOCK_SAMPLE;

static const adc_channel_t adc1_channels[] = {
  ADC1_CHANNEL_6,
  ADC1_CHANNEL_3,
  ADC1_CHANNEL_0, // unused
  ADC1_CHANNEL_5, // unused
};

static const adc2_channel_t adc2_channels[] = {
  ADC2_CHANNEL_0, // unused
  ADC2_CHANNEL_1, // unused
  ADC2_CHANNEL_8,  /*!< ADC2 channel 8 is GPIO25 */
  ADC2_CHANNEL_9  /*!< ADC2 channel 9 is GPIO26 */  
};

void zero_histogram() {
  memset(histogram, 0, (sizeof(uint64_t))*CORNER_COUNT*CONFIG_NUM_HISTOGRAM_BUCKETS);
}

// Populate normalized histogram array where buckets represent percentage of the 
// total sample count
void populate_normalized_histogram() {
  // TODO: this should take the destination object as an argument
  for (uint16_t corner = 0; corner < CORNER_COUNT; corner++) {
    // add extra sample to avoid divide by zero
    uint64_t total_samples_count = 1;
    
    for (uint16_t bucket = 0; bucket < CONFIG_NUM_HISTOGRAM_BUCKETS; bucket++) {
      total_samples_count += histogram[corner][bucket];
    }
    for (uint16_t bucket = 0; bucket < CONFIG_NUM_HISTOGRAM_BUCKETS; bucket++) {
      normalized_histogram[corner][bucket] = (uint16_t)(histogram[corner][bucket]*1000 / total_samples_count);
    }  
  }
}

void shock_histogram_init() {
  //Configure ADC
  adc1_config_width(ADC_WIDTH_BIT);
  adc1_config_channel_atten(adc1_channels[0], atten);
  adc1_config_channel_atten(adc1_channels[1], atten);
  adc2_config_channel_atten(adc2_channels[0], atten);
  adc2_config_channel_atten(adc2_channels[1], atten);

  zero_histogram();    

  if (sample_delay_ticks <= 0 ) {
    ESP_LOGE(LOGGER_TAG, "Warning: shock sampling interval is more frequent than "
	     "clock tick. Please rebuild with a higher tick frequency.");
    sample_delay_ticks = 10;
  }
}

// rate must be in mm/s
static int32_t get_bucket_from_rate(int32_t rate) {
  int16_t bucket = (int16_t)( rate + MAX_SPEED_MM_S) / HISTOGRAM_BUCKET_SIZE;
  if (bucket < 0) return  0;
  if (bucket >=  CONFIG_NUM_HISTOGRAM_BUCKETS) return CONFIG_NUM_HISTOGRAM_BUCKETS - 1;
  return bucket;
}

int32_t get_adc_value(uint16_t channel, bool adc2) {

  if (adc2) {
    // ADC shares hardware with the wifi and using a different read code path.
    int read_raw;
    esp_err_t r = adc2_get_raw(adc2_channels[channel], ADC_WIDTH_12Bit, &read_raw);
    if (r == ESP_ERR_TIMEOUT) {
      ESP_LOGE(LOGGER_TAG,"ADC2 used by Wi-Fi.\n");
    }
    return read_raw;
  } else {
    return adc1_get_raw((adc1_channel_t)adc1_channels[channel]);
  }
}

void sample_corner(uint16_t corner) {
  struct timeval tv;
  int32_t shock_velocity;
  int32_t adc_val = 0;
  
  // Read and timestamp the channel		    
  for (uint16_t sample_count = 0; sample_count < ADC_MULTISAMPLE_COUNT; sample_count++) {
    int32_t adc_raw = get_adc_value(corner, corner > 1);
#ifdef LOG_ADC_RAW
    gettimeofday(&tv, 0);
    printf("%d, %ld, %ld, %d\n", corner, tv.tv_sec, tv.tv_usec, adc_raw);
#endif
    adc_val += adc_raw;
    esp_task_wdt_reset();
  }
  adc_val /= ADC_MULTISAMPLE_COUNT;
  
  if (gettimeofday(&tv, 0) != 0) {
    ESP_LOGE(LOGGER_TAG, "Failed to read system time, aborting");
    return;
  }
  int64_t timestamp_us = (int64_t) tv.tv_usec + ((int64_t) tv.tv_sec) * 1e6;
  
  // calculate the channel rate
  int32_t count_per_second = ((adc_val - last_shock_position[corner])*1e6) / (timestamp_us - last_shock_time[corner]);
  shock_velocity = ADC_TO_MM(count_per_second);
  histogram[corner][get_bucket_from_rate(shock_velocity)]++;
  // save current readings
  last_shock_position[corner] = adc_val;
  last_shock_time[corner] = timestamp_us;
}

void log_sample_rate(const char *tag) {
  static struct timeval tv, last_tv;
  static uint32_t sample_count = 0;
  struct timeval time_diff;
  
  if (++sample_count > 1024) {
    gettimeofday(&tv, 0);
    time_diff.tv_sec  = tv.tv_sec  - last_tv.tv_sec;
    time_diff.tv_usec = tv.tv_usec - last_tv.tv_usec;
    float rate = (float)sample_count / (time_diff.tv_sec + time_diff.tv_usec * 1e-6);
    printf("rate(hz): %3.1f", rate);
    printf(" positions(mm): [");
    for (int i = 0 ; i < CORNER_COUNT; i++) {
      printf("% 3d", ADC_TO_MM(last_shock_position[i]));
    }
    printf("]\n");

    last_tv = tv;
    sample_count = 0;	
  }  
}

void sample_shock_channels(const uint8_t first_channel, const uint8_t last_channel, char *tag) {
  // subscribe to watchdog and verify
  ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
  ESP_ERROR_CHECK(esp_task_wdt_status(NULL));

  bool zero_next_iteration = false;  
  while (true) {    
    vTaskDelay(sample_delay_ticks);
    if (recording_active) {
      if (zero_next_iteration) {
	zero_histogram();
	zero_next_iteration = false;
      }
      
      for(uint16_t i = first_channel; i <= last_channel; i++) {
	sample_corner(i);
	ESP_ERROR_CHECK(esp_task_wdt_reset());
      }
      log_sample_rate(tag);
    } else {
      ESP_ERROR_CHECK(esp_task_wdt_reset());
      zero_next_iteration = true;
    }
  }
}

void get_current_shock_positions_mm(int32_t *positions) {
  for (int corner = 0 ; corner < CORNER_COUNT ; corner++) {
    positions[corner] = ADC_TO_MM(last_shock_position[corner]);
  }
}

void sample_front_channels() {
  sample_shock_channels(0, 1, "[front]");
}

void sample_rear_channels() {
  sample_shock_channels(2, 3, "[rear]");
}

