#!usr/bin/python

import sys
import os
import errno
import shutil
import time
import zmq
import logging
import argparse
import yaml
from irrad_control.devices.adc.ADS1256_definitions import *
from irrad_control.devices.adc.pipyadc import ADS1256
from irrad_control.devices.adc.ADS1256_drates import ads1256_drates
from datetime import datetime
import irrad_control.devices.adc.ADS1256_default_config as ADS1256_default_config


def _create_actual_adc_channels(channels, mode):

    # channels TODO: represent not only positive channels
    _all_channels = [POS_AIN0, POS_AIN1,
                     POS_AIN2, POS_AIN3,
                     POS_AIN4, POS_AIN5,
                     POS_AIN6, POS_AIN7]
    # gnd
    _gnd = NEG_AINCOM

    # get actual channels by name
    if len(channels) > 8 and mode == 's':
        raise ValueError('Only 8 single-ended input channels exist')
    elif len(channels) > 4 and mode == 'd':
        raise ValueError('Only 4 differential input channels exist')
    else:
        # only single-ended measurements
        if mode == 's':
            actual_channels = [_all_channels[i] | _gnd for i in range(len(channels))]

        # only differential measurements
        elif mode == 'd':
            actual_channels = [_all_channels[i] | _all_channels[i + 1] for i in range(len(channels))]

        # mix of differential and single-ended measurements
        elif len(mode) > 1:
            # get configuration of measurements
            channel_config = [1 if mode[i] == 's' else 2 for i in range(len(mode))]

            # modes are known and less than 8 channels in total
            if all(m in ['d', 's'] for m in mode) and sum(channel_config) <= 8:
                i = j = 0
                actual_channels = []

                while i != sum(channel_config):
                    if channel_config[j] == 1:
                        actual_channels.append(_all_channels[i] | _gnd)
                    else:
                        actual_channels.append(_all_channels[i] | _all_channels[i + 1])
                    i += channel_config[j]
                    j += 1

                if len(actual_channels) != len(channels):
                    raise ValueError('Number of channels (%i) not matching measurement mode ("%s" == %i differential & %i single-ended channels)!'
                                     % (len(channels), mode, mode.count('d'), mode.count('s')))
                else:
                    raise ValueError(
                        'Unsupported number of channels! %i differential (%i channels) and %i single-ended (%i channels) measurements but only 8 channels total'
                        % (mode.count('d'), mode.count('d') * 2, mode.count('s'), mode.count('s')))
        else:
            raise ValueError('Unknown measurement mode %s. Supported modes are "d" for differential and "s" for single-ended measurements.' % mode)

    return actual_channels

def check_config():
    # Function, which reads the configuration yaml and checks, if all required information is contained for the chosen case.
    # sys.argv is a list that contains the command line arguments which where given when this script was called (0th element is path to script itself)
    # The config.yaml should be the last argument, when you call the script.
    path_to_config_file = sys.argv[-1]

    # Here we need to check if the config path that was given exists and is a file
    if not os.path.isfile(path_to_config_file):
        print('No config file found at the given path.')
        return

     # At this point we know that the file exists so we can proceed to open and read it
    with open(path_to_config_file, 'r') as conf_file:
        try:
            config = yaml.safe_load(conf_file)
        except yaml.YAMLError as exception:
            print(exception)
            return

    # When we're here we know, that the file was loaded correctly: we need to check if all the required info is contained in the config
    # Initialize a tuple of the values of the config file, which are essential to run the data_logger
    required_info = ('n_digits', 'channels', 'show_data', 'log_type')

    # check, if all the values which we require are given in the config file
    missing = []
    for req_i in required_info:
        if req_i not in config:
            missing.append(req_i)
    # print out values, which were not handed over by the config file
    if missing:
        print('Following config info is missing: {}'.format(', '.join(missing)))
        return

    # check for valid configuration for each log_type, where port or ip are needed
    if 's' in config['log_type']:
        if not config['port']:
            raise ValueError('data_logger was called with the sending option, but no ZMQ port is given.')
            return

    if 'r' in config['log_type']:
        if not (config['port'] and config['ip']):
            raise ValueError('data_logger was called with the receiving option, but no ZMQ port or host-ip is given.')
            return

    print('Configuration successful.')
    return config


