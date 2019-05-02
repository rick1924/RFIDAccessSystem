# Modified by Ricardo Rivera on May 1st, 2019
#   This file uses the MFRC522-Python library created by Mario Gomez that is
#   available for download at https://github.com/mxgxw/MFRC522-python

# This program uses a RFID reader and RFID tags to authenticate a student and enable the operation of a
# machine. Each tag has written in it a unique identifier ("UID") and the user's Booked ID, all of
# which is retrieved by the RFID reader and temporarily stored in memory. The program then evaluates whether
# the tag belongs to an administrator, or the tag belongs to a user.
# First, the script checks the local administrator table, and checks whether the UID of the tag, matches any
# of the records inside the table. If the UID of the tag does not exist in the table, then it will make an API
# call to Booked, and use the Booked ID to find the information about the user. If the user has an active
# reservation at the time the tag is read, a relay then enables the machine. If the user does not have a reservation
# at that time, access will not be granted. If the tag that was read belongs to an admin, it will automatically grant
# access, no matter whether a reservation was made or not.
# Every time a user is allowed access to the machine, the script will log the UID of the user in a separate file.

# Modify all code you see written in CAPS with an underscore with your information. Be careful not to modify the SQL code that is also in caps.

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

# Function that makes an API call to our server's database, extracts the admin table, and stores it locally.
def download_admin():
    try:
        engine = create_engine("mysql+pymysql://SQL_USERNAME:SQL_PASSWORD@MYSQL_SERVER_IP_ADDRESS/YOUR_DATABASE_NAME")
        admin_table = engine.execute("SELECT * FROM YOUR_ADMIN_TABLE_NAME").fetchall()
        admin_frame = pd.DataFrame(admin_table, columns=["Name","UID","id"])
        admin_frame.to_csv("/home/pi/YOUR_PROJECT_FOLDER/AdminTags.csv", index = False)
        logging.info("The admin tag table was successfully updated")    # Creates a log entry
        print "The admin tag table was successfully updated."
    except exc.OperationalError:
        logging.info("The admin tag table could not be updated.")   # Creates a log entry
        print "The admin tag table could not be updated."

# Function that closes all communication between the Pi and the modules.
def end_read(signal, frame):
    global continue_reading
    print "Ctrl+C captured, ending read"
    continue_reading = False
    GPIO.cleanup()
    os._exit(0)

# Function that compares the time a certain user made a reservation in Booked, with the time that it is now.
def compare_times_resource_id(user_id_int, auth_headers, resource_id):
    reservations_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Reservations/"
    params = {"userId": user_id_int}
    get_reservations = requests.get(reservations_url, headers=auth_headers, params=params)  # Gets all the reservations made for a specific user.
    get_reservations_json = get_reservations.json()  # Converts into a JSON object.

    machine_id = get_reservations_json["reservations"][0]["resourceId"]

    time_a = get_reservations_json["reservations"][0]["startDate"]  # We only have to check the first entry ([0]) since Booked returns the reservations in chronological order.
    time_b = get_reservations_json["reservations"][0]["endDate"]
    year_a, month_a, day_a, hour_a, minute_a = int(time_a[0:4]), int(time_a[5:7]), int(time_a[8:10]), int(time_a[11:13]), int(time_a[14:16])
    year_b, month_b, day_b, hour_b, minute_b = int(time_b[0:4]), int(time_b[5:7]), int(time_b[8:10]), int(time_b[11:13]), int(time_b[14:16])

    allowed_minutes = 15    # We allow users to access the machine 15 minutes before their reservation time.
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
    return int(get_user_info_json["customAttributes"][0]["value"])

# The function determines whether the tag owner is a regular user or an admin.
def admin_or_user(uid_int, user_id_int):
    if (find_if_admin(uid_int) == True):
        return True
    else:
        headers = get_headers()
        if (find_booked_uid(user_id_int, headers) == uid_int and compare_times_resource_id(user_id_int, headers, resource_id) == True):
            return True

# This line says the Pi belongs to the resource with id __. Only reservations made for this machine will work with this Pi.
resource_id = "RESOURCE_ID"

# The following two lines configure the log file were all relevant information will be stored. "INFO" is used to provide good but not too detailed information.
log_filename = "/home/pi/YOUR_PROJECT_FOLDER/LogMainLoop.log"
logging.basicConfig(filename=log_filename, level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%d/%m/%Y %H:%M:%S")

# This line calls the function that downloads the admin tag table and stores it in memory.
download_admin()

# The following blocks of code prepare the I/O pins of the Raspberry Pi for the RFID Reader.
relay = 11
red_led = 12
buzzer = 13

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(relay, GPIO.OUT)
GPIO.setup(red_led, GPIO.OUT)
GPIO.setup(buzzer, GPIO.OUT)

GPIO.output(relay, GPIO.LOW)
GPIO.output(red_led, GPIO.LOW)
GPIO.output(buzzer, GPIO.LOW)

# Hook the SIGINT.
signal.signal(signal.SIGINT, end_read)

# Create an object of the class MFRC522.
MIFAREReader = MFRC522.MFRC522()

continue_reading = True

while continue_reading:

    # Scan for cards.
    (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)

    # If a card is found.
    if status == MIFAREReader.MI_OK:
        print "Card detected"

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

            # Gets the Booked User ID from the tag (of type "list"), and converts it into an integer.
            user_id_list = MIFAREReader.MFRC522_Read(8)
            MIFAREReader.MFRC522_StopCrypto1()
            user_id_int = int(''.join(str(e) for e in user_id_list))

            # Converts the uid into an integer.
            uid_int = int(''.join(str(e) for e in uid))

            try:
                if admin_or_user(uid_int, user_id_int) == True:
                    logging.info("The user with UID {} and BookedId {} has started a session".format(uid_int, user_id_int)) # Makes a log entry every time a user has been given access to the machine.
                    next_read = True
                    i = 0

                    while next_read:
                        GPIO.output(red_led, GPIO.LOW)
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
                            GPIO.output(red_led, GPIO.HIGH)
                            GPIO.output(buzzer, GPIO.HIGH)
                            time.sleep(3)       # Seconds that the buzzer remains on.
                            GPIO.output(buzzer, GPIO.LOW)
                            ii = 0
                            while critical_mode:
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
                                        time.sleep(10)
                                else:
                                    critical_mode = False
                                    next_read = False
                    GPIO.output(relay, GPIO.LOW)
                    GPIO.output(red_led, GPIO.LOW)
                else:
                    print "The time of the reservation does not match or you are not authorized to use this machine."

            except KeyError:      # Error associated with the "find_booked_uid" function. If the user is not registered in Booked.
                print "The user does not exist in Booked"
            except IndexError:     # Error associated with the "compare_reservations_time" function. If the user has no reservations then this error happens.
                print "The user does not have any active reservations for this machine."
            except TypeError:
                logging.info("There was a problem reading the BookedId of the tag.")     # Error that pops up ocasionally in the line "user_id_int".
                raise
            except requests.exceptions.ConnectionError:     # Error occurs when the Pi cannot communicate with Booked (i.e there is no wi-fi or Booked is down).
                logging.info("Communication with Booked could not be established.") # Makes a log entry for when there is no wi-fi.
                print "There is a problem with the wi-fi connection. Ask the shop personnel for admin tags."

            time.sleep(3)  # Time it takes for the reader to make another reading. Ensures the RFID module reads correctly.

        else:
            print "Authentication error"
