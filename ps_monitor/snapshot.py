import sys
import zmq
import time
import argparse

# Socket to talk to server
context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.setsockopt(zmq.SUBSCRIBE, '')  # Subscribe to everything


def recv_data(channels, port, ip):

    #print info header info
    print('# Date: %s \n' % time.asctime())
    print('# Timestamp receiver / s\t' + 'Timestamp data / s\t' + ' \t'.join('%s / V' % c for c in channels) + '\n')

    # try-except clause for ending logger
    try:
        print "Collecting data from RaspberryPi..."
        # connecting to specified ip address and port
        socket.connect("tcp://%s:%s" % (ip, port))
        print "START"
	i=0
	clear_on_volts=[]
	clear_off_volts=[]
	sw_sub_volts=[]
	for i in range(100):
            # receive actual voltage values including timestamp
            data = socket.recv_json()

            _meta, _data = data['meta'], data['data']

            write_data = [time.time(), _meta['timestamp']] + [_data[ch] for ch in channels]
	    clear_on_volts.append(write_data[2])
	    clear_off_volts.append(write_data[3])
	    sw_sub_volts.append(write_data[4])
	    # print voltages to terminal
            print('\t'.join('%.{}f'.format(8) % v for v in write_data) + '\n')
	    i+=1

    # end receiving with KeyboardInterrupt
    except KeyboardInterrupt:
        print('\nStopping logger...\nClosing data file...')

    mean_clear_on = sum(clear_on_volts)/(len(clear_on_volts))
    mean_clear_off = sum(clear_off_volts)/(len(clear_off_volts))
    mean_sw_sub = sum(sw_sub_volts)/(len(sw_sub_volts))
    print("CLEAR_ON [mV]", mean_clear_on*1000)
    print("CLEAR_OFF [mV]", mean_clear_off*1000)
    print("SW_SUB [mV]", mean_sw_sub*1000)

if __name__ == '__main__':

    # parse args from command line
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--channels', help='Channel names', required=True)
    parser.add_argument('-ip', '--ip_address', help='IP address', required=True)
    parser.add_argument('-p', '--port', help='Port', required=True)
    args = vars(parser.parse_args())

    recv_data(channels=args['channels'].split(' '), ip=args['ip_address'], port=args['port'])

