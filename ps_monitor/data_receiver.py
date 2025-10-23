import sys
import zmq
import time
import argparse

# Socket to talk to server
context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.setsockopt(zmq.SUBSCRIBE, b'')  # Subscribe to everything


def recv_data(channels, port, ip, outfile):

    # open outfile
    with open(outfile, 'a') as out:
        # write info header
        out.write('# Date: %s \n' % time.asctime())
        out.write('# Timestamp receiver / s\t' + 'Timestamp data / s\t' + ' \t'.join('%s / V' % c for c in channels) + '\n')

        # try-except clause for ending logger
        try:
            print("Collecting data from RaspberryPi...")
            # connecting to specified ip address and port
            socket.connect("tcp://%s:%s" % (ip, port))
            print("START")
            while True:
                # receive actual voltage values including timestamp
                data = socket.recv_json()

                _meta, _data = data['meta'], data['data']

                write_data = [time.time(), _meta['timestamp']] + [_data[ch] for ch in channels]

                # write voltages to file
                out.write('\t'.join('%.{}f'.format(8) % v for v in write_data) + '\n')

        # end receiving with KeyboardInterrupt
        except KeyboardInterrupt:
            print('\nStopping logger...\nClosing data file...')


if __name__ == '__main__':

    # parse args from command line
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--channels', help='Channel names', required=True)
    parser.add_argument('-o', '--outfile', help='Output file', required=True)
    parser.add_argument('-ip', '--ip_address', help='IP address', required=True)
    parser.add_argument('-p', '--port', help='Port', required=True)
    args = vars(parser.parse_args())

    recv_data(channels=args['channels'].split(' '), ip=args['ip_address'], port=args['port'], outfile=args['outfile'])

