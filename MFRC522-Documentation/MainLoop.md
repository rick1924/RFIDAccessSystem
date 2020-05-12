# Main Loop of the Project

### Created by Ricardo Rivera
### Last Edit: Ricardo Rivera, August 5th 2019

**Note:** The following script is specifically meant to be used with Python 3.

Here, I will thoroughly explain the most relevant script in our project. This is the script that continuously reads RFID tags and evaluates if the user will be granted access to the machine. To begin understanding the program, we should know that there are two types of identifications in our project: students and admin. Students have to make an online reservation in **Booked** to have access to the machine, but admin can use the machine any time. We will use RFID tags and an RFID reader to authenticate the person wanting to use the machine and enable the operation of a machine. The RFID reader module also allows us to write to tags, the program used to do this is called "WriteToTag.py", which you can read more about in its documentation. Briefly, each tag has written in it a unique identifier (**UID**) and the student's **Booked ID**, all of which are retrieved by the RFID reader and temporarily stored in memory. The UID is a list of numbers between 8 and 15 characters long, while the Booked ID (a four digit number) is stored within a list of numbers of 16 characters long. **Note:** The tag's UID is intrinsic to each tag and cannot be changed in any way.

This program then determines whether the tag read was that of an administrator or that of a student, and depending on the thing read, consequences will follow. We begin by creating a link to the "adminTokens" database, located in our server, and download into memory the latest version of the admin table. The program then makes an API call to Booked and extracts all information about the student. These two things together help us authenticate the user. Clearly, the program relies on a wi-fi connection to authenticate users and check reservation times. Depending on whether the Raspberry Pi has internet connection or not, the program takes different paths. Therefore, I should explain these two cases separately.

---
__Wi-fi connection__: 
The program first downloads the latest version of the admin table and uses it to compare the UID of the tag read to the table entries. If there is a match, the machine activates, but if there is no match, the program uses the tag's Booked ID and retrieves the reservations done by the user. If user has no reservations, or the Booked ID does not exist, the program ends. But if there are reservations, the program compares the time it is now with the times of the reservations and checks whether the UID for that person in Booked matches the one just read. If these two are true, the machine activates.

__No wi-fi connection__:
Since the program will not be able to download the latest version of the admin table, it will use the one most recently downloaded version and compare the UID read with the table entries. If there is a match, the machine activates, but if there is no match, we run into problems. The next step would be to get the reservations for that user from Booked, but since there is no internet connection, this is not possible. Therefore, the only way to use the program if there is no internet connection is through the use of admin tags. Simply, if there is no wi-fi, the student can request an admin tag to the personnel of the machine shop.

This is the general idea behind the functioning of the script, but now let's study it in detail.

### Libraries
---
We begin by importing all the necessary libraries. Some of them should already be installed in your Raspberry Pi, but the ones who aren't can easily be installed with `pip`. The only one that has to be manually installed is "MFRC522". You can install the library by cloning the git repository [here](https://github.com/mxgxw/MFRC522-python).

```python
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
```
### Defining Functions
---
__Function 1__:
The first function we are going to declare is one that connects to the SQL database stored in our server and downloads the admin table into memory. Depending on whether the table was successfully downloaded or not, we return `True` or `False`. On the first line, we use the library called `create_engine` to establish the connection from the Pi to the server's SQL database. Once the connection has been made, we pull all records from the table that holds our admin tags. In our case, this table is called "adminTokens". The data is then stored into a `pandas` dataframe, which is immediately converted to a CSV file with the `to_csv` command and gets stored in the Pi's memory. In a log file, which we will configure later, we record whether the operation was successful or not.

```python
def download_admin():
    try:
        engine = create_engine("mysql+pymysql://SQL_USERNAME:SQL_PASSWORD@MYSQL_SERVER_IP_ADDRESS/YOUR_DATABASE_NAME")
        admin_table = engine.execute("SELECT * FROM adminTokens").fetchall()
        admin_frame = pd.DataFrame(admin_table, columns=["Name","UID","id"])
        admin_frame.to_csv("/home/pi/YOUR_PROJECT_FOLDER/AdminTags.csv", index = False)
        logging.info("The admin tag table was successfully updated")
        print ("The admin tag table was successfully updated.")
        return True
    except exc.OperationalError:
        logging.info("The admin tag table could not be updated.")
        print ("The admin tag table could not be updated.")
        return False
```

