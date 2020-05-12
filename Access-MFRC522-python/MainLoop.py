# Created by Ricardo Rivera
# Last Edit: Ricardo Rivera, August 4th 2019
#   This file uses the MFRC522-Python library created by Mario Gomez that is
#   available for download at https://github.com/mxgxw/MFRC522-python

# This program uses a RFID reader and RFID tags to authenticate a student and enable the operation of a
# machine. Each tag has written in it a unique identifier "UID" and the student's Booked ID, all of
# which is retrieved by the RFID reader and temporarily stored in memory. The program then evaluates whether
# the tag belongs to an administrator, or the tag belongs to a user.
# First, the script checks the local administrator table, and checks whether the UID of the tag, matches any
# of the records inside the table. If the UID of the tag does not exist in the table, then it will make an API
# call to Booked, and use the Booked ID to find the information about the student. If the user has an active
# reservation at the time the tag is read, a relay then enables the machine. If the user does not have a reservation
# at that time, access will not be granted. If the tag that was read belongs to an admin, it will automatically grant
# access, no matter whether a reservation was made or not.
# Every time a user is allowed access to the machine, the script with log the UID of the user in a separate file.

import RPi.GPIO as GPIO
import MFRC522
import signal

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy import exc
import time
import datetime
import logging
import requests
import json
import os
import sys

import board
import busio
import adafruit_character_lcd.character_lcd_rgb_i2c as character_lcd

# Function that makes an API call to our server's database, extracts the admin table, and stores it locally.
def download_admin():
    try:
        engine = create_engine("mysql+pymysql://SQL_USERNAME:SQL_PASSWORD@MYSQL_SERVER_IP_ADDRESS/YOUR_DATABASE_NAME")
        admin_table = engine.execute("SELECT * FROM YOUR_ADMIN_TABLE_NAME").fetchall()
        admin_frame = pd.DataFrame(admin_table, columns=["Name","UID","id"])
        admin_frame.to_csv("/home/pi/YOUR_PROJECT_FOLDER/AdminTags.csv", index = False)
        logging.info("The admin tag table was successfully updated")    # Creates a log entry
        print ("The admin tag table was successfully updated.")
    except exc.OperationalError:
        logging.info("The admin tag table could not be updated.")   # Creates a log entry
        print ("The admin tag table could not be updated.")
        return False

# The following function gets the authentication headers by making a "POST" call to Booked. We will use these headers to make all successive calls.
def get_headers():
    authentication_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Authentication/Authenticate"
    admin_username = "BOOKED_ADMIN_USERNAME"
    admin_password = "BOOKED_ADMIN_PASSWORD"
    arguments = {"username": admin_username, "password": admin_password}  # A dictionary or JSON. Make sure the user specified here has admin access.
    arguments_json = json.dumps(arguments)  # Transforms http_arguments into a string.
    authenticate_response = requests.post(authentication_url, data=arguments_json)
    authenticate_response_json = authenticate_response.json()  # Makes the response a json object, easier to parse.
    session_token = authenticate_response_json["sessionToken"]
    admin_user_id = authenticate_response_json["userId"]
    return {"X-Booked-SessionToken": session_token, "X-Booked-UserId": admin_user_id}

# Function that gets the next active reservation by the given user.
def get_user_reservation(user_id_int, auth_headers):
    reservations_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Reservations/"
    params = {"userId": user_id_int}
    user_reservations = requests.get(reservations_url, headers=auth_headers, params=params)  # Gets all the reservations made for a specific user.
    user_reservations_json = user_reservations.json()  # Converts into a JSON object.
    first_reservation = user_reservations_json["reservations"][0] # We only have to check the first entry "0" since booked accommodates the reservations chronologically.
    return first_reservation

# Function that compares the time a certain user made a reservation in Booked, with the time that it is now.
def compare_times_resource_id(user_id_int, resource_id, reservation, auth_headers):
    machine_id = reservation["resourceId"]
    time_a = reservation["startDate"]
    time_b = reservation["endDate"]
    year_a, month_a, day_a, hour_a, minute_a = int(time_a[0:4]), int(time_a[5:7]), int(time_a[8:10]), int(time_a[11:13]), int(time_a[14:16])
    year_b, month_b, day_b, hour_b, minute_b = int(time_b[0:4]), int(time_b[5:7]), int(time_b[8:10]), int(time_b[11:13]), int(time_b[14:16])

    allowed_minutes = 10
    allowed_time = datetime.timedelta(minutes = allowed_minutes)
    start_datetime = datetime.datetime(year_a, month_a, day_a, hour_a, minute_a) - allowed_time
    end_datetime = datetime.datetime(year_b, month_b, day_b, hour_b, minute_b)
    now = datetime.datetime.now()

    if (start_datetime < now < end_datetime) and machine_id == resource_id:
        return True
    else:
        return False

