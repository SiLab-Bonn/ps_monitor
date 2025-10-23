import sys
import zmq
import time
import argparse

# Socket to talk to server
context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.setsockopt(zmq.SUBSCRIBE, b'')  # Subscribe to everything


def recv_data(channels, port, ip):

    #print info header info
    print('# Date: %s \n' % time.asctime())

    # try-except clause for ending logger
    try:
        print("Collecting data from RaspberryPi...")
        # connecting to specified ip address and port
        socket.connect("tcp://%s:%s" % (ip, port))
        print("START")

        gate_on1_volts=[]
        gate_off_volts=[]
        for i in range(200):
            # receive actual voltage values including timestamp
            data = socket.recv_json()

            _meta, _data = data['meta'], data['data']

            write_data = [time.time(), _meta['timestamp']] + [_data[ch] for ch in channels]
            gate_on1_volts.append(write_data[2])
            gate_off_volts.append(write_data[3])
            # print voltages to terminal
                #print('\t'.join('%.{}f'.format(8) % v for v in write_data) + '\n')
            

    # end receiving with KeyboardInterrupt
    except KeyboardInterrupt:
        print('\nStopping logger...\nClosing data file...')

    mean_gate_on1 = sum(gate_on1_volts)/(len(gate_on1_volts))
    mean_gate_off = sum(gate_off_volts)/(len(gate_off_volts))
    print("GATE_ON1 [mV]", mean_gate_on1*1000)
    print("GATE_OFF [mV]", mean_gate_off*1000)
    pasteable = f"\t{mean_gate_on1*1000:.2f}\t{mean_gate_off*1000:.2f}"
    print(pasteable)
    f = open("tmpfile", "a")
    f.write(pasteable)
    f.close()


if __name__ == '__main__':

    # parse args from command line
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--channels', help='Channel names', required=True)
    parser.add_argument('-ip', '--ip_address', help='IP address', required=True)
    parser.add_argument('-p', '--port', help='Port', required=True)
    args = vars(parser.parse_args())

    recv_data(channels=args['channels'].split(' '), ip=args['ip_address'], port=args['port'])

