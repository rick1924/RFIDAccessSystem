# Write To RFID Tags & Update SQL Database

### Edited by Ricardo Rivera, May 1st 2019

**Note:** The following script is specifically meant to be used with Python 2.7.

In this document I explain the "WriteToTag.py" script and the reasoning behind it. This program is to be used when new students are added to the student table and do not have a tag. The students however must have an account in "Booked". The program makes a connection to our student database where we have information about the students who registered for the program. The program reads this table from top to bottom, finds the students who do not have a tag (the field UID is empty), and generates one for them. The program asks the person to place the tags in the reader, and the program writes the Booked ID associated with that person into the tag. This is so when the tag is scanned in other scripts, we have this information handy. We have to alter the Booked ID number so it can be written into the tag, we call this the "StudentToken". Finally, the program also writes the tag UID corresponding to the user into "Booked". The UID will be the main authentication method for our project, and we will see this later on the program called "MainLoop.py".

### Libraries
---
We begin by importing all the necessary libraries. Some of them should already be installed in your Raspberry Pi, but the ones who aren't can easily be installed with `pip`. The library `MFRC522` should have been downloaded with the repository.

```python
import RPi.GPIO as GPIO
import MFRC522
import signal

from sqlalchemy import create_engine
import pandas as pd
import math
import time
import requests
import json
```
### Defining Functions
---
The following is a function that the creator of the "MFRC522-Python" library, Mario Gomez, has made. It safely ends all communication between the reader and the Pi.

```python
def end_read(signal, frame):
    global continue_reading
    print "Ctrl+C captured, ending read."
    continue_reading = False
    GPIO.cleanup()
```
The following function authenticates the user with admin privileges which will make all further calls to "Booked". Briefly, the code makes an API call of type "POST" to "Booked" taking as arguments the admin's username and password. If the user is successfully verified, the JSON response will include a "sessionToken" and the Booked "userId", which will serve as an argument for all further calls.

**Important:** Make sure that the key names for the "headers" variable are exactly named `X-Booked-SessionToken` and `X-Booked-UserId`.

```python
def authenticateBookedAdmin():
    authenticate_url = "http://YOUR_BOOKED_DOMAIN_NAME/Web/Services/index.php/Authentication/Authenticate"
    admin_username = "YOUR_BOOKED_USERNAME"
    admin_password = "YOUR_BOOKED_PASSWORD"
    arguments = {"username": admin_username, "password": admin_password}  # The variable is a dictionary or JSON
    arguments_str = json.dumps(arguments)  # Transforms arguments into a string
    authenticate_response = requests.post(authenticate_url, data=arguments_str)
    authenticate_response_json = authenticate_response.json()  # Makes the response a json object, easier to parse
    session_token = authenticate_response_json["sessionToken"]
    user_id = authenticate_response_json["userId"]
    return ({"X-Booked-SessionToken": session_token, "X-Booked-UserId": user_id})
```

### Initializing
---
In the following line of code we initialize the connection to the server. This requires using the package "create_engine" from sqlalchemy that creates the link to the database and student table for us. In the previous line of code, "mysql" indicates the **Dialect** that is used and "pymysql" is the **Driver** used, which together determine the behavior of the database. **Note:** To be able to extract and edit any of the fields in the table, the account used has to admin privileges.

```python
engine = create_engine("mysql+pymysql://YOUR_SQL_USERNAME:YOUR_SQL_PASSWORD@YOUR_SERVER_IP_ADDRESS/YOUR_DATABASE_NAME")
```

Now that the connection to the database has been established, we can pull the fields of interest from the "mechStudents" table and store them into a pandas dataframe. It is useful to think about the dataframe as a Microsoft Excel table.

```python
call_to_table = engine.execute("SELECT id, GivenName, Surname, Email, BookedID, BookedUsername FROM mechStudents WHERE UID IS NULL").fetchall()
table = pd.DataFrame(call_to_table, columns=["id", "GivenName", "Surname", "Email", "BookedID", "BookedUsername"])
```

Finally, we initialize the termination signal that triggers if the program crashes or there is a keyboard interrupt, as well as the MFRC522 reader.

```python
signal.signal(signal.SIGINT, end_read)
MIFAREReader = MFRC522.MFRC522()
```
### For Loop
---
We create a "for" loop that will iterate over the dataframe and select all the information for one student. We then ask the person to tap an empty tag on the reader. Finally we create a variable that will remain with a value "true" until there are no more students in the dataframe. Everything that follows in this document is placed inside this "for" loop.

