# Modified by Ricardo Rivera on May 1st, 2019

# Modify all code you see written in CAPS with an underscore with your information. Be careful not to modify the SQL code that is also in caps.

import RPi.GPIO as GPIO
import MFRC522
import signal

from sqlalchemy import create_engine
import pandas as pd
import math
import time
#import requests
#import json

# Capture SIGINT for cleanup when the script is aborted.
def end_read(signal, frame):
    global continue_reading
    print "Ctrl+C captured, ending read."
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
call_to_table = engine.execute("SELECT id, GivenName, Surname, Email, BookedID, BookedUsername  FROM YOUR_USER_TABLE_NAME WHERE UID IS NULL").fetchall()
table = pd.DataFrame(call_to_table, columns=["id", "GivenName", "Surname", "Email", "BookedID", "BookedUsername"])

# Hook the SIGINT
signal.signal(signal.SIGINT, end_read)

# Create an object of the class MFRC522
MIFAREReader = MFRC522.MFRC522()

# Main loop that will figure out which students in the table do not have a UID. It will then ask to place the tag near the reader to generate the StudentToken key.
for i in table.index:
    row = table.iloc[i]
    print "Quickly tap and remove the tag for %s with id %i on the reader now" % (row["GivenName"], row["id"])

    continue_reading = True

    # This loop keeps checking for chips. If one is near it will get the UID and authenticate
    while continue_reading:

        # Scan for cards
        (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)

        # If a card is found
        if status == MIFAREReader.MI_OK:
            print "Card detected"

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
            print "\n"

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

                print "Sector 8 looked like this:"
                # Read block 8
                MIFAREReader.MFRC522_Read(8)
                print "\n"

                MIFAREReader.MFRC522_Write(8, data)

                print "It now looks like this:"
                # Check to see if it was written
                MIFAREReader.MFRC522_Read(8)
                print "\n"

                # We iterate over the list "uid" to create a number.
                uid_int = int(''.join(str(e) for e in uid))

                # Writes the tag's UID into the "mechStudents" table
                engine.execute("UPDATE YOUR_USER_TABLE_NAME SET UID = %i WHERE GivenName = '%s'" % (uid_int, row["GivenName"]))

                # The following commented block of code writes the UID corresponding to that user and tag in Booked. Commented out because
                # "UpdateBooked.py" performs the same task. It is placed here for the reader to understand the following scripts.
                    #headers = authenticateBookedAdmin()
                    #update_user_url = "http://ubcmechstudentmachineshop.brickhost.com/Web/Services/index.php/Users/%i" % row["BookedID"]
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
                print "Authentication error"