__Function 2__:
The function prepares the URL necessary to make the calls to authenticate the admin user. This admin user will make all further calls to check other user information and reservations. Briefly, the code makes an API call of type "POST" to "Booked" taking as arguments the admin's username and password. If the user is successfully verified, the JSON response will include a "sessionToken" and the Booked "userId", which we return as a dictionary. This dictionary, which we will later call "auth_header", will serve as argument for all further calls.

**Note:** This header expires after a certain amount of time, and therefore it is essential that we get a new header every time a new student wants to access the machine. This may not be relevant for the performance of the function, but the location of the function inside the main code has great consequences.

**Note:** Make sure that the key names for the "headers" variable are exactly named `X-Booked-SessionToken` and `X-Booked-UserId`.

```python
def get_headers():
    authentication_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Authentication/Authenticate"
    admin_username = "ADMIN_BOOKED_USERNAME"
    admin_password = "ADMIN_BOOKED_PASSWORD"
    arguments = {"username": admin_username, "password": admin_password}  # A dictionary or JSON. Make sure the user specified here has admin access.
    arguments_json = json.dumps(arguments)  # Transforms http_arguments into a string
    authenticate_response = requests.post(authentication_url, data=arguments_json)
    authenticate_response_json = authenticate_response.json()  # Makes the response a JSON object. Easier to parse.
    session_token = authenticate_response_json["sessionToken"]
    admin_user_id = authenticate_response_json["userId"]
    return {"X-Booked-SessionToken": session_token, "X-Booked-UserId": admin_user_id} # "Header"
```

__Function 3__:
The following function gets all future reservations made by the given user, from which it only selects the next active reservation for later use. Similar to Function 2, we write the URL for the API call, and create a dictionary in which we will store the Booked ID of the user. We the make a "GET" request to the URL while passing the Booked ID and the authorization headers to the function. This will give us a list containing all the reservations sorted in chronological order made by the user. Since the list is organized chronologically, we only select the first active reservation, that with the index 0.

```python
def get_user_reservation(user_id_int, auth_headers):
    reservations_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Reservations/"
    params = {"userId": user_id_int}
    user_reservations = requests.get(reservations_url, headers=auth_headers, params=params)  # The response contains all reservations made for the given user.
    user_reservations_json = user_reservations.json()  # Converts into a JSON object.
    first_reservation = user_reservations_json["reservations"][0]
    return first_reservation
```

__Function 4__:
Here, we compare the time of the student's reservation with the current time, and the **resource ID** of the machine where the student made the reservation with the resource ID of this Pi. The function takes the user's Booked ID, the resource ID, the user's next active reservation, and the admin authentication headers as arguments. The resource ID is a number Booked sets to each machine. Each Pi corresponds to one machine, and so we hardcode the resource ID of that specific machine into this script. This will allow us to only grant access to the users who have made a reservation for this specific machine. **Note:** We can find the resource ID of each machine by making an API call to Booked (not covered here).

To recap, the user's next active reservation will be provided by the function above, while the Booked administrator headers will be provided by Function 2. The remaining arguments will be found on the main section of the code. The function takes the next active reservation and finds three relevant pieces of information we care about: the resource ID where the reservation was made (`resourceId`),  the reservation's starting date/time (`startDate`), and the finishing date/time (`endDate`). The fields "startDate/endDate" are strings and therefore hard to evaluate and perform operations on; as a solution we cut them into smaller pieces and make them an object of the class "datetime". For our project, we do not want the reservation times to be strictly enforced, so we will allow students to be able to use the machines 10 minutes prior to their start time. We can achieve this by using the `datetime.timedelta()` function, and subtracting it to the `start_datetime` variable. This class also gives us the current date and time with the line `datetime.datetime.now()`. Now that we have the machine's resource ID where the user made the reservation, and the start/end times of the reservation, we can finally evaluate if the student is asking access to the correct machine and is within the time of reservation.