# Function that given a UID, checks if this UID exists in the admin table stored in memory.
def find_if_admin(uid_int):
    df = pd.read_csv('/home/pi/YOUR_PROJECT_FOLDER/AdminTags.csv')
    admin_values = df["UID"]
    for i in admin_values:
        if i == uid_int:
            return True
    return False

# Function that given the BookedId of a certain tag, will find in Booked the UID of the user that corresponds to that tag.
def find_booked_uid(user_id_int, auth_headers):
    user_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Users/%s" % user_id_int
    get_user_info = requests.get(user_url, headers=auth_headers)
    get_user_info_json = get_user_info.json()
    try:
        return int(get_user_info_json["customAttributes"][0]["value"])
    except KeyError:
        return False

# The function determines the identification of the user. Whether the user is an admin, has a reservation on this machine at this particular instant, is
# registered in the systerm but does not have an active reservation, or simply the tag is not registered in the system.
def find_identification(uid_int, user_id_int, auth_headers):
    if find_booked_uid(user_id_int, auth_headers) == uid_int:
        try:
            reservation = get_user_reservation(user_id_int, auth_headers)
            if compare_times_resource_id(user_id_int, resource_id, reservation, auth_headers) == True:
                identification = confirmed_student
            else:
                identification = rejected_student
        except IndexError:
            identification = rejected_student
            reservation = {}
    else:
        reservation = {}
        if find_if_admin(uid_int) == True:
            identification = admin
        else:
            identification = unknown
    return reservation, identification

# Function that writes in Booked the time the student with a reservation first begins using the machine.
def check_in(identification, user_id_int, reservation, auth_headers):
    if identification == confirmed_student:
        ref_num =  reservation["referenceNumber"]
        checkin_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Reservations/{}/CheckIn".format(ref_num)
        requests.post(checkin_url, headers=auth_headers)

# Function that writes in Booked the time he student with a reservation leaves the machine.
def check_out(identification, user_id_int, reservation, auth_headers):
    if identification == confirmed_student:
        ref_num = reservation["referenceNumber"]
        checkout_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Reservations/{}/CheckOut".format(ref_num)
        requests.post(checkout_url, headers=auth_headers)

# Function that closes all communication between the Pi and the modules.
def end_read(signal, frame):
    global continue_reading
    print "Ctrl+C captured, ending read"
    continue_reading = False
    GPIO.cleanup()
    sys.exit(1)

# This line retrieves the resource id that the Pi belongs. It does it by finding the host name, and then removing the first two letters from this string, therefore giving
# the resource id.  Only reservations made for this machine will work with this Pi.
pi_hostname = os.uname()[1] # This command gets the hostname of the Pi. Recall that the hostname is different from the username.
resource_id = pi_hostname[2:]

