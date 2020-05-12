# Created by Ricardo Rivera
# Last Edit: Ricardo Rivera, August 12th 2019
# The test table is called "mechStudents"

#!/usr/bin/env python
# -*- coding: utf8 -*-
#
#    Copyright 2014,2018 Mario Gomez <mario.gomez@teubi.co>
#
#    This file is part of MFRC522-Python
#    MFRC522-Python is a simple Python implementation for
#    the MFRC522 NFC Card Reader for the Raspberry Pi.
#
#    MFRC522-Python is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    MFRC522-Python is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with MFRC522-Python.  If not, see <http://www.gnu.org/licenses/>.
# Modify all code you see written in CAPS with an underscore with your information. Be careful not to modify the SQL code that is also in caps.

import RPi.GPIO as GPIO
import MFRC522
import signal

from sqlalchemy import create_engine
from sqlalchemy.sql import text
import pandas as pd
import math
import time
import requests
import json

# Capture SIGINT for cleanup when the script is aborted.
def end_read(signal, frame):
    global continue_reading
    print ("Ctrl+C captured, ending read.")
    continue_reading = False
    GPIO.cleanup()

# The following funtion is not used in the code. It is only here for demonstration purposes
def authenticateBookedAdmin():
    authenticate_url = "http://YOUR_BOOKED_DOMAIN_NAME/Web/Services/index.php/Authentication/Authenticate"
    admin_username = "BOOKED_ADMIN_USERNAME"
    admin_password = "BOOKED_ADMIN_PASSWORD"
    arguments = {"username": admin_username, "password": admin_password}  # The variable is a dictionary or JSON
    arguments_str = json.dumps(arguments)  # Transforms arguments into a string
    authenticate_response = requests.post(authenticate_url, data=arguments_str)
    authenticate_response_json = authenticate_response.json()  # Makes the response a json object, easier to parse
    session_token = authenticate_response_json["sessionToken"]
    user_id = authenticate_response_json["userId"]
    return ({"X-Booked-SessionToken": session_token, "X-Booked-UserId": user_id})

# Creates the link to the our server's student database
engine = create_engine("mysql+pymysql://SQL_USERNAME:SQL_PASSWORD@MYSQL_SERVER_IP_ADDRESS/YOUR_DATABASE_NAME")

# Finds the students in the table that do not have an UID and creates a pandas dataframe with these.
call_to_table = engine.execute("SELECT id, GivenName, Surname, Email, BookedID, BookedUsername, TagNum FROM mechStudents WHERE UID=0 AND Registered=0").fetchall()
table = pd.DataFrame(call_to_table, columns=["id", "GivenName", "Surname", "Email", "BookedID", "BookedUsername", "TagNum"])

# Hook the SIGINT
signal.signal(signal.SIGINT, end_read)

# Create an object of the class MFRC522
MIFAREReader = MFRC522.MFRC522()

# Main loop that will figure out which students in the table do not have a UID. It will then ask to place the tag near the reader to generate the StudentToken key.
for i in table.index:
    row = table.iloc[i]
    print("Quickly tap and remove the tag {} for {} on the reader now".format(row["TagNum"],row["GivenName"]))

    continue_reading = True

    # This loop keeps checking for chips. If one is near it will get the UID and authenticate
    while continue_reading:

        # Scan for cards
        (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)

        # If a card is found
        if status == MIFAREReader.MI_OK:
            print ("Card detected")

        # Get the UID of the card
        (status, uid) = MIFAREReader.MFRC522_Anticoll()

        # If we have the UID, continue
        if status == MIFAREReader.MI_OK:

            # This is the default key for authentication
            key = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]

            # Select the scanned tag
            MIFAREReader.MFRC522_SelectTag(uid)

            # Authenticate
            status = MIFAREReader.MFRC522_Auth(MIFAREReader.PICC_AUTHENT1A, 8, key, uid)
            print ("\n")

            # Check if authenticated
            if status == MIFAREReader.MI_OK:

                # Variable for the data to write
                data = []

                # Generates the StudentToken by appending the Booked ID to the list variable. It left-pads with zeros.
                zeros = range(0, 16 - len(str(row["BookedID"])))
                for i in zeros:
                    data.append(0)
                for ii in str(row["BookedID"]):
                    data.append(int(ii))

                print ("Sector 8 looked like this:")
                # Read block 8
                MIFAREReader.MFRC522_Read(8)
                print ("\n")

                MIFAREReader.MFRC522_Write(8, data)

                print ("It now looks like this:")
                # Check to see if it was written
                MIFAREReader.MFRC522_Read(8)
                print ("\n")

                # We iterate over the list "uid" to create a number.
                uid_int = int(''.join(str(e) for e in uid))

                # Writes the tag's UID into the "mechStudents" table
                write_uid_command = text("UPDATE mechStudents SET UID = :v1 WHERE id = :v2")
                engine.execute(write_uid_command, v1=uid_int, v2=int(row["id"]))

                # The following commented block of code writes the UID corresponding to that user and tag in Booked. Commented out because
                # "UpdateBooked.py" performs the same task. It is placed here for the reader to understand the following scripts.
                    #headers = authenticateBookedAdmin()
                    #update_user_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Users/%i" % row["BookedID"]
                    #update_user_args = {"firstName": row["GivenName"], "lastName": row["Surname"], "emailAddress": row["Email"],
                    #"userName": row["BookedUsername"], "timezone": "America/Vancouver", "customAttributes": [{"attributeId": "10", "attributeValue": uid_int}]}
                    #update_user_args_str = json.dumps(update_user_args)
                    #requests.post(update_user_url, data=update_user_args_str, headers=headers)

                # Stop
                MIFAREReader.MFRC522_StopCrypto1()

                time.sleep(3)

                # Make sure to stop reading for cards
                continue_reading = False

            else:
                print ("Authentication error")