```python
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
```

__Function 5__:
The function checks if the tag read is an admin tag. To do so, it compares the UID of the tag to the entries in the administrator table. The function uses the library called "pandas" to open the CSV file and stores it into a dataframe. We can think of a dataframe as an excel spreadsheet. The function then scans all elements of the column `UID` and compares them with the UID read. If there is a match, the function returns the value "True", but if there is no match, then returns "False". **Note:** Make sure the admin table is stored in the same directory as your "MainLoop.py" script.

```python
def find_if_admin(uid_int):
    df = pd.read_csv('/home/pi/YOUR_PROJECT_FOLDER/AdminTags.csv')
    admin_values = df["UID"]
    for i in admin_values:
        if i == uid_int:
            return True
    return False
```

__Function 6__:
This function looks in Booked for the UID associated with the student who tapped the tag. If this UID and the one of the physical tag match, the first step of verification succeeds. The function takes as argument the student's Booked ID and uses it to make an API call to Booked and obtain information about this student. Specifically, this function seeks the UID of the student, which is stored in the "customAttributes" field. However, since it is possible that ID read is not one registered in the system, then `get_user_info_json` will be empty and if we try to access is "customAttributes" we will get an error. For this reason, we use a try block so the program does not crash in case this happen. If we do find the UID of the user, we convert it into a string.

```python
def find_booked_uid(user_id_int, auth_headers):
    user_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Users/%s" % user_id_int
    get_user_info = requests.get(user_url, headers=auth_headers)
    get_user_info_json = get_user_info.json()
    try:
        return int(get_user_info_json["customAttributes"][0]["value"])
    except KeyError:
        return False
```

__Function 7__:
The next function determines the identification of the user whose tag was tapped. It takes as arguments the UID and Booked ID provided in the tag, as well as the authentication headers. The user's identification has four possible values, which we find by testing each scenario. Let's analyze each case individually. First, we call `find_booked_uid` to find the UID stored in Booked for the given Booked and checks if the UID of the tag and the one found in Booked match.

If the UID on the tag and the one found in Booked for that user match, we then check whether the user has any reservations in the system.
  1.  If the user has a reservation, we then compare the time of the reservation made, and the time it is now by calling the function `compare_times_resource_id`. If these times match, and the resource id and machine id also match, we allow the student access to the machine and save their reservation for future reference.
  2. If the times, or the resource and machine id do not match, we then reject the user, meaning that they do not have a reservation at this hour or they do have one but just not in this machine.
  3. If the user does not have any future reservations, the function `get_user_reservation` would make the program crash. As a solution, we use the try block to prevent it from crashing, and we just simply reject the user. We assign an empty dictionary to the reservation variable.
What if the Booked ID read in the tag is not in the system? The following two cases are a consequence of this.
  4. We use the `find_if_admin` to check if the tag belongs to an admin. If it does we save the identification.
  5. Since the tag did not belong to a student or to an admin, and there are no other possible identifications, we say that the tag is unknown.

For cases 4 and 5, we also assign empty dictionaries to the reservation variable. Every status possible should have a reservation variable associated with it since the function returns the user reservation as well as their identification.

**Extra:** This paragraph shows with more detail what would happen inside the functions that could make the program crash, and how we fix it. What if there was no Booked ID associated with the tag read, and functions `find_booked_id` and `compare_times_resource_id` were called? The response Booked gives when the user does not exist or when the user has no reservations during the next two weeks, is `{'reservations': [], 'endDateTime': None, 'links': [], 'startDateTime': None, 'message': None}`. Then, the line `int(get_user_info_json["customAttributes"][0]["value"])` in Function 6 would have no value "customAttributes", and so we would get a `KeyError`. Also, in Function 4, the line  `get_reservations_json["reservations"][0]["startDate"]` would have no index "0", giving us an `IndexError`. To prevent the code from crashing if this scenario happens, we will later on add a try/catch block.

