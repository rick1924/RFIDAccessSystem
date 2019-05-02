# Main Loop of the Project

### Edited by Ricardo Rivera, March 14th 2019

**Note:** The following script is specifically meant to be used with Python 2.7.

This program then determines whether the tag read was that of an administrator or that of a regular user, and depending on the thing read, some consequences will follow. We begin by creating a link to the "adminTokens" database, located in our server, and download into memory the latest version of the admin table. The program then makes an API call to Booked and extracts all information about the user. These two things together help us authenticate the user. Clearly, the program relies on a wi-fi connection to authenticate users and check reservation times. Depending on whether the Raspberry Pi has internet connection or not, the program takes different paths. Therefore, I will explain these two cases separately.

---
__Wi-fi connection__: 
The program first downloads the latest version of the admin table and uses it to compare the UID of the tag read to the table entries. If there is a match, the machine activates, but if there is no match, the program uses the tag's Booked ID and retrieves the reservations done by the user. If the user has no reservations, or the Booked ID does not exist, the program ends. But if there are reservations, the program compares the time it is now with the times of the reservations and checks whether the UID for that person in Booked matches the one just read. If these two are true, the machine activates.

__No wi-fi connection__:
Since the program will not be able to download the latest version of the admin table, it will use the one most recently downloaded version and compare the UID read with the table entries. If there is a match, the machine activates, but if there is no match, we run into problems. The next step would be to get the reservations for that user from Booked, but since there is no internet connection, this is not possible. Therefore, the only way to use the program if there is no internet connection, is through the use of admin tags. Simply, if there is no wi-fi, the student can request an admin tag to the administrative personnel.

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
```
### Defining Functions
---
__Function 1__:
The function prepares the URL necessary to make the calls to authenticate the admin user. This admin user will make all further calls to check other user information and reservations. Briefly, the code makes an API call of type "POST" to "Booked" taking as arguments the admin's username and password. If the user is successfully verified, the JSON response will include a "sessionToken" and the Booked "userId", which we return as a dictionary. This dictionary, which we will later call "header", will serve as argument for all further calls.
The header expires after a certain amount of time, and therefore it is essential that we get a new header every time a new student wants to access the machine. This may not be relevant for the performance of the function, but the location of the function inside the main code has great consequences.

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

__Function 2__:
This function connects to the SQL database stored in our server. Once the connection has been made, we pull all records from the table that holds our admin tags. In our case, this table is called "adminTokens". The data is then stored into a "pandas dataframe", which is immediately converted to a CSV file and gets stored in the Pi's memory. We can think of a dataframe as an excel spreadsheet with rows and columns where we can store data. In a log file, we then record whether the operation was successful or not. We will configure this file later in the script.

```python
def download_admin():
    try:
        engine = create_engine("mysql+pymysql://SQL_USERNAME:SQL_PASSWORD@MYSQL_SERVER_IP_ADDRESS/YOUR_DATABASE_NAME")
        admin_table = engine.execute("SELECT * FROM YOUR_ADMIN_TABLE_NAME").fetchall()
        admin_frame = pd.DataFrame(admin_table, columns=["Name","UID","id"])
        admin_frame.to_csv("/home/pi/YOUR_PROJECT_FOLDER/AdminTags.csv", index = False)
        logging.info("The admin tag table was successfully updated")
        print "The admin tag table was successfully updated."
    except exc.OperationalError:
        logging.info("The admin tag table could not be updated.")
```

__Function 3__:
The first function we are going to use is one that the creator of the "MFRC522-Python" library, Mario Gomez, has made. The only modification we are going to make is to add the line `os._exit(0)`, that ensures that all communication between the Pi and the RFID reader closes properly in the case the program crashes or there is a keyboard interrupt.

```python
def end_read(signal, frame):
    global continue_reading
    print "Ctrl+C captured, ending read"
    continue_reading = False
    GPIO.cleanup()
    os_exit(0)
