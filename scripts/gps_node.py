#!/usr/bin/env python
'''
NOVA ROVER TEAM

This script retrieves GPS coordinates from the Adafruit Ultimate GPS v3 module. GPS data is sent out
from the module in NMEA 0183 format. Thus, the script parses through the data lines to obtain the GPS
coordinates and publishes them to the NavSatFix message type.

More information on the wiring of the sensor + transmitted data can be found here: 
https://cdn-learn.adafruit.com/downloads/pdf/adafruit-ultimate-gps.pdf

Author: Andrew Stuart (94andrew.stuart@gmail.com)
Last modified: 14/10/2019 by Marcel Masque (marcel.masques@gmail.com)

Publishes:
    NatSatFix (sensor_msgs) named ant_gps:
        latitude - the latitude of the GPS in decimal degrees
        longitude - the longitude of the GPS in decimal degrees

Subscribes to:
    None
'''


import rospy
import serial
import time
from sensor_msgs.msg import NavSatFix
# Frequency at which the main code is repeated
ROS_REFRESH_RATE = 10

class SerialInterface:
    '''
    This class provides a general interface with a serial port. It will open and read information from the 
    port until the end of the buffer.

    Attributes:
        serial_address (str): the name of the serial connection
        baud_rate (int): the baud rate of the serial connection
        timeout (int): the maximum time in milliseconds for receiving bytes before returning
        received_data (str): the received message from serial
        uart (obj): the serial object
    TODO: Implement method to close serial connection

    '''
    def __init__(self, serial_channel, baud, timeout):
        '''
        Arguments:
            serial_channel (str): see attr
            baud (int): see attr
            timeout (int): see attr
        '''
        self.received_data = ""
        self.serial_address = serial_channel
        self.baud_rate = baud
        self.timeout = timeout
        self.uart = serial.Serial(self.serial_address, baudrate=self.baud_rate, timeout=self.timeout)
    def __clearReceivedData(self):
        self.received_data = ""

    def readSerialInput(self):
        ''' Removes previous messages and returns latest data '''
        self.__clearReceivedData()
        while(self.uart.inWaiting() > 0):
            self.received_data += self.uart.read()
        return self.received_data

class GPSSerialInterface(SerialInterface):
    ''' 
    THis class provides a specific serial interface for a GPS module recieving NMEA data. The GPS is configured to send
    only RMC data at a rate of 10 Hz
    '''
    def __init__(self, *args, **kwargs):
        ''' Method passes all given arguments to superclass and configures GPS to recieve RMC data and refresh at 10hz'''
        SerialInterface.__init__(self, *args, **kwargs)
        self.configureGPS()

    def configureGPS(self):
        ''' Configures GPS to return only RMC data and sets its refresh rate to 10Hz'''

        self.send_command(self.uart, b'PMTK314,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0')
        #Need to do sleep between commands so GPS accepts all of the commands.
        time.sleep(1)
        self.send_command(self.uart, b'PMTK220,100')

    def send_command(self, ser, command):
        '''
        Formats commands to be sent to GPS with '$' character at beginning and adds a checksum and \r\n lines to the sent command
        This function is a modified version of adafruits send_command function in their adafruit-gps library
        (https://github.com/adafruit/Adafruit_CircuitPython_GPS/blob/master/adafruit_gps.py) that works in python2
        '''

        ser.write(b'$')
        ser.write(command)
        checksum = 0
        for char in command:
            checksum ^= ord(char)
        ser.write(b'*')
        ser.write(bytes('{:02x}'.format(checksum).upper()))
        ser.write(b'\r\n')

