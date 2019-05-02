# Edited by Ricardo Rivera on May 1st, 2019

# The code checks if the user table in the SQL database had any manual modifications. This is whether a field was updated or a user was
# deleted from the table. For the code to work we had to add two triggers on the SQL database; see the documentation file of this script for
# more detailed information. If there was any modification in the table, the script updates the relevant fields in Booked. If the user was deleted
# from the table, the user is also removed from Booked.

from sqlalchemy import create_engine
import json
import requests
from sqlalchemy.sql import text
import pandas as pd

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

headers = authenticateBookedAdmin()


# In the following block of code we find which fields have been manually changed in the database table, and update those fields in Booked.
# If a field in the table has been modified, MySQL creates a flag which sets the field "Modified" to 1. The script finds the users that have
# this flag, and updates Booked with the new information.
engine = create_engine("mysql+pymysql://SQL_USERNAME:SQL_PASSWORD@MYSQL_SERVER_IP_ADDRESS/RFIDTagSystem")

modified_rows = engine.execute("SELECT id, GivenName, Surname, Email, UID, BookedID, BookedUsername FROM YOUR_USER_TABLE_NAME WHERE Modified = 1").fetchall()
modified_table = pd.DataFrame(modified_rows, columns=["id","GivenName","Surname","Email","UID", "BookedID", "BookedUsername"])

for i in modified_table.index:
    row = modified_table.iloc[i]

    #If the user has just been created and has no UID assigned yet, for the code not to crash, it writes the value "0" in this field
    if (row["UID"] == None):
        update_info = {"firstName": row["GivenName"], "lastName": row["Surname"], "emailAddress": row["Email"], "userName": row["BookedUsername"],
    "timezone": "America/Vancouver", "customAttributes": [{"attributeId": "10", "attributeValue": 0}]}
    else:
        update_info = {"firstName": row["GivenName"], "lastName": row["Surname"], "emailAddress": row["Email"], "userName": row["BookedUsername"],
    "timezone": "America/Vancouver", "customAttributes": [{"attributeId": "10", "attributeValue": int(row["UID"])}]}

    update_info_str = json.dumps(update_info)
    update_user_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Users/%i" % row["BookedID"]
    requests.post(update_user_url, data=update_info_str, headers=headers)

    erase_flag = text("UPDATE YOUR_USER_TABLE_NAME SET Modified = 0 WHERE id = :v1") # Since Booked has been updated, we erase the flag from the table
    engine.execute(erase_flag, v1=int(row["id"]))

# In the following block of code, if a user was deleted in the "mechStudents" table, it also deletes the user from Booked.
# When the user is deleted, we have configured MySQL to move this user into a new table called "deleted". This scripts checks if there are
# students in the "deleted" table and makes a "DELETE" API call to Booked to remove the user from there as well.
deleted_rows = engine.execute("SELECT id, GivenName, Surname, BookedID FROM deleted").fetchall()
deleted_table = pd.DataFrame(deleted_rows, columns=["id", "GivenName", "Surname", "BookedID"])

for ii in deleted_table.index:
    row = deleted_table.iloc[ii]

    delete_url = "http://YOUR_BOOKED_DOMAIN/Web/Services/index.php/Users/%i" % row["BookedID"]
    requests.delete(delete_url, headers=headers)

    erase_user = text("DELETE FROM deleted WHERE id = :w1")   # We delete the user from the "deleted" table
    engine.execute(erase_user, w1=int(row["id"]))