```

__Function 4__:
Here, we compare the time of the student's reservation with the current time, and the **resource ID** of the machine where the user made the reservation with the resource ID of this Pi. The function takes the user's Booked ID, the admin authentication headers, and the resource ID of the Pi as arguments. Each Pi corresponds to one resource, and so we hardcode the resource ID of that specific machine into this script. This will allow us to only grant access to the users who have made a reservation for this specific machine. **Note:** We can find the resource ID of each machine by making an API call to Booked whose syntax you can find by typing "http://YOUR_BOOKED_DOMAIN/Web/Services" into your browser.

The Booked administrator headers will be provided by Function 1, and the Booked ID will be obtained by scanning the tag with the RFID reader. The function makes an API call to Booked in order to get the reservations made by that user. If the user has made several reservations for the week, the reservations are given to us in chronological order. This is helpful, because it means we only have to check the times for the first reservation (index 0). The response is converted into JSON format and then parsed or split, which allows us to read the data better. The three pieces of information that we care about from this response are the machine's resource ID,  reservation's starting date/time (`startDate`), and the finishing date/time (`endDate`). The fields "startDate/endDate" are strings, and therefore hard to evaluate and perform operations on; as a solution, we cut them into smaller pieces and make them an object of the class "datetime". For our project, we do not want the reservation times to be strictly enforced, so we will allow users to be able to use the machines 15 minutes prior to their start time. We can achieve this by using the `datetime.timedelta()` function, and subtracting it to the `start_datetime` variable. This class also gives us the current date and time with the line `datetime.datetime.now()`. Now that we have the machine's resource ID where the user made the reservation, and the start/end times of the reservation, we can finally evaluate if the user is asking access to the correct machine and is within the time of their reservation.

```python
def compare_times_resource_id(user_id_int, auth_headers, resource_id):
    reservations_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Reservations/"
    params = {"userId": user_id_int}
    get_reservations = requests.get(reservations_url, headers=auth_headers, params=params)  # Gets all the reservations made for a specific user.
    get_reservations_json = get_reservations.json()  # Converts into a JSON object.

    machine_id = get_reservations_json["reservations"][0]["resourceId"]

    time_a = get_reservations_json["reservations"][0]["startDate"]  # We only have to check the first entry "0" since booked accommodates the reservations chronologically.
    time_b = get_reservations_json["reservations"][0]["endDate"]
    year_a, month_a, day_a, hour_a, minute_a = int(time_a[0:4]), int(time_a[5:7]), int(time_a[8:10]), int(time_a[11:13]), int(time_a[14:16])
    year_b, month_b, day_b, hour_b, minute_b = int(time_b[0:4]), int(time_b[5:7]), int(time_b[8:10]), int(time_b[11:13]), int(time_b[14:16])

    allowed_minutes = 15
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
The function checks if the tag read is an admin tag. To do so, it compares the UID of the tag to the entries in the administrator table. The function uses the library called "pandas" to open the CSV file and stores it into a dataframe. The function then scans all elements of the column `UID` and compares them with the UID read. If there is a match, the function returns the value "True", but if there is no match, then returns "False". **Note:** Make sure the admin table is stored in the same directory as your "MainLoop.py" script.

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
This function looks in Booked for the UID associated with the user who tapped the tag. If this UID and the one of the physical tag match, the first step of verification succeeds. The function takes as argument the user's Booked ID and uses it to make an API call to Booked and obtain information about this user. Specifically, this function seeks the UID of the student, which is stored in the "customAttributes" field. Since the UID is stored as a string, for reasons we will soon see, we convert it into an integer.

```python
def find_booked_uid(user_id_int, auth_headers):
    user_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Users/%s" % user_id_int
    get_user_info = requests.get(user_url, headers=auth_headers)
    get_user_info_json = get_user_info.json()
    return int(get_user_info_json["customAttributes"][0]["value"])
```