```python
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
```

__Function 8__:
The function below takes as argument the identification of the user, and evaluates if its a student with an active reservation. If true, it then gets the student's next reservation reference number and uses it to create an entry in Booked containing the current time of the system.

```python
def check_in(identification, user_id_int, reservation, auth_headers):
    if identification == confirmed_student:
        ref_num =  reservation["referenceNumber"]
        checkin_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Reservations/{}/CheckIn".format(ref_num)
        requests.post(checkin_url, headers=auth_headers)
```

__Function 9__:
Similar to the function above, this function writes in Booked the time the user stops using the machine.

```python
def check_out(identification, user_id_int, reservation, auth_headers):
    if identification == confirmed_student:
        ref_num = reservation["referenceNumber"]
        checkout_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Reservations/{}/CheckOut".format(ref_num)
        requests.post(checkout_url, headers=auth_headers)
```

__Function 10__:
The following function is one that the creator of the "MFRC522-Python" library, Mario Gomez, has made. We add a couple of lines at the end to ensure that all communication between the RFID reader and the LCD display closes properly in the case the program crashes or there is a keyboard interrupt.

```python
def end_read(signal, frame):
    global continue_reading
    print ("Ctrl+C captured, ending read")
    continue_reading = False
    lcd.clear()
    GPIO.cleanup()
    sys.exit(1)
```

