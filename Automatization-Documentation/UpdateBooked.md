# Update Booked if Change in Database

### Edited by Ricardo Rivera, March 14th 2018

The program tied to this document finds any changes that were made to the database, either manually or automatically, and updates that user in Booked. Specifically, the program looks for a "flag" (a true or false value in a given column) in the user SQL table. There are quite some changes that have to be made on the database for the following code to work. I will explain these below.

### SQL Table Modifications
---
In our user table we create a new column called "Modified" of type "Boolean", and assign a default value of 0. In this table we create a trigger called "check_if_modified" that when some other column (other than the column "Modified" itself) is updated, "Modified" receives a value of 1. This first trigger is as follows.

```sql
CREATE TRIGGER check_if_modified
BEFORE UPDATE ON YOUR_USER_TABLE_NAME FOR EACH ROW
IF (OLD.Modified = NEW.Modified) THEN SET NEW.Modified =1;
END IF;
```

The next thing we have to do is to make a new table in the database called "deleted", that should only have three columns: the user's given name, surname, and Booked ID. This table is used to check which users were removed from the main user table, meaning that the user should also be removed from Booked. When a user is deleted from the table, the trigger "delete_users" is called, which then moves the user's given name, surname and Booked ID to the "deleted" table.

```sql
CREATE TRIGGER deleted_users
BEFORE DELETE ON YOUR_USER_TABLE_NAME
FOR EACH ROW INSERT INTO RFIDTagSystem.deleted(GivenName, Surname, BookedID)
VALUES(old.GivenName, old.Surname, old.BookedID);
```

### Libraries
---
We begin by importing all the necessary libraries into the server:

```python
from sqlalchemy import create_engine
import json
import requests
from sqlalchemy.sql import text
import pandas as pd
```

### Defining Functions
---
The following function authenticates the user with admin privileges which will make all further calls to Booked. Briefly, the code makes an API call of type "POST" to Booked, taking as arguments the admin's username and password. If the user is successfully verified, the JSON response will include a "sessionToken" and a Booked "userId", which will serve as an argument for all further calls.

**Note:** Make sure that the key names for the "headers" variable are exactly named `X-Booked-SessionToken` and `X-Booked-UserId`.

```python
def authenticateBookedAdmin():
    authenticate_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Authentication/Authenticate"
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
We begin by calling the first function that we defined in the document, which authenticates the user and returns the header information necessary for all subsequent calls.

```python
headers = authenticateBookedAdmin()
```

In the following line of code we initialize the connection to the server's student database. This requires using the package "create_engine" from the library "sqlalchemy" that creates the link to the database and student table for us.  Once the connection to the database has been established, we pull the fields of interest for a user if the column "Modified" has a value of 1. The "Modified" column is what we call a flag. We then store the data into a pandas dataframe.

```python
engine = create_engine("mysql+pymysql://SQL_USERNAME:SQL_PASSWORD@MYSQL_SERVER_IP_ADDRESS/YOUR_DATABASE_NAME")
modified_rows = engine.execute("SELECT id, GivenName, Surname, Email, UID, BookedID, BookedUsername FROM YOUR_USER_TABLE_NAME WHERE Modified = 1").fetchall()
modified_table = pd.DataFrame(modified_rows, columns=["id","GivenName","Surname","Email","UID", "BookedID", "BookedUsername"])
```

### For Loop
---
We create a "for" loop that will iterate over the dataframe and select all columns for one user, creating a row of information. The "if" statement then checks if the "UID" of the selected student is empty. If the field is empty, it means that the student has no tag assigned yet and the field in Booked is then set to "NULL". In Python, the equivalent to "NULL" is "None", however the Booked site does not accept this value; then, as an alternative solution, we just write a "0" to this field. Every field that we pulled is then written into a dictionary and then transformed into a string.

 ```python
 for i in modified_table.index:
     row = modified_table.iloc[i]

     if (row["UID"] == None):
         update_info = {"firstName": row["GivenName"], "lastName": row["Surname"], "emailAddress": row["Email"], "userName": row["BookedUsername"],
     "timezone": "America/Vancouver", "customAttributes": [{"attributeId": "10", "attributeValue": 0}]}
     else:
         update_info = {"firstName": row["GivenName"], "lastName": row["Surname"], "emailAddress": row["Email"], "userName": row["BookedUsername"],
     "timezone": "America/Vancouver", "customAttributes": [{"attributeId": "10", "attributeValue": int(row["UID"])}]}

     update_info_str = json.dumps(update_info)
     ...
     ...
     ...
 ```

The following code goes inside the scope of the "for" loop we created above. We store the URL necessary for the API call that updates the information for a specific user into a variable. We make the call to update the user passing as arguments the string and the headers that we created above. Now that Booked has been updated, we can delete the flag from the user table. We do so by using a tool called "text" that enables us to pass variables to an SQL command.

 ```python
 update_user_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Users/%i" % row["BookedID"]
 requests.post(update_user_url, data=update_info_str, headers=headers)

 erase_flag = text("UPDATE YOUR_USER_TABLE_NAME SET Modified = 0 WHERE id = :v1")
 engine.execute(erase_flag, v1=int(row["id"]))
 ```

The following block of code is now outside the scope of the "for" loop we mentioned above. In this block, we deal with the case of a deleted user in the student table. When the user is deleted, we have configured MySQL to move this user into a new table called "deleted". This scripts checks if there are any users in the "deleted" table and makes an API call of type "DELETE" to Booked in order to remove the user from the site.
The lines of code are similar to the ones above so I will not go into detail.

```python
for ii in deleted_table.index:
    row = deleted_table.iloc[ii]

    delete_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Users/%i" % row["BookedID"]
    requests.delete(delete_url, headers=headers)

    erase_user = text("DELETE FROM deleted WHERE id = :w1")   # We delete the user from the "deleted" table
    engine.execute(erase_user, w1=int(row["id"]))
```
