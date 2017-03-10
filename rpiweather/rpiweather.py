#!/usr/bin/python3

import threading
import Adafruit_ADS1x15
import RPi.GPIO as GPIO
import time
from datetime import datetime
import json
import socket
import Adafruit_BMP.BMP280 as BMP280
from aosong import am2315
from os import system


class am2315_i2cfix(am2315.Sensor):
	def pi_i2c_bus_number(self):
		return 1


## Weewx
WEEWX_ADDRESS = '127.0.0.1'
WEEWX_PORT = '8888'


## GPIO
WIND_GPIO = 21
RAIN_GPIO = 20


## ADC
GAIN = 1
ADC_WIND_DIRECTION_CHANNEL = 1
adc = Adafruit_ADS1x15.ADS1115(address=0x49)


## wind
KMH_PER_TICK_SECOND = 2.4
wind_lock = threading.Semaphore()


# rain
# MM_PER_TICK = 0.2794
MM_PER_TICK = -0.2794 # disable rain by making it negative
rain_lock = threading.Semaphore()


# pressure
INHG_PER_PA = 0.0002953
bmp = BMP280.BMP280()


# humidity
am = am2315_i2cfix()


# hack to generate fake rain
from threading import Timer
rain_ticks = 0
def make_rain():
	ticks = 1
	with rain_lock:
		global rain_ticks
		rain_ticks = rain_ticks + ticks
	t = Timer(10, make_rain)
	t.start()
t = Timer(10, make_rain)
# t.start()


class DataManager(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self, daemon=True, name="DataManager")
		self.wind_ticks = 0
		self.rain_ticks = 0

		self.destination_address = WEEWX_ADDRESS
		self.destination_port = int(WEEWX_PORT)

		GPIO.setmode(GPIO.BCM)
		GPIO.setup(WIND_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP) 
		GPIO.setup(RAIN_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP) 
		GPIO.add_event_detect(WIND_GPIO, GPIO.FALLING, callback=self._gpio_callback, bouncetime=10)  
		GPIO.add_event_detect(RAIN_GPIO, GPIO.FALLING, callback=self._gpio_callback, bouncetime=10)  

	def run(self):
		self.last_wind_update = datetime.utcnow()
		self.last_rain_update = datetime.utcnow()

		while True:
			humidity = self._get_humidity()
			pressure_pa = self._get_pressure()
			temperature_c = self._get_temperature()
			enclosure_temperature_c = self._get_enclosure_temperature()

			wind_direction = self._get_wind_direction()
			wind_speed = self._get_wind_speed()
			rain_mm_per_second = self._get_rain()

			print_message = "{} wind speed: {:.1f} km/h, wind direction: {} deg, rain fall: {:.3f} mm, temperature: {} C, humidity: {}%, pressure: {:.0f} Pa, enclosure temperature: {:.2f} C".format(
				datetime.now(), wind_speed, wind_direction, rain_mm_per_second, temperature_c, humidity, pressure_pa, enclosure_temperature_c)

			print(print_message)
			system('echo {} >> /root/rpiweather.log'.format(print_message))

			observations = {}
			observations['dateTime'] = time.time()
			observations['usUnits'] = 'weewx.METRIC'
			observations['pressure'] = pressure_pa * INHG_PER_PA * 33.863881588173335 # FIXME magic number
			observations['outTemp'] = temperature_c
			observations['windSpeed'] = wind_speed
			observations['windDir'] = wind_direction
			observations['outHumidity'] = humidity
			observations['rain'] = rain_mm_per_second / 10
			observations['inTemp'] = enclosure_temperature_c

			packet = json.dumps(observations)

			sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			sock.sendto(bytes(packet, "utf-8"), (self.destination_address, self.destination_port))

			time.sleep(1)

	def _get_humidity(self):
		try:
			humidity = float(am.humidity())
		except:
			humidity = None
		return humidity

	def _get_temperature(self):
		try:
			temperature_c = float(am.temperature())
			# temperature_c = float(bmp.read_temperature())
		except Exception as e:
			print(e)
			temperature_c = None
		return temperature_c

	def _get_pressure(self):
		try:
			pressure_pa = float(bmp.read_pressure())
		except:
			pressure_pa = None
		return pressure_pa

	def _read_adc_average(self, channel, gain, averages):
		raw_adc = adc.read_adc(channel, gain=gain)
		for i in range(1, averages):
			raw_adc = raw_adc + adc.read_adc(channel, gain=gain)
		raw_adc = raw_adc / averages
		return int(round(raw_adc))

	def _get_wind_direction(self):
		try:
			raw_adc = self._read_adc_average(ADC_WIND_DIRECTION_CHANNEL, GAIN, 10)
			print("adc: {}".format(raw_adc))
			system('echo {} >> /root/adc.log'.format(raw_adc))

			# default to an invalid value if there are no matches below
			degrees = 361

			# direction in degrees : ADC reading
			# these ADC values can be refined using the data collected in /root/adc_rounded.log after a few days
			directions = {
				"112.5": 17,
				"67.5": 23,
				"90.0": 32,
				"157.5": 47,
				"135.0": 62,
				"202.5": 73,
				"180.0": 104,
				"22.5": 118,
				"45.0": 153,
				"247.5": 161,
				"225.0": 167,
				"337.5": 180,
				"0.0": 197,
				"292.5": 212,
				"270.0": 227,
				"315.0": 242,
			}

			raw_adc = int(round(raw_adc / 100))

			print("adc: {}".format(raw_adc))
			system('echo {} >> /root/adc_rounded.log'.format(raw_adc))
			for direction, adc_value in directions.items():
				if (adc_value - 5) <= raw_adc <= (adc_value + 5):
					degrees = float(direction)

		except Exception as e:
			print(e)
			degrees = None
		return degrees

	def _get_wind_speed(self):
		with wind_lock:
			now = datetime.utcnow()
			seconds = (now - self.last_wind_update).total_seconds()
			kmh = KMH_PER_TICK_SECOND * self.wind_ticks / seconds

			self.last_wind_update = datetime.utcnow()
			self.wind_ticks = 0
			return float(kmh)

	def _get_rain(self):
		with rain_lock:
			global rain_ticks
			self.rain_ticks += rain_ticks
			now = datetime.utcnow()
			seconds = (now - self.last_rain_update).total_seconds()
			mm_per_second = MM_PER_TICK * self.rain_ticks

			self.last_rain_update = datetime.utcnow()
			self.rain_ticks = 0
			rain_ticks = 0
			return float(mm_per_second)

	def _get_enclosure_temperature(self):
		try:
			temperature_c = float(bmp.read_temperature())
		except:
			temperature_c = None
		return temperature_c

	def _gpio_callback(self, channel):
		if channel == WIND_GPIO:
			with wind_lock:
				self.wind_ticks = self.wind_ticks + 1
		elif channel == RAIN_GPIO:
			with rain_lock:
				self.rain_ticks = self.rain_ticks + 1

def main():
	data_thread = DataManager()
	data_thread.start()
	data_thread.join()

if __name__ == "__main__":
	main()