__Function 7__:
The next function determines whether the tag belong to a normal user with a reservation or an admin. It takes as arguments the UID and Booked ID provided in the tag, and uses them to make calls to other functions. This function uses three of the functions we have defined above. First, it calls `find_if_admin` to find if the tag read belongs to an admin. If the tag does not belong to an admin, then it uses the Booked ID of the tag to make a call to the functions `find_booked_uid` and `compare_times_resource_id`, which together authenticate a user and the time of reservation in order to grant access to the machine.

What would happen if the user was not admin, and the tag had no Booked ID associated with it? In other words, what if there was no Booked ID associated with the tag read, and functions `find_booked_id` and `compare_times_resource_id` were called? The program would crash. The response Booked gives when the user does not exist or when the user has no reservations during the next two weeks, is `{'reservations': [], 'endDateTime': None, 'links': [], 'startDateTime': None, 'message': None}`. Then, the line `int(get_user_info_json["customAttributes"][0]["value"])` in Function 6 would have no value "customAttributes", and so we would get a `KeyError`. Also, in Function 4, the line  `get_reservations_json["reservations"][0]["startDate"]` would have no index "0", giving us an `IndexError`. To prevent the code from crashing if this scenario happens, we will later on add a try/catch block.

```python
def admin_or_user(uid_int, user_id_int):
    if (find_if_admin(uid_int) == True):
        return True
    else:
        headers = get_headers()
        if (find_booked_uid(user_id_int, headers) == uid_int and compare_times_resource_id(user_id_int, headers, resource_id) == True):
            return True
```
### Initializing
---

