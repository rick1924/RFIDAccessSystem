# RFID Tag System for Access Control with Online Reservations

The project consists on the design of a cheap and fully customizable RFID tag system that together with Booked (a paid online reservation system), grants users access to machine shop equipment. The project is developed with Python, and is mainly targeted to those who want to have a better control over equipment and bigger spaces, such as an inventory tracking system, or control access to buildings, rooms, and computer labs. However, with some slight modifications, it may be transformed for personal use, such as using it to lock/unlock belongings or bedroom doors.
The project was made in collaboration with the Department of Mechanical Engineering at the University of British Columbia.

There are three main components to the project, with the addition of an optional component which helps reduce administrative time and optimizes fluidity. The former three will be described generally in this document, while the latter can be found [here](Automatization). Almost each script you observe in this repository, has an associated documentation file with detailed explanations. For the first part of the project, the project manager will have to register an account in the paid reservation system "Booked Scheduler", list the resources, and hours of operation in which the users can reserve equipment. The resources are the machines or rooms that the users will have access to once everything has been set up. Second, each user will have to create an account , and each user will be given a unique RFID tag which will be linked to their Booked account. Finally, each resource will have a Raspberry Pi controller with an RFID reader, that will read the student's tag, communicate with Booked, and authenticate the user.

There are two types of users in this project, administrators ("admin" for short), and normal users. The main difference is that admins do not need to make a reservation in order to have access to the machine, which is achieved by creating admin tags. Also, the information about administrators is stored locally in each Pi, such that there is no need for an internet connection. This also provides a solution to many unforeseen problems we may encounter while the system is running live. For example, if the Pi looses connection to the internet, or a user forgets their tag at home, the project administrators can provide users with admin tags.

## Prerequisites
As I have mentioned before, there are essential, as well as optional parts to the project. From here on, I will try to differentiate the essential from the optional components of the project. In the list below, I will also include the URL to the places where you can buy/download the hardware and software. All RFID readers and tags should be similar, but if you want to follow the project exactly, I would recommend getting the same ones as we did.

For this project we will need the following items:

### Hardware
* One Raspberry Pi 3 for each resource. Model B, B+ or A+ work fine.
* One Micro SD card for each Pi (8, 16, or 32 Gb)
* [RFID-RC522](https://www.sunfounder.com/rc522-card-read.html)
* [RFID Writable Tags]()
* Prototyping Cables
* Channel Relay
* Red LED (*optional*)
* PWM Piezoelectric Buzzer (*optional*)

### Software
* [Raspbian Stretch](https://www.raspberrypi.org/downloads/raspbian/) (Recommended)
* [Booked Scheduler](https://www.bookedscheduler.com/)
* SPI-Py
* Wi-Fi Connection
* Any SQL Database
* [PiBakery](https://www.pibakery.org/)
* Cloud Server (*optional*)

## Setup
### RFID Reader & Relay
Mario Gomez created a python library called "MFRC522-python" that enables us to interact with the RFID-RC522 reader, mentioned above. We have modified some of his original code to suit our needs, as well as used bits and pieces to make our own. This repo includes our own version of the library called "Access-MFRC522-python". In order to begin using the RFID reader module, we have to set the following connections:

| Name | Pin # |
|:----:|:-----:|
| VCC  | 1     |
| RST  | 22    |
| GND  | Any Ground |
| MISO | 21    |
| MOSI | 19    |
| SCK  | 23    |
| NSS  | 24    |
| IRQ  | None  |

**Note:** NSS is sometimes also called SDA.

To control access to the resources, we use a relay which will turn on the resource once a user has been authenticated. The relay is connected to the Pi, as well as to a 220V wall plug. The relay is "usually closed", with the purpose that if there is any problem with the Pi, it can just be disconnected and the resources would resume normal function. In our specific case, we use a red LED and a buzzer to alert the user that the tag has been removed from the reader. The connections for the relay are as follow:

| Name | Pin #|
|:----:|:----:|
| VCC  | 2    |
| GND |  Any ground |
| IN | 15 |

For a diagram of the connections click [here](CircuitDiagram.png).

### User SQL Table
The project administrator will require a computer or a cloud server that has to be constantly running, where all the information about the users will be stored. It must be constantly running since we will be accessing the user information stored in the database through the Raspberry Pis attached to each resource. The least processes we have running in this computer, the more efficient the project will be, therefore we recommend using a cloud server fully dedicated to the project.

We decided to use MySQL for our database management system, but the queries you will observe in other files can be modified to suit other systems. To begin, the project administrator will have to create a database, and then a table where the information about normal users will be stored. Some of the fields in the table could be, for example, first name, surname, email, Booked ID, and UID. The field "tag number" may also be included, and this value represents a physical marking imprinted on the tag, that helps personnel quickly identify the tag (*optional*). Booked ID is an integer and unique identifier that Booked Scheduler will assign to each user registered in the system. The UID is an integer that uniquely identifies the RFID tag given to that user. In the python scripts, we will often look at the fields UID and Booked ID, in order to authenticate the user who is requesting access to a certain resource. Also, the administrator will have to create another table that will hold the records for the admin personnel and tags. The four columns needed are: id, first name, surname, and UID. Then, the people in this table will be able to access the resources anytime, without the need of reservations.

### Booked Scheduler
Booked Scheduler is a paid open-source reservation system created by Nick Korbel. The instructions to download the system and other necessary documentation can be found [here](https://www.bookedscheduler.com/). Once the administrator account has been created in Booked, the administrator will have to input all rooms or machines available for the users to use. The system is fully customizable, granting the option to have different hours of operation for each resource, as well as time intervals for which the resource can be booked.
To add users, the administrator will have to email the users an invitation, where users can configure their account. The system will automatically assign each user a Booked ID. Once registered, the users can book any resource according to the rules set by the administrator.

**Note:** The Booked ID cannot be seen in Booked, rather it can only be obtained via API calls to the system. The documentation on how to manage the system through API can be found by typing your Booked domain name, and adding "/Web/Services". For example if your Booked system has domain "http://mytestbookingsite.com", to access the API documentation you would have to type "http://mytestbookingsite.com/Web/Services".

### Tag Creation
Each user will be given an RFID tag, which they will use to unlock the machines. In order for the reader and the Pi to search whether the user has a reservation online, we will first have to link the tag with the Booked system. We will do this by "writing" the Booked ID of the user into each tag. Each RFID tag has two attributes that will be of our interest: a "UID" and a "key". UID stands for unique identifier, which is an integer intrinsic of the tag, and it cannot be changed. However, the "key" is a writable list that contains 16 fields where each field allows a value from 0 to 255. Therefore, we will use the RFID reader mentioned in the hardware section of this document, to write the user's Booked ID into this "key". The python script that is in charge of the writing is called "WriteToTag.py", and its documentation has a very detailed explanation on we use the reader to write things into the tags. Once the Booked ID has been written into the tag, when the user wants access to the machine, the Raspberry Pi will read this number, and use it to make API calls to the reservation system and extract information about that user.

**Note:** Admin users do not have to be registered in Booked, and so do not have a Booked ID. All we will need to authenticate an administrator, is the UID of the tag they are given.

## MainLoop
The file "MainLoop.py" is the most important part of the project. This script is the one in charge of constantly scanning for tags, and authenticating users. The script is rather complicated, so it is best to read its documentation. Briefly, the script consists of an infinite loop that uses the RFID reader module to constantly scans for tags. When a tag is detected, the UID, as well as the Booked ID of the user is extracted. First, the script uses the UID and compares it with the entries of the table. If there is a match, the tag belongs to an admin and so it will automatically grant access. If the UID does not exist in the admin table, then it will make an API call to Booked, and use the Booked ID to find the information about this user. If the user has an active reservation at the time the tag is read, a relay will then enable the machine. However, if the user does not have a reservation at the time, access will not be granted.

## File Order
For every file in the following list, the reader should input their corresponding Booked domain name, as well as the database and table names. We recommend first to read the documentation file corresponding to each python file, and then modifying it accordingly.

1. Access-MFRC522-python/WriteToTag.py
2. Access-MFRC522-python/MainLoop.py
3. Automatization README (*optional*)
4. Automatization/UpdateBooked.py (*optional*)

## Authors
**Ricardo Rivera**

## License
This code and figures are licensed under the GNU Lesser General Public License 3.0 - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments
* The University of British Columbia, Department of Mechanical Engineering
* Bernhard Nimmervoll
* Markus Fengler
* Nick Korbel
* Mario Gomez
