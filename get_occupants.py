""" 
Author: Ryan Peterman
Contributors: Jeffrey Chan

Lab Occupancy Sensor - to tell if anyone is in the lab
"""

import subprocess
import os
import json
import time
from slackclient import SlackClient
import csv
import datetime

# to track stderr for bugfix
import sys
import traceback
import re

# list of officers
officer_list = []

class Officer:
    """ Class to hold the data for each person """
    name = ""
    mac_addr = ""
    status = 0 # 0 == online, 1 == tracked
    is_in_lab = False
    miss_count = 0 # if this gets to 5 we remove them from the list
                   # if they are seen on the scan we set it to 0

    def __init__(self):
        self.name = ""
        self.mac_addr = ""
        self.status = 0
        self.is_in_lab = False
        self.miss_count = 0

    def print_officer(self):
        """ print officer function for debugging"""
        print "-------------------------"
        for m_data in [a for a in dir(self)
            if not a.startswith('__') and not callable(getattr(self, a))]:

            print m_data + " = " + str(getattr(self, m_data))

def run_scan():
    """ populates officer list with mac addresses seen in arp-scan,
    returns number of matches """

    # store arp output (max 20 retries)
    for _ in xrange(20):
        try:
            arp_output = subprocess.check_output(["sudo", "arp-scan", "-l"])
        except Exception:
            # skip break and try again if error when running arp-scan
            continue

        # break if arp-scan worked
        break

    # didnt work even after 20 tries
    if not arp_output:
        sys.stderr.write("Error: arp-scan failed 20 times in a row")

    # number of hits
    num_hits = 0
    # used to add to miss count
    scan_hit = False

    # find if any officer mac address is found in the arp_output
    for officer in officer_list:
        for line in arp_output.splitlines():
            if officer.mac_addr in line:
                # we know they are in the lab
                officer.is_in_lab = True
                officer.miss_count = 0
                scan_hit = True

        # if this officer not found in arp-scan
        if not scan_hit:
            officer.miss_count += 1

        # officer was found and set scan_hit back to false for next officer
        else:
            scan_hit = False

        # they have been missing for more than 25 seconds?
        if officer.miss_count > 5:
            officer.is_in_lab = False

    return num_hits

def get_occupants():
    """ Checks current list of officers to see who is in the lab """
    # build up newline delimited string of officers
    officer_str = ""

    # bool for when only anonymous people in lab
    is_someone_in = False

    # if officer is in lab add to str
    for officer in officer_list:
        if officer.is_in_lab:
            if not officer.status:
                officer_str += officer.name + "\n"
            else:
                is_someone_in = True

    # no officers to explicitly add
    if not officer_str:
        # an anoymous person is in the lab
        if is_someone_in:
            return "People are in the lab."
        else:
            return ("I Haven't seen anyone in the lab."
            "Please try again to be sure!")

    return officer_str

def init_officers():
    """ Populates all the officer objects with their data from csv"""

    file_handler = open('total_hours.csv', 'rb')
    reader = csv.reader(file_handler)
    # skip over header_list
    header_list = reader.next()

    for row in reader:

        # create officer object
        officer = Officer()

        for col_label, i  in zip(header_list, range(len(header_list))):
            if col_label == "Name":
                officer.name = str(row[i])
            elif col_label == "Mac Address":
                # lower because this is how arp-scan outputs it
                officer.mac_addr = str(row[i].lower())
            elif col_label == "Status":
                officer.status = int(row[i])

        # add officer to officer list
        officer_list.append(officer)

    file_handler.close()

    for officer in officer_list:
        officer.print_officer()

def exit_handler():
    # exit without calling anything else
    os._exit(0)

def handle_input(user_input, event, slack_obj):
    """ returns the message that a user would receive based on their input """

    message = ""

    # if bot received text "whois"
    if user_input == "whois":
        # reply with list of officers
        message = get_occupants()

    else:
        message = ("Here are the following commands I support:\n"
        "whois - prints people currently in the lab \n")

    return message

def main():
    # read bot token into variable
    with open('key.txt', 'r') as key_file:
        bot_token = key_file.read().replace('\n', '')

    # initialize SlackClient
    slack_obj = SlackClient(bot_token)

    # initialize officers
    init_officers()

    # the id of the bot
    bot_id = "U0H7GEEJW"

    # counts up after every sleep(1)
    # so we can poll when counter reachs 5 sec
    counter = 0

    # connect to the bots feed
    if slack_obj.rtm_connect():
        while True:
            # read event_list from peterbot's feed
            try:
                event_list = slack_obj.rtm_read()
            # in the event that it throws an error just set it
            # to an empty list and continue
            except Exception, excep:
                # print to add to log
                sys.stderr.write(excep)
                event_list = []

            for event in event_list:
                user_input = ""
                message = ""

                # get and format the input text
                if event.get("text"):
                    user_input = event.get("text").lower().strip()
                    print "Received user input: ", user_input

                    # return a message based on the user's input
                    message = handle_input(user_input, event, slack_obj)

                # if there is a message to send, then send it
                # will not respond if received from bot message to prevent
                # looping conversation with itself
                if message and event.get("user") != bot_id:
                    chan_id = event.get("channel")
                    slack_obj.api_call("chat.postMessage", as_user="true:",
                        channel=chan_id, text=message)

            # delay
            time.sleep(1)
            counter += 1

            # every 5 seconds, run a scan quietly
            if counter >= 5:
                counter = 0
                num_hits = run_scan()

    else:
        sys.stderr.write("Connection Failed: invalid token")

# runs main if run from the command line
if __name__ == '__main__':
    try:
        main()
    finally:
        exit_handler()