### Initializing
---
In the first two lines below, we retrieve the resource id that the Pi belongs. Recall that the resource id is found in the pi's hostname as we put it with PiBakery. The hostname should be something like "pi267". Then we find the Pi's hostname and store it into the variable  `pi_username`, which we then remove the first two letters from this string, resulting in the integer or resource id. On the next two lines, we configure the log file using the library `logging`. We ask the program to name the file "LogMainLoop.log", to write the date and time of events, and allow us to include a message with each event. Notice that the function contains an argument called "level", which determines how important the event has to be in order to be logged into the file. You can read more about these levels [here](https://docs.python.org/3/library/logging.html). Briefly, the setting `logging.INFO` will allow us to have detailed logs with descriptions of the errors, warnings, and information messages we will get during the program. In the last line, we call the function that downloads the admin tag table and saves it into the Pi's memory. The variable `admin_table` becomes true if the table downloaded successfully, and false if it wasn't.

```python
pi_username = os.uname()[1] # This command gets the hostname of the Pi. Recall that the hostname is different from the username.
resource_id = pi_username[2:]

log_filename = "/home/pi/YOUR_PROJECT_FOLDER/LogMainLoop.log"
logging.basicConfig(filename=log_filename, level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%d/%m/%Y %H:%M:%S")

admin_table = download_admin()
```

Below, we assign numerical values to the possible identification status we declared on Function 7.

```python
unknown = 0
admin = 1
confirmed_student = 2
rejected_student = 3
```

The following block of code configures the I/O pins of the Raspberry Pi that will control the relay, buzzer, and green LED. The line `GPIO.setmode(GPIO.BCM)` tells Python which of the two possible pin layouts we are going to use. Click [here](https://raspberrypi.stackexchange.com/questions/12966/what-is-the-difference-between-board-and-bcm-for-gpio-pin-numbering) two learn more about these layouts. The last three lines make sure that there is no current flowing through those pins.

```python
relay = 19
red_led = 16
buzzer = 26

GPIO.setmode(GPIO.BOARD)
GPIO.setup(relay, GPIO.OUT)
GPIO.setup(red_led, GPIO.OUT)
GPIO.setup(buzzer, GPIO.OUT)

GPIO.output(relay, GPIO.LOW)
GPIO.output(red_led, GPIO.LOW)
GPIO.output(buzzer, GPIO.LOW)
```

Next, we configure the LCD display on the first two lines, telling it the number of columns and rows that our LCD display has. Then we initialize the I2C communication between the Pi and the display.

```python
lcd_columns = 16
lcd_rows = 2
i2c = busio.I2C(board.SCL, board.SDA)
lcd = character_lcd.Character_LCD_RGB_I2C(i2c, lcd_columns, lcd_rows)
```

Before we get to the main loop of the program, there are three more small things to do. We have to initialize the termination signal, initialize the RFID reader, and set the `continue_reading` variable to always be true. We will use this variable to keep the loop constantly running and scanning for tags.

```python
signal.signal(signal.SIGINT, end_read)
MIFAREReader = MFRC522.MFRC522()
continue_reading = True
```
### Reading Tags
---
From here until the end of this document, I will be using portions of the python script "Read.py" that comes with the MFRC522 library that I mentioned at the beginning of the document. Some of the comments are the original ones by Mario Gomez.

This is where the main section of the script begins. We begin by creating a "while" loop, and everything that follows in this document goes inside this loop.

```python
while continue_reading:
    ...
    ...
```

Inside the loop, we first check the value stored in `admin_table` which was referenced above. If true, we display the message `Ready`, but if this value is false, then this could mean that there is no internet connection or there is a problem in the communication to the database. In this case we we suggest the user to reboot the machine.

```python
if admin_table == True:
    lcd.message = "Ready\nInsert Tag"
    GPIO.output(green_led, GPIO.HIGH)
else:
    lcd.message = "Comm Error\nRestart Pi"
    GPIO.output(green_led, GPIO.LOW)
```

Inside the loop, we begin by scanning for tags and checking for any physical error or alteration of these tags. If there is a a problem with the tag, the script will print "Authentication Error". The meaning of each line, with the help of the comment, is self-explanatory. **Note:** The line that contains the variable "key" is of no relevance to us, but it should still be placed there.

```python
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

        # Check if authenticated
        if status == MIFAREReader.MI_OK:
            ...
            ...
            ...
            ...
        else:
            print "Authentication error"
```
### Try Block
---
Everything that follows in this document goes inside the last if statement as shown above. Before going any further, we have to create a try/catch block to prevent the code from crashing in the event of some error created by the functions inside. We've seen some try blocks on the beginning of the document, however those errors were all relevant to find the identification of the user. In contrast, these are general errors. The first error we could encounter is `requests.exceptions.ConnectionError`, which triggers when there is no wi-fi connection and so the admin tag table could not be downloaded from the server. We make a log of it. **Note:** This last error is not intrinsic of Python, rather it is produced by the library `requests`.

Besides the one above, there are no other errors we think could show up, but sometimes it is still worth to log any other error that may appear just so we are aware that something wrong happened. The exception `Exception` handles all other errors. It is recommended that when one of these errors happen, we do not continue running the script, but make it stop. Before stopping the program completely with the `raise` command, we will first make a log of it.

```python
try:
    ...
    ...
    ...
    ...
except requests.exceptions.ConnectionError:    
    logging.info("Communication with Booked could not be established.") # Makes a log entry for when there is no wi-fi.
    print ("There is a problem with the wi-fi connection. Ask the shop personnel for admin tags.")
    GPIO.output(green_led, GPIO.LOW)
    lcd.clear()
    lcd.message = "No Wifi\nRestart Pi"
except Exception:   # Logs in all other unknown errors.
    logging.exception("Unknown Error")
    raise
```

Now that we have handled all errors that could appear within the program, we proceed to develop the main routine. First, we extract the tag's UID, and we then read the Booked ID and store the 16 characters long list into memory. Because the UID and Booked ID are both lists of characters (each field is a string), we have to convert them into a form that is useful to us. To do this, we iterate over the UID and Booked ID, and explicitly cast the string of characters into integers. On the last line, we get the authorization tokens to make all further call to Booked.

```python
user_id_list = MIFAREReader.MFRC522_Read(8)
MIFAREReader.MFRC522_StopCrypto1()    # Closes the connection between the tag and the reader
user_id_int = int(''.join(str(e) for e in user_id_list))
uid_int = int(''.join(str(e) for e in uid))

auth_headers = get_headers()
```
### Authentication
---
On the line below we use the function `find_identification` to find the user's next reservation, if any, as well as their identification. As I have mentioned before, there are only two cases in which we allow the user access to the machine. This is when the tad belongs to an admin, or the student has an active reservation on this machine at this particular moment. Therefore, we use an "if" statement to evaluate if the identification of the user is any of the two. If they are, we allow them in. However, if they are any of the other cases, we do not grant access and print messages on the LCD screen for them to see.

```python
reservation, identification = find_identification(uid_int, user_id_int, auth_headers)

if identification == admin or identification == confirmed_student:
    check_in(identification, user_id_int, reservation, auth_headers)
    logging.info("The user with UID {} and BookedId {} has started a session".format(uid_int, user_id_int))
    ...
    ...
    ...
else:
  if identification == unknown:  # When the tag is not registered in the system.
      print ("The tag is not registered on the system")
      lcd.clear()
      lcd.message = "Unrecognized Tag"
  elif identification == rejected_student: # When the user exists in our system but does not have a reservation in this machine at the time.
      print ("Currently, the user does not have any active reservations on this machine.")
      lcd.clear()
      lcd.message = "No Reservations\nFound"
```

In the block below, we begin by declaring a variable that will run/exit the following `while` loop, followed by another variable which we will use as a counter later on. The loop begins by putting a message into the LCD display, and turning on the relay giving power to the machine. The Pi will then wait for 20 seconds before scanning for the tag again and registering the tag's UID. The last two lines indicate that when we do not want to continue reading for that tag, or the user has left the machine, it will turn off the relay and write the time of check out in Booked.
Everything that follows in this document is placed inside the `while` loop.

```python
next_read = True
i=0

while next_read:
    lcd.clear()
    lcd.message = "Authenticated\nDon't Remove Tag"
    GPIO.output(relay, GPIO.HIGH)

    time.sleep(20)

    (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
    (status, new_uid) = MIFAREReader.MFRC522_Anticoll()
    MIFAREReader.MFRC522_StopCrypto1()
    ...
    ...
    ...
GPIO.output(relay, GPIO.LOW)
check_out(identification, user_id_int, reservation, auth_headers)
```

If the UID of the tag that was scanned in the block of code above remains the same, then the variable `next_read` and `i` will remain unchanged. If the reader did not detect a new UID or if the UID of the tag just read is different than the one with which the session was started, we check if `i < 1`. If the statement is true, then we just add one to the counter, if false, the program goes into `critical mode`, which I will explain on detail in the next block.

Why does the cycle have to repeat two times before going into critical mode? If it does not detect a UID the first time, why not go directly into critical mode? The reason why we have to go through two cycles is because of a bug or reading error. We found that when the RFID reader reads the tag for the first time, it processes it correctly, but if the tag remains in place, the next reading will fail. And twenty seconds after it fails, it will again read it correctly, and so on. In other words, what this block of code does, is that it waits two cycles of not reading the tag or reading different UIDs before going into critical mode.

Everything that follows in this document, will take place inside the `else` statement.

```python
if (new_uid == uid):
    next_read = True
    i = 0
elif (i < 1):
    i += 1
else:
  critical_mode = True
  ...
  ...
```

When the Pi goes into critical mode the buzzer will emit a sound for three seconds before turning off again. The purpose of the buzzer is that of alerting the user to place the tag near the reader, or the machine will shutdown. We then initialize another counter `ii` which we will use in the next section. Inside the "while" loop we will show a changing message telling the user the state of the system, as well as some instructions.

```python
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
```

To finalize, the block below explains that while in critical mode, there will be a scan every ten seconds for one minute. If the initial tag is placed before the minute expires, the system will go back to normal. Back in the normal state, the buzzer will be off, and the readings will happen every 20 seconds. "Normal" state begins in the line `while next_read` three blocks of code above. However, if the tag is not placed by the end of the minute, the line `next_read = False` will terminate the current session turning off the relay.

```python
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
```
