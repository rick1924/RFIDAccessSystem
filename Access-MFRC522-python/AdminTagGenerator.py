# Created by Ricardo Rivera
# Last Edit: Ricardo Rivera, July 12th 2019

# This program automatically creates an admin tag. The programs requests a name
# and then asks to place the tag close to the reader. Once the tag is read, the
# program communicates with the database, and adds the name of the admin, and the
# UID of the card in the "adminTokens" table.

import time

import RPi.GPIO as GPIO
import MFRC522
import signal

from sqlalchemy import create_engine
from sqlalchemy.sql import text

# Capture SIGINT for cleanup when the script is aborted.
def end_read(signal, frame):
    global continue_reading
    print ("Ctrl+C captured, ending read.")
    continue_reading = False
    GPIO.cleanup()

engine = create_engine("mysql+pymysql://SQL_USERNAME:SQL_PASSWORD@MYSQL_SERVER_IP_ADDRESS/YOUR_DATABASE_NAME")

tag_name = input("Input the name of the admin: \n")
print ("Quickly tap the admin tag on the reader")

# Hook the SIGINT
signal.signal(signal.SIGINT, end_read)

# Create an object of the class MFRC522
MIFAREReader = MFRC522.MFRC522()

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

            uid_int = int(''.join(str(e) for e in uid))

            write_admin = text("INSERT INTO adminTokens (Name,UID) VALUES (:v1, :v2)")
            engine.execute(write_admin, v1=tag_name, v2=uid_int)

            print ("The admin tag was been successfully created")

            continue_reading = False

        else:
            print ("Authentication error")
