#!/usr/bin/python
import os

os.chdir("/home/pi/PiModules/code/python/package")
os.system("sudo python setup.py install")
os.chdir("/home/pi/PiModules/code/python/upspico/picofssd/")
os.system("sudo python setup.py install")
os.system("sudo systemctl enable picofssd.service")