```python
for i in table.index:
    row = table.iloc[i]
    print "Quickly tap and remove the tag for %s with id %i on the reader now" % (row["GivenName"], row["id"])

    continue_reading = True
    ...
    ...
```
### Reading Tags
---
From here until the end of the documentation I use portions of the python script "Read.py" that comes with the MFRC522 library. Some of the comments are the original ones by Mario Gomez.
To read the tags we need a "while" loop as the central element. Everything that follows in this document goes inside this "while" loop, so the structure is as follows:

```python
while continue_reading:
    ...
    ...
```

Inside the loop we begin by scanning for tags and checking that there is no physical error in them or that they have been altered in any way. If there is a a problem with the tag, the script will print "Authentication Error". The meaning of each line, with the help of the comment, is self-explanatory. **Note:** The line that contains the variable "key" is of no relevance to us, but should still be placed there.

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
### Creating StudentToken Key & Updating Database
---
Inside the "if" statement that I mentioned on the previous section we are going to create the "StudentToken" key, write it into the tag, and update the student table with the "UID" number we extracted from the previous section.

By inspecting the original code by Mario Gomez, we determine that the "StudentToken" key must be 16 bytes long. This is a list with 16 fields where each field allows a value from 0 to 255. We know that the key must be 16 fields long, so we left-pad the BookedID number with zeros and writhe this to the list variable. However, first we must find how many characters "BookedID" has. Remembering that "BookedID" is a number, and cannot be iterated, we change its type to an iterable string by writing `str(row["BookedID"])` and then finding its length with `len()`.

```python
data = []
zeros = range(0, 16 - len(str(row["BookedID"])))
for i in zeros:
    data.append(0)
for ii in str(row["BookedID"]):
    data.append(int(ii))
```

Then we ask the Raspberry Pi to write the list created above to the tag and display the old and new keys on screen:

```python
print "Sector 8 looked like this:"
MIFAREReader.MFRC522_Read(8)
print "\n"

MIFAREReader.MFRC522_Write(8, data)

print "It now looks like this:"
MIFAREReader.MFRC522_Read(8)
print "\n"
```

Finally, we iterate over the list "uid" to create a number that we can write into the table. As we did at the beginning of the document, we write an SQL command to save this value into the table.

```python
uid_int = int(''.join(str(e) for e in uid))
engine.execute("UPDATE YOUR_USER_TABLE_NAME SET UID = %i WHERE GivenName = '%s'" % (uid_int, row["GivenName"]))
```

### Writing to Booked
---
In the actual python script corresponding to this file, the following code is commented out. This is because once we have written the "UID" into the student table, another python script (UpdateBooked.py) will see that a new field has been written or modified and will make the necessary changes in Booked. Therefore, there is no reason to be repeating the same thing twice. The code is not completely removed because it is important to understand how this "UID" field is written into "Booked" since we will be using it in the next script, "MainLoop.py".
Right below where we left off in the last section, we write the "UID" into Booked. We begin by creating the header for the "POST" request by calling the function `authenticateBookedAdmin`. We then create a variable that holds the URL for the appropriate API call, and pass the "BookedID" for that student into the string. We then write the data and the fields that we want to update as a dictionary, and convert it into a string with `json.dumps()`. The reason why we change the dictionary into a string is because the "requests" library demands it. We then make the "POST" call to the "Booked" URL passing as arguments the data and the headers.

```python
headers = authenticateBookedAdmin()
update_user_url = "http://ubcmechstudentmachineshop.brickhost.com/Web/Services/index.php/Users/%i" % row["BookedID"]
update_user_args = {"firstName": row["GivenName"],"lastName": row["Surname"], "emailAddress":row["Email"],
"userName": row["BookedUsername"], "timezone": "America/Vancouver", "customAttributes": [{"attributeId": "10", "attributeValue": uid_int}]}
update_user_args_str = json.dumps(update_user_args)
requests.post(update_user_url, data=update_user_args_str, headers=headers)
```
### Finalizing
---
Finally, we close stop the communication between the tag and the reader, and wait three seconds before starting again with the "for" loop that checks if there is another student in the dataframe.
```python
MIFAREReader.MFRC522_StopCrypto1()
time.sleep(3)
continue_reading = False    # Stop reading for tags
```
