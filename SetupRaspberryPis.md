# Setup a Raspberry Pi 3 Model B or B+ from Scratch (For  Raspbian Stretch OS)

### Created by Ricardo Rivera
### Last Edit: September 24th 2018

In this document I will not include how to download and load Raspbian Stretch into an empty SD card. Please refer to the [Raspberry Pi](https://www.raspberrypi.org/documentation/installation/installing-images/) documentation that shows in great detail how to make the installation.
Here, we will jump directly into the configuration necessary to have a fully functioning and secure Raspberry Pi.

### Raspberry Pi Settings Configuration
---
There are two ways of configuring your Raspberry Pi settings. The first one will require a computer with a monitor, a keyboard, a mouse, and an HDMI cable. The second way, called "headless configuration", can be done just using a laptop that has a micro SD or SD card slot, and access to wi-fi.

#### Normal Configuration (Recommended)
The first step is to connect your Raspberry Pi to the computer monitor using an HDMI cable. Once you have connected it, the Raspberry Pi's graphic interface will load in your monitor. It might take some minutes for it to load.

The Raspberry Pi might ask for a username and password the first time you are booting it up. The default username and password are:
username = pi
password = raspberry

Now that we are inside the Pi, we want to configure access to wi-fi. You will find the wi-fi icon at the top right of your Desktop. Click on your network and type the password.

If you want to access to your Raspberry Pi without using the monitor and HDMI cable, you will first have to set up an SSH or VNC connection. To setup an ssh connection open the program called "Terminal" and and type `sudo raspi-config` and a new window will open, the select the following `Interfacing Options --> SSH --> YES`. When this is done, reboot the Pi.
In a further section I will show how to access the Raspberry pi using SSH and configure VNC.

#### Headless Configuration
Take the micro SD card and plug it into your laptop, you may need and SD card adapter. In your Desktop you will see two new folders called "Boot" and "Recovery". Open any text editor of your preference and copy the following lines. Make sure to edit the "country", "ssid" and "psk" fields to match your network's country, username and password.

```
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=YOUR_COUNTRY_ISO_CODE_HERE

network={
    ssid="YOUR_NETWORK_USERNAME_HERE"
    psk="YOUR_NETWORK_PASSWORD_HERE"
    key_mgmt=YOUR_INTERNET_ENCRYPTION_KEY   # The most common encryption is WPA-PSK
}
```
Once you have typed this into the file and edited the corresponding fields, save the file as "**wpa_supplicant.conf**" and place it in the "Boot" folder I mentioned before.

To access the Pi wirelessly we will also want to configure an SSH connection. Create a new file in your text editor, do not write anything in it, save it as "**ssh.txt**" and place it in the "Boot" folder. In the next section I will explain how to connect to the Pi using SSH.

### SSH Wireless Access
---
**Important:**  If you want to access the Raspberry Pi wirelessly either with SSH or VNC, you will need to have access to the network's router since this is the only way of finding the Raspberry Pi's IP address.

I have shown you how to configure an ssh connection in the previous section, now I will explain how to access the Pi with it.  Go into your router's configuration page, look for your Raspberry Pi's IP address, and make note of it. **Depending on your router, this IP address might change the next time you power on the Pi**.

In your laptop open a "Command Line" window and type `ssh pi@YOUR_PI_IP_ADDRESS_HERE`. If the username and IP match to that of your Pi, the program will ask for a password. If you have not changed this password before, then the default password is **raspberry**.
And that is it! Keep in mind that SSH only lets you communicate to the Pi using "Command Line" commands. However, if you want a more user friendly way to communicate with it, I urge you to look at the next section.

### VNC Wireless Access
---

VNC is a program that enables the user to access the Raspberry Pi's graphical interface wirelessly. Before we do anything with the Pi, [download](https://www.realvnc.com/en/connect/download/viewer/) the VNC Viewer program into your PC or Mac.

In your Raspberry Pi open a new "Terminal" window and execute the following commands:

```
sudo apt-get install realvnc-vnc-server
sudo apt-get install realvnc-vnc-viewer
```

Now all we have to do is enable it. In the same "Terminal" window type `sudo raspi-config` and then select `Interfacing Options --> VNC --> YES` and reboot the Pi.

To access the Raspberry Pi from your PC or Mac open the VNC app and on the search bar type your Raspberry Pi's IP address and enter your Pi's username and password.

### Update & Upgrade
---
**Important:** Upgrading your Raspberry Pi might take up to an hour, so be patient.

The first time you get your Raspberry Pi, it is necessary to update and upgrade your Pi in order to get the newest firmware. After that it is good custom to update your Pi every two weeks or so. To upgrade and update your Pi open a "Terminal" window and run the following commands:

```
sudo apt-get upgrade
sudo apt-get update
```

### Change Raspberry Pi Password
---
Since all Raspberry Pi have the same default username and password, changing the password as soon as possible is a great idea. To do so open a new "Terminal" window and type `sudo raspi-config` and then select `Change User Password` and type your new password.