def logger(channels, log_type, n_digits, show_data=False, path=None, fname=None, drate=None, pga_gain=None, rate=None, mode='s', port=None, ip=None):
    """
    Method to log the data read back from a ADS1256 ADC to a file.
    Default is to read from positive AD0-AD7 pins from 0 to 7 for single-
    ended measurement. For differential measurement pin i and i + 1 are
    selected as inputs. Only as many channels are read as there are names
    in the channel list.

    The script should be executed like this : ps_monitor config.yaml
    The config.yaml file should always be copied from the default_config.yaml and then be modified as desired.
    Parameters
    ----------

    channels: list
        list of strings with names of channels
    log_type: str
        type of logging behaviour
            'w' for ONLY writing data locally
            'sw' for sending data on the specified ZMQ port AND writing it locally on the publisher
            's' for ONLY sending data on the specified ZMQ port
            'rw' for receiving data on the specified ZMQ port AND writing it locally on the receiver
    outfile: str
        string of output file location
    rate: int
        Logging rate in Hz, if None go crazy fast
    drate: int
        ADS1256 sampling rate
    pga_gain: int
        ADC programmable gain amplifier setting
    n_digits: int
        number of decimal places to be logged into the outfile
    mode: 's' or 'd' or str of combination of both
        string character(s) describing the measurement mode: single-endend (s) or differential (d)
    show_data: bool
        whether or not to show the data every second on the stdout
    port:
        ZMQ port on which data is published/received via TCP protocol

    Returns
    -------
    """
    # Create file path, where data should be stored and a copy of the used config.yaml file is saved
    full_path = os.path.join(path, datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%H-%M-%S'))

    # First thing to do: figure out which arguments are needed from log_type
    if log_type in ('w', 'sw', 'rw'):  # Here we are sure we need to open a file

        print('Storing data in ' + full_path)

        # Check if path to data_outfile already exists and makedir, if not
        if not os.path.exists(full_path):
            try:
                os.makedirs(full_path)
            # This protects us from race conditions, if the directory was created between .exists and .makedir
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise

        # Open required file
        out = open(os.path.join(full_path, 'data.dat' if fname is None else fname), 'w')

    # Second thin to figure out: are we sending or receiving data on a socket
    if log_type in ('sw', 'rw', 's'):

        # Check if port works
        try:
            _ = int(port)
        except ValueError:
            print("Port must be castable to type int! No socket will be opened!")
            return

        # Fire up ZMQ stuff
        ctx = zmq.Context()
        socket = ctx.socket(zmq.PUB if log_type != 'rw' else zmq.SUB)

        # Make distinctions between socket types
        if socket.socket_type == zmq.PUB:
            socket.bind("tcp://*:{}".format(port))
        else:
            socket.setsockopt(zmq.SUBSCRIBE, '')  # Connect to all available data
            socket.connect("tcp://{}:{}".format((ip, port)))

    # We're using the ADC
    if log_type in ('s', 'sw', 'w'):

        # dictionary of possible gain settings
        _pga_gain = dict([(1, GAIN_1),
                          (2, GAIN_2),
                          (4, GAIN_4),
                          (8, GAIN_8),
                          (16, GAIN_16),
                          (32, GAIN_32),
                          (64, GAIN_64)])

        # write chosen pga_gain setting into adcon register
        ADS1256_default_config.adcon = CLKOUT_OFF | SDCS_OFF | _pga_gain[pga_gain]  # pga_gain needs to be 0-6

        # set chosen sampling rate
        ADS1256_default_config.drate = ads1256_drates[drate]

        # get instance of ADC Board
        adc = ADS1256(conf=ADS1256_default_config)

        # additional delay after changing gain and drate registers
        adc.wait_DRDY()

        # self-calibration
        adc.cal_self()
        adc.wait_DRDY()

        actual_channels = _create_actual_adc_channels(channels, mode)

        # Get the offset voltages for every pin pair we're using here
        offset_volts = []
        for pin_pair in actual_channels:
            adc.mux = pin_pair
            adc.cal_system_offset()
            bit_offset = adc.ofc
            offset_volts.append(bit_offset * adc.v_per_digit)
        print([o * 1e3 for o in offset_volts])

        # Set this to 0 since we want to manually calc the offset for each channel
        adc.ofc = 0

        # We're writing to file
        if log_type != 's':
            out.write('# Date: %s \n' % time.asctime())
            out.write('# Measurement in %s mode.\n' % ('differential' if mode == 'd' else 'single-ended' if mode == 's' else mode))
            out.write('# ADC settings: PGA_gain = {}; Sampling_rate = {}\n'.format(pga_gain, drate))
            out.write('# Offset voltages in V: ' + '\t'.join('%.{}f'.format(n_digits) % o for o in offset_volts) + '\n')
            if log_type == 'rw':
                out.write('# Timestamp receiver / s\t' + 'Timestamp data / s\t' + ' \t'.join('%s / V' % c for c in channels) + '\n')
            else:
                out.write('# Timestamp / s\t' + ' \t'.join('%s / V' % c for c in channels) + '\n')

    # save a copy of the used config.yaml file in the data path
    shutil.copyfile(sys.argv[-1], full_path + '/used_config.yaml')

    # try -except clause for ending logger
    try:
        print 'Start logging channel(s) %s to file %s.\nPress CTRL + C to stop.\n' % (', '.join(channels), full_path)
        start = time.time()
        while True:

            # get current channels
            if log_type == 'rw':

                # receive actual voltage values including timestamp
                data = socket.recv_json()

                _meta, _data = data['meta'], data['data']

                write_data = [time.time(), _meta['timestamp']] + [_data[ch] for ch in channels]

            else:

                readout_start = time.time()

                raw = adc.read_continue(actual_channels)
                volts = [b * adc.v_per_digit for b in raw]

                # TODO: offset seems to be subtracted already in adc.cal_system_offset() in line 133 -> temporarily inserted factor 0.
                actual_volts = [volts[i] - offset_volts[i] for i in range(len(volts))]

                write_data = [readout_start] + actual_volts

                readout_end = time.time()

                # send data to
                if 's' in log_type:
                    data = {'meta': {'timestamp': readout_start}, 'data': dict(zip(channels, actual_volts))}
                    socket.send_json(data)

                # wait, if wanted
                if rate is not None:
                    time.sleep(1. / rate)

            # write voltages to file
            if 'w' in log_type:
                out.write('\t'.join('%.{}f'.format(n_digits) % v for v in write_data) + '\n')

            # User feedback about logging and readout rates every second
            if time.time() - start > 1:

                # actual logging and readout rate
                logging_rate = 1. / (time.time() - readout_start)
                readout_rate = 1. / (readout_end - readout_start)

                # print out with flushing
                log_string = 'Logging rate: %.2f Hz' % logging_rate + ',\t' + 'Readout rate: %.2f Hz for %i channel(s)'\
                             % (readout_rate, len(actual_channels))

                # show values
                if show_data:
                    # print out with flushing
                    log_string += ': %s' % ', '.join('{}: %.{}f V'.format(channels[i], n_digits) % actual_volts[i] for i in range(len(actual_volts)))

                # print out with flushing
                sys.stdout.write('\r' + log_string)
                sys.stdout.flush()

                # test print measured voltages before sending
                # print (actual_volts)

                # overwrite
                start = time.time()

    except KeyboardInterrupt:
        if 'w' in log_type:
            print '\nStopping logger...\nClosing %s...' % str(full_path)

        if 's' in log_type or 'r' in log_type:
            socket.close()
            print('Stopped {} data'.format('sending' if 's' in log_type else 'receiving'))

    print 'Finished'


def main():
    config = {}
    config = check_config()
    logger(**config)  # Casting of dict into 'kwargs' aka keyword arguments a la key=value

    # TODO: add "socket" as argument: socket={"type": receiver|sender, "address": tcp://127.0.0.1.8888}
    # TODO: add 'logger_type' keyword which determines whether logger function will a) only write to a file b) only send data c) only receive data


if __name__ == '__main__':
    main()