class NMEAParser:
    '''
    This class parses through NMEA formatted data to retrieve GPS coordinates. Only NMEA 0183 
    is supported, though this class can be extended for other standards.

    Attributes:
        NMEA_Version (str): The NMEA version of the data being parsed

    TODO: Extend with other NMEA types

    '''
    def __init__(self, NMEA_type):
        '''
        Arguments:
            NMEA_type (str): The NMEA standard to be parsed
        '''
        self.NMEA_version = NMEA_type
        self.__NMEA_ID = -1 # Initialise ID of NMEA as invalid (<0)      
        if(NMEA_type == 'NMEA_0183'):
            self.__NMEA_ID = 0

    def getNMEAVersion(self):
        ''' Returns internal NMEA ID '''
        return self.__NMEA_ID

    def __convertDMToDD(self, deg, min, direction):
        '''
        Converts a GPS coordinate in Degrees Minutes format to Decimal Degrees

        Arguments:
            deg (int): coordinate degrees
            min (float): coordinate minutes
            direction (char/str): the coordinate direction (N/S/E/W)

        Returns:
            float: the coordinate in decimal degrees format

        TODO: Add range limits
        '''
        direction_modifier = 1.0
        if((direction == "W") or (direction == "S")):
            direction_modifier = -1.0
        return (direction_modifier*(deg + (min/60.0)))

    def __formatGPSData(self, data):
        '''
        Takes in an array containing coordinate information strings in an array.The strings are 
        then converted into int/float for degrees and minutes.

        Arguments:
            data (str array): string array containing coordinate information in the form of
                [latitude, latitude direction, longitude, longitude direction]

        Returns:
            float array: the latitude and longitude in decimal degrees format

        TODO: Uncouple __formatGPSData and __convertDMToDD
        '''
        # For NMEA 0183....
        if(self.__NMEA_ID == 0):
            # Retrieve coordinate strings
            raw_latitude = data[0]
            latitude_direction = data[1]
            raw_longitude = data[2]
            longitude_direction = data[3]

            # Separate coordinate into degrees and minutes
            lat_deg = int(raw_latitude[0:2])
            lat_min = float(raw_latitude[2:])
            long_deg = int(raw_longitude[0:3])
            long_min = float(raw_longitude[3:])

            # Convert each coordinate into decimal degrees
            latitude_DD = self.__convertDMToDD(lat_deg, lat_min, latitude_direction)
            longitude_DD = self.__convertDMToDD(long_deg, long_min, longitude_direction)
            return [latitude_DD, longitude_DD]

    def getGPSLocation(self, data):
        '''
        The main method called - when given NMEA strings, the strings are parsed to find the
        line containing RMC (the recommended minimum coordinates). This lines contains the GPS
        coordiates. The coordinates are then split from the rest of the line and are converted
        into decimal degrees format.

        Arguments:
            data (str): string containing NMEA data lines

        Returns:
            float array: the latitude and longitude in decimal degrees format

        TODO: Add other NMEA types
        '''
        # For NMEA 0183...
        if(self.__NMEA_ID == 0):
            split_lines = []
            split_lines = data.split('$') # Each line starts with $ - we can use this to separate each line

            # Iterate through each line
            for data_line in split_lines:
                if(data_line[2:5] == 'RMC'): # The line containing the GPS coordinates has the identifier RMC
                    split_RMC_line = data_line.split(',')   # Split RMC line into different fields
                    if(len(split_RMC_line) <> 13):  # 13 fields are expected, variations from this point to corruption
                        rospy.logwarn("INVALID RMC READING - CHECK FOR HARDWARE CORRUPTION")
                        return 0.0, 0.0
		    
                    if(split_RMC_line[2] == 'V'):   # V is printed at the end of the line if no fix has been established
                    	rospy.logwarn("NO GPS FIX")
                        return 0.0, 0.0
                    if not (self.computeChecksum(data_line)):
                        rospy.logwarn("CHECKSUM FAILED - POSSIBLE DATA CORRUPTION")
                        return 0.0, 0.0

                    elif(split_RMC_line[2] == 'A'): # A indicates a valid GPS fix
                    	return self.__formatGPSData(split_RMC_line[3:7]) # Format the GPS data into decimal degrees
                    else:
                        rospy.logwarn("INVALID RMC READING - CHECK FOR HARDWARE CORRUPTION")
                    	return 0.0, 0.0



    #Yoinked from adafruit: https://github.com/adafruit/Adafruit_CircuitPython_GPS/blob/master/adafruit_gps.py
    def send_command(ser, command):
        ser.write(b'$')
        ser.write(command)
        checksum = 0
        for char in command:
            checksum ^= char
        ser.write(b'*')
        ser.write(bytes('{:02x}'.format(checksum).upper(), "ascii"))
        ser.write(b'\r\n')

    def computeChecksum(self,data):
        """compute a char wise XOR checksum of the data and compare it to the hex value after the * in the data string

        Argument:
        data {str} -- String containing comma separated GPS data with checksum result directly after *
        Returns: 
        {bool} -- True if checksum is correct, False otherwise
        """
        try:
            #take a substring between $ and *
            s1 = data.split('*')[0]
        except:
            #if we can't find a * the data is corrupt; return false
            return False

        #compute char wise checksum
        checksum = 0
        for char in s1:
            checksum ^= ord(char)
        #convert to hex for comparison with checksum value in str
        checksum = hex(checksum)
	
        try:
            checksum_str = "0x" + data.split("*")[1]
        except:
            return False
        checksum_int = int(checksum_str, 16)
        hex_checksum = hex(checksum_int)

        if checksum != hex_checksum:
            return False
        else:
            return True	


def transmitGPS():
    '''
    This function sets up the ROS node, serial connection and NMEA Parser. It then repeatedly checks for new data received 
    on the serial line and converts this data to GPS coordinates if available. The frequency of checks depends on the 
    global variable ROS_REFRESH_RATE.
    '''

    gps_interface = GPSSerialInterface("/dev/serial0", 9600, 3000)
    msg = NavSatFix()
    pub = rospy.Publisher('ant_gps', NavSatFix, queue_size=10)
    rospy.init_node('antenna_gps', anonymous=True)
    rate = rospy.Rate(ROS_REFRESH_RATE)
    parser = NMEAParser('NMEA_0183')
    while not rospy.is_shutdown():
        received_data = gps_interface.readSerialInput()                 # Get serial data
	rospy.loginfo(received_data)
	try:
		[latitude, longitude] = parser.getGPSLocation(received_data)    # Parse data and set message fields
	        msg.latitude = latitude                                         # Publish coordinates
        	msg.longitude = longitude
		pub.publish(msg)	
        	rate.sleep()                                                    # Sleep until next check
	except:
		rate.sleep()
		pass
if __name__ == '__main__':
    try:
        transmitGPS()
    except rospy.ROSInterruptException:
        pass