In the first line of the code below, we declare the variable that holds the resource ID of the machine where this Pi is placed. On the next two lines, we configure the log file using the library "logging". We ask the program to name the file "LogMainLoop.log", to write the date and time of events, and allow us to include a message with each event. Notice that the function contains an argument called "level", which determines how important the event has to be in order to be logged into the file. You can read more about these levels [here](https://docs.python.org/3/library/logging.html). Briefly, the setting `logging.INFO` will allow us to have detailed logs with descriptions of the errors, warnings, and information messages we will get during the program. In the last line, we call the function that downloads the admin tag table and saves it into the Pi's memory.

```python
resource_id = "RESOURCE_ID"

log_filename = "/home/pi/YOUR_PROJECT_FOLDER/LogMainLoop.log"
logging.basicConfig(filename=log_filename, level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%d/%m/%Y %H:%M:%S")

download_admin()
```

The following block of code configures the I/O pins of the Raspberry Pi that will control the relay, buzzer, and red LED. The line `GPIO.setmode(GPIO.BOARD)` tells Python which of the two possible pin layouts we are going to use. Click [here](https://raspberrypi.stackexchange.com/questions/12966/what-is-the-difference-between-board-and-bcm-for-gpio-pin-numbering) two learn more about these layouts. The last three lines make sure that there is no current flowing through those pins.

```python
relay = 11
red_led = 12
buzzer = 13

GPIO.setmode(GPIO.BOARD)
GPIO.setup(relay, GPIO.OUT)
GPIO.setup(red_led, GPIO.OUT)
GPIO.setup(buzzer, GPIO.OUT)

GPIO.output(relay, GPIO.LOW)
GPIO.output(red_led, GPIO.LOW)
GPIO.output(buzzer, GPIO.LOW)
```

Before we get to the main loop of the program, there is three more smaller things to do. That is to initialize the termination signal, initialize the RFID reader, and to set a variable to always be true. We will use this variable to keep the loop constantly running and scanning for tags.

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

Everything that follows in this document goes inside the last if statement as shown above. Now that we have extracted the tag's UID, we then read the Booked ID and store the 16 characters long list into memory. Because the UID and Booked ID are both lists of characters (each field is a string), we have to convert them into a form that is useful to us. To do this, we iterate over the UID and Booked ID, and explicitly cast the strings into integers.

```python
user_id_list = MIFAREReader.MFRC522_Read(8)
MIFAREReader.MFRC522_StopCrypto1()    # Closes the connection between the tag and the reader
user_id_int = int(''.join(str(e) for e in user_id_list))
uid_int = int(''.join(str(e) for e in uid))
```
### Try Block
---
Before going any further, we have to create a try/catch block to prevent the code from crashing in the event of some error created by the functions inside. The functions that could produce such errors are: find_booked_uid, compare_reservation_times, and download_admin. The first error we can get is of type `KeyError` which appears when the user's tag has no associated Booked ID or the Booked ID no longer exists in the current version of Booked. The second error we can get is of type `IndexError` which happens when the user has no upcoming reservations for the next two weeks. The last error, we could find is `requests.exceptions.ConnectionError`, which implies that there is no wi-fi connection and so the admin tag table could not be downloaded. For the first two errors, we only want to display a message on screen; however, with the last error we want to create a log entry of it. **Note:** This last error is not intrinsic of Python, rather it is produced by the library `requests`, and so it requires special syntax.

Everything that follows in this document goes inside this try/catch block.

```python
try:
    ...
    ...
    ...
    ...
except KeyError:
    print "The user does not exist in Booked"
except IndexError:
    print "The user does not have any active reservations"
except requests.exceptions.ConnectionError:    
    logging.info("Communication with Booked could not be established.")
    print "There is a problem with the wi-fi connection. Ask the shop personnel for admin tags."
```
### Authentication
---
Right after the try block in the last section, we are going to place the verification functions that will tell us whether the tag belongs to admin, a user with a reservation, or neither of these. Here, we call the function that determines if the tag belongs to an admin or a user with a reservation. If the tag belongs to one of the two, the if statement evaluates to true and we proceed to start a session. The session will remain open until the reservation time ends or the tag is taken away from the reader for over a minute. When the session has just started, the program will create a log entry where information about the user will be recorded. If the user has no reservations, or has made a reservation in another machine, we print a message.

```python
if admin_or_user(uid_int, user_id_int) == True:
    logging.info("The user with UID {} and BookedId {} has started a session".format(uid_int, user_id_int))
    ...
    ...
    ...
else:
    print "The time of the reservation does not match or you are not authorized to use this machine."
```

For the next block, we begin by declaring a variable that will run/exit the following "while" loop, followed by another variable which we will use as a counter later on. The loop begins by turning off the red LED and turning on the relay, giving power to the machine. The Pi will then wait for 20 seconds before scanning for the tag again and registering the tag's UID. The last two lines indicate that when we do not want to continue reading for that tag, it will turn off the relay and the red LED.
Everything that follows in this document is placed inside the `while` loop.

```python
next_read = True
i=0

while next_read:
    GPIO.output(red_led, GPIO.LOW)
    GPIO.output(relay, GPIO.HIGH)

    time.sleep(20)

    (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
    (status, new_uid) = MIFAREReader.MFRC522_Anticoll()
    MIFAREReader.MFRC522_StopCrypto1()
    ...
    ...
    ...
GPIO.output(relay, GPIO.LOW)
GPIO.output(red_led, GPIO.LOW)
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

When the Pi goes into critical mode, the red LED will turn on, and the buzzer will emit a sound for three seconds before turning off again. The purpose of the buzzer is that of alerting the user to place the tag near the reader, or the machine will shutdown. We then initialize another counter `ii` which we will use in the next section.

```python
GPIO.output(red_led, GPIO.HIGH)
GPIO.output(buzzer, GPIO.HIGH)
time.sleep(3)       # Seconds that the buzzer remains on.
GPIO.output(buzzer, GPIO.LOW)
ii = 0
while critical_mode:
```

To finalize, the block below explains that while in critical mode, there will be a scan every ten seconds for one minute. If the initial tag is placed before the minute expires, the system will go back to normal. In the normal state, the red LED will turn off and readings will happen every 20 seconds. "Normal" state begins in the line `while next_read` three blocks of code above. However, if the tag is not placed by the end of the minute, the line `next_read = False` will terminate the current session, turning off the relay and the LED.

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
      time.sleep(10)
else:
    critical_mode = False
    next_read = False
```
