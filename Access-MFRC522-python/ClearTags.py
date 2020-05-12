# Created by Ricardo Rivera
# Last Edit: Ricardo Rivera, June 24th 2019

import RPi.GPIO as GPIO
import MFRC522
import signal

# Capture SIGINT for cleanup when the script is aborted.
def end_read(signal, frame):
    global continue_reading
    print ("Ctrl+C captured, ending read.")
    continue_reading = False
    GPIO.cleanup()

# Hook the SIGINT
signal.signal(signal.SIGINT, end_read)

# Create an object of the class MFRC522
MIFAREReader = MFRC522.MFRC522()

continue_reading = True
# This loop keeps checking for tags.
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
                data = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]

                print ("Sector 8 looked like this:")
                # Read block 8
                MIFAREReader.MFRC522_Read(8)
                print ("\n")

                MIFAREReader.MFRC522_Write(8, data)

                print ("It now looks like this:")
                # Check to see if it was written
                MIFAREReader.MFRC522_Read(8)
                print ("\n")

                # Stop
                MIFAREReader.MFRC522_StopCrypto1()