# The following two lines configure the log file were all relevant information will be stored. "INFO" is used to provide good but not too detailed information.
log_filename = "/home/pi/YOUR_PROJECT_FOLDER/LogMainLoop.log"
logging.basicConfig(filename=log_filename, level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%d/%m/%Y %H:%M:%S")

# This line calls the function that downloads the admin tag table and stores it in memory.
download_admin()

# Possible identification status
unknown = 0
admin = 1
confirmed_student = 2
rejected_student = 3

# The following blocks of code prepare the I/O pins of the Raspberry Pi for the RFID Reader.
relay = 19
red_led = 16
buzzer = 26

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(relay, GPIO.OUT)
GPIO.setup(red_led, GPIO.OUT)
GPIO.setup(buzzer, GPIO.OUT)

GPIO.output(relay, GPIO.LOW)
GPIO.output(red_led, GPIO.LOW)
GPIO.output(buzzer, GPIO.LOW)

# Configures the LCD screen
lcd_columns = 16
lcd_rows = 2
i2c = busio.I2C(board.SCL, board.SDA)
lcd = character_lcd.Character_LCD_RGB_I2C(i2c, lcd_columns, lcd_rows)
lcd.color = [100, 0, 0]

# Hook the SIGINT.
signal.signal(signal.SIGINT, end_read)

# Create an object of the class MFRC522.
MIFAREReader = MFRC522.MFRC522()

continue_reading = True

while continue_reading:

        if admin_table == True:
        lcd.message = "Ready\nInsert Tag"
        GPIO.output(green_led, GPIO.HIGH)
    else:
        lcd.message = "Comm Error\nRestart Pi"
        GPIO.output(green_led, GPIO.LOW)

    # Scan for cards.
    (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)

    # If a card is found.
    if status == MIFAREReader.MI_OK:
        print ("Card detected")

    # Get the UID of the card.
    (status, uid) = MIFAREReader.MFRC522_Anticoll()

    # If we have the UID, continue.
    if status == MIFAREReader.MI_OK:

        # This is the default key for authentication.
        key = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]

        # Select the scanned tag.
        MIFAREReader.MFRC522_SelectTag(uid)

        # Authenticate
        status = MIFAREReader.MFRC522_Auth(MIFAREReader.PICC_AUTHENT1A, 8, key, uid)

        # Check if authenticated.
        if status == MIFAREReader.MI_OK:

            try:
                # Gets the Booked User ID from the tag (of type "list"), and converts it into an integer.
                user_id_list = MIFAREReader.MFRC522_Read(8)
                MIFAREReader.MFRC522_StopCrypto1()
                user_id_int = int(''.join(str(e) for e in user_id_list))

                # Converts the uid into an integer.
                uid_int = int(''.join(str(e) for e in uid))

                # Gets the administrator token that we use to authenticate API calls.
                auth_headers = get_headers()

                reservation, identification = find_identification(uid_int, user_id_int, auth_headers)

                if identification == admin or identification == confirmed_student:
                    check_in(identification, user_id_int, reservation, auth_headers)
                    logging.info("The user with UID {} and BookedId {} has started a session".format(uid_int, user_id_int)) # Makes a log entry every time a user has been given access to the machine.
                    next_read = True
                    i = 0

                    while next_read:
                        lcd.clear()
                        lcd.message = "Authenticated\nDon't Remove Tag"
                        GPIO.output(relay, GPIO.HIGH)

                        # This is the time that the Pi will take before taking another reading.
                        time.sleep(20)

                        (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
                        (status, new_uid) = MIFAREReader.MFRC522_Anticoll()
                        MIFAREReader.MFRC522_StopCrypto1()
                        if (new_uid == uid):
                            next_read = True
                            i = 0
                        elif (i < 1):
                            i += 1
                        else:
                            critical_mode = True
                            GPIO.output(buzzer, GPIO.HIGH)
                            time.sleep(3)       # Seconds that the buzzer remains on.
                            GPIO.output(buzzer, GPIO.LOW)
                            ii = 0
                            while critical_mode:
                                lcd.clear()
                                lcd.message = "Ending Session\nIn 60s"
                                time.sleep(2.5)
                                lcd.clear()
                                lcd.message = "Continue?\nReinsert Tag"
                                # Waits for 60 seconds in critical mode. If no valid tag is inserted, it goes back to initial loop.
                                if(ii <= 6):
                                    (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
                                    (status, new_uid) = MIFAREReader.MFRC522_Anticoll()
                                    MIFAREReader.MFRC522_StopCrypto1()
                                    if (new_uid == uid):
                                        critical_mode = False
                                        i = 0
                                    else:
                                        ii += 1
                                        time.sleep(5)
                                else:
                                    critical_mode = False
                                    next_read = False
                    GPIO.output(relay, GPIO.LOW)
                    check_out(identification, user_id_int, reservation, auth_headers)
                else:
                    if identification == unknown:  # When the tag is not registered in the system.
                        print ("The tag is not registered on the system")
                        lcd.clear()
                        lcd.message = "Unrecognized Tag"
                    elif identification == rejected_student: # When the user exists in our system but does not have a reservation in this machine at the time.
                        print ("Currently, the user does not have any active reservations on this machine.")
                        lcd.clear()
                        lcd.message = "No Reservations\nFound"

            except TypeError:
                logging.info("There was a problem reading the BookedId of the tag.")     # Error that pops up ocasionally in the line "user_id_int".
            except requests.exceptions.ConnectionError:     # Error occurs when the Pi cannot communicate with Booked (i.e there is no wi-fi or Booked is down).
                logging.info("Communication with Booked could not be established.") # Makes a log entry for when there is no wi-fi.
                print ("There is a problem with the wi-fi connection. Ask the shop personnel for admin tags.")
                GPIO.output(green_led, GPIO.LOW)
                lcd.clear()
                lcd.message = "No Wifi\nRestart Pi"
            except Exception:   # Logs in all other unknown errors.
                logging.exception("Unknown Error")
                raise

            time.sleep(3)  # Time it takes for the reader to make another reading. Ensures the RFID module reads correctly.
            lcd.clear()

        else:
            print ("Authentication error")
