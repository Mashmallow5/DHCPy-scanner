import socket
import struct
from uuid import getnode as get_mac
from random import randint
import sys

# Based on https://github.com/doyler/SecurityTools/tree/master/PyDHCPDiscover

class Scanner:
    rogueFound = False

    def __init__(self):
        if sys.version_info[0] < 3:
            raise Exception("Python 3 or a more recent version is required.")
        self.rogueFound = False
        self.optionsOut = []

    def strToIP(self, input):
        if len(input) == 4:
            input = socket.inet_ntoa(input)
        elif len(input) == 8:
            input = socket.inet_ntop(socket.AF_INET, input)
        else:
            raise ValueError("Unexpected string length for {}".format(input))
        return input

    def getMacString(self):
        mac = str(hex(get_mac())[2:])
        while (len(mac) < 12):
            mac = '0' + mac
        macB = bytes()
        for i in range(0, 12, 2) :
            m = int(mac[i:i + 2], 16)
            macB += struct.pack('!B', m)
        return macB

    def genTransactionID(self):
        transactionID = bytes()
        for i in range(4):
            t = randint(0, 255)
            transactionID += struct.pack('!B', t)
        return transactionID

    def buildDiscoverPacket(self, transactionID):
        # en.wikipedia.org/wiki/Dynamic_Host_Configuration_Protocol#DHCP_discovery

        packet = b''
        # Message type: Boot Request (1)
        packet += b'\x01'
        # Hardware type: Ethernet
        packet += b'\x01'
        # Hardware address length: 6
        packet += b'\x06'
        # Hops: 0
        packet += b'\x00'
        # Transaction ID
        packet += transactionID
        # Seconds elapsed: 0
        packet += b'\x00\x00'
        # Bootp flags: 0x8000 (Broadcast) + reserved flags
        packet += b'\x80\x00'
        # Client IP address: 0.0.0.0
        packet += b'\x00\x00\x00\x00'
        # Your (client) IP address: 0.0.0.0
        packet += b'\x00\x00\x00\x00'
        # Next server IP address: 0.0.0.0
        packet += b'\x00\x00\x00\x00'
        # Relay agent IP address: 0.0.0.0
        packet += b'\x00\x00\x00\x00'
        # Client MAC address
        packet += self.getMacString()
        # Client hardware address padding: 00000000000000000000
        packet += b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        # Server host name not given
        packet += b'\x00' * 67
        # Boot file name not given
        packet += b'\x00' * 125
        # Magic cookie: DHCP
        packet += b'\x63\x82\x53\x63'
        # Option: (t=53,l=1) DHCP Message Type = DHCP Discover
        packet += b'\x35\x01\x01'
        # Option: (t=61,l=6) Client MAC
        packet += b'\x3d\x06' + self.getMacString()
        # Option: (t=55,l=3) Parameter Request List
        packet += b'\x37\x03\x03\x01\x06'
        # End Option
        packet += b'\xff'
        return packet

    def getOption(self, key, value):
        # en.wikipedia.org/wiki/Dynamic_Host_Configuration_Protocol#DHCP_options

        optName = 'Option not found'
        optValue = 'N/A'

        if key is 1:
            optName = 'Subnet Mask'
            optValue = self.strToIP(value)
        elif key is 3:
            optName = 'Available Router'
            optValue = self.strToIP(value)
        elif key is 6:
            optName = 'Domain Name Server(s)'
            optValue = self.strToIP(value)
        elif key is 28:
            optName = 'Broadcast Address'
            optValue = self.strToIP(value)
        elif key is 51:
            optName = 'IP address Lease Time'
            optValue = str(struct.unpack('!L', value)[0])
        elif key is 53:
            optName = 'DHCP Message Type'
            if ord(value) is 1:
                optValue = 'DHCP Discover message (DHCPDiscover)'
            elif ord(value) is 2:
                optValue = 'DHCP Offer message (DHCPOffer)'
            elif ord(value) is 3:
                optValue = 'DHCP Request message (DHCPRequest)'
            elif ord(value) is 4:
                optValue = 'DHCP Decline message (DHCPDecline)'
            elif ord(value) is 5:
                optValue = 'DHCP Acknowledgment message (DHCPAck)'
            elif ord(value) is 6:
                optValue = 'DHCP Negative Acknowledgment message (DHCPNak)'
            else:
                optValue = 'Message type not supported'
        elif key is 54:
            optName = 'Server IP'
            optValue = self.strToIP(value)
            # get dhcp server's IP from the json file and compare it with the one
            # in the DHCPOFFER message
            if self.getJsonData("server_IP") != optValue:
                self.rogueFound = True
            else:
                self.rogueFound = False
        elif key is 58:
            optName = 'Renewal (T1) Time Value'
            optValue = str(struct.unpack('!L', value)[0])
        elif key is 59:
            optName = 'Rebinding (T2) Time Value'
            optValue = str(struct.unpack('!L', value)[0])
        return [optName, optValue]

    def unpackOfferPacket(self, data, transactionID):
        # en.wikipedia.org/wiki/Dynamic_Host_Configuration_Protocol#DHCP_offer

        if (data[4:8] == transactionID):
            offerIP = self.strToIP(data[16:20])
            nextServerIP = self.strToIP(data[20:24])
            dhcpOptions = data[240:]
            optionsDict = {}
            optionsOut = []
            nextOption = dhcpOptions[0] # 53
            while nextOption is not 255:
                optionKey = nextOption
                optionLen = dhcpOptions[1] # 1
                optionVal = dhcpOptions[2:2+optionLen]
                optionsDict[optionKey] = optionVal
                dhcpOptions = dhcpOptions[2+optionLen:]
                nextOption = dhcpOptions[0]

            for key in optionsDict:
                optionsOut.append(self.getOption(key, optionsDict[key]))

            if self.rogueFound:
                print("\n--- DHCP ROGUE SERVER FOUND! ---\n")
            else:
                print('\n--- DHCP SERVER FOUND! ---\n')

            for i in range(len(optionsOut)):
                print('{0:25s} : {1:15s}'.format(optionsOut[i][0], optionsOut[i][1]))

            print('{0:25s} : {1:15s}'.format('Offered IP Address', offerIP))
            print('{0:25s} : {1:15s}'.format('Gateway IP Address', nextServerIP))
            print('')

            # create a log file with server info
            self.createLog(optionsOut)

    def sendEmail(self):
        import smtplib
        from email.mime.text import MIMEText

        # get the data
        sender = self.getJsonData("mail_sender")
        receiver = self.getJsonData("mail_receiver")
        domain = self.getJsonData("mail_domain")
        password = self.getJsonData("mail_pass")
        # build the email
        subject = "DHCP rogue server found!"
        text = """A rogue DHCP server has been found in your network.
Please check the local log file for more info."""
        message = MIMEText(text, 'plain')
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = receiver
        # try to send it
        try:
            smtpObj = smtplib.SMTP_SSL(domain)
            smtpObj.login(sender, password)
            smtpObj.sendmail(sender, receiver, message.as_string())
            print("\nSuccessfully sent email\n")
        except smtplib.SMTPException as e:
            print("\nError: unable to send email\n", e)
        finally:
            smtpObj.close()

    def getJsonData(self, key):
        import json
        import os

        curDir = os.getcwd()
        inputJson = os.path.join(curDir, "input.json")

        with open(inputJson, "r") as f:
            value = json.load(f)[key]
            return value

    def createLog(self, info):
        import logging

        logPath = "DHCP_scans.log"
        logging.basicConfig(filename=logPath, filemode="a",
                            format="%(asctime)s:%(message)s", level=logging.DEBUG)
        text = ""
        for i in range(len(info)):
            text += '{0:25s} : {1:15s}\n'.format(info[i][0], info[i][1])
        text += "----------"
        if self.rogueFound:
            logging.warning("DHCP ROGUE FOUND!\n----------\n" + text)
        else:
            logging.info("DHCP SERVER FOUND!\n----------\n" + text)

        print("Log file updated\n")

    def run(self):
        dhcpSrv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dhcpSrv.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        dhcpSrv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            dhcpSrv.bind(('0.0.0.0', 68))
        except Exception as ex:
            print('There was an exception with the bind: ' + str(ex))
            dhcpSrv.close()

        transactionID = self.genTransactionID()
        dhcpSrv.sendto(self.buildDiscoverPacket(transactionID), ('<broadcast>', 67))
        print('\nDHCP Discover sent, waiting for reply\n')
        dhcpSrv.settimeout(3)
        try:
            while True:
                data = dhcpSrv.recv(2048)
                self.unpackOfferPacket(data, transactionID)
        except Exception as ex:
            if not ex is socket.timeout:
                print('There was an exception with the offer: ' + str(ex))
        finally:
            if self.rogueFound and self.getJsonData("mail_on"):
                self.sendEmail()

        dhcpSrv.close()
### end of class Scanner ###


s = Scanner()
s.run()
