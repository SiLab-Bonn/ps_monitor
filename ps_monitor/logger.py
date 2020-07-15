#!usr/bin/env python

import sys
import os
import tables as tb
import numpy as np
import errno
import shutil
import time
import zmq
import yaml
from datetime import datetime
from irrad_control.devices.adc.ADS1256_definitions import *
from irrad_control.devices.adc.pipyadc import ADS1256
from irrad_control.devices.adc.ADS1256_drates import ads1256_drates
import irrad_control.devices.adc.ADS1256_default_config as ADS1256_default_config

def load_config(path_to_config_file):
    # Function, which reads the configuration yaml and checks, if all required information is contained for the chosen case.
    # Here we need to check if the config path that was given exists and is a file
    if not os.path.isfile(path_to_config_file):
        print('No config file found at the given path.')
        return

    # At this point we know that the file exists so we can proceed to open and read it
    with open(path_to_config_file, 'r') as conf_file:
        try:
            config = yaml.safe_load(conf_file)
            return config
        except yaml.YAMLError as exception:
            print(exception)
            return


def check_config(config):
    # When we're here we know, that the file was loaded correctly: we need to check if all the required info is contained in the config
    # Initialize a tuple of the values of the config file, which are essential to run the data_logger
    required_info = ('n_digits', 'channels', 'show_data', 'log_type')
    # since channel names are read from main_config.yaml as complete string, we have to get rid of the spaces first, so they dont get recognized as channel names
    config['channels'] = config['channels'] if isinstance(config['channels'], list) else config['channels'].split()
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

    if 'r' in config['log_type']:
        if not (config['port'] and config['ip']):
            raise ValueError('data_logger was called with the receiving option, but no ZMQ port or host-ip is given.')

    print('Configuration successful.')


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


def logger(channels, log_type, n_digits, show_data=False, path=None, fname=None, drate=None, pga_gain=None, rate=None, mode='s', port=None, ip=None):
    """
    Method to log the data read back from a ADS1256 ADC to a file.
    Default is to read from positive AD0-AD7 pins from 0 to 7 for single-
    ended measurement. For differential measurement pin i and i + 1 are
    selected as inputs. Only as many channels are read as there are names
    in the channel list.

    The script should be executed like this : ps_monitor main_config.yaml
    The main_config.yaml file should always be copied from the default_config.yaml and then be modified as desired.
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

    # Create file path, where data should be stored and a copy of the used main_config.yaml file is saved
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
        out = tb.open_file(os.path.join(full_path, 'data.h5' if fname is None else fname), 'w')

        # Declare data type numpy style of incoming data
        data_type = [('timestamp_recv', '<f8'), ('timestamp_data', '<f8')] + [(ch, '<f4') for ch in channels]

        # Create buffer for incoming data
        data_buffer = np.zeros(shape=1, dtype=data_type)

        # Create Group
        out.create_group(out.root, "RPiData")

        # Make table
        data_table = out.create_table("/RPiData", description=data_buffer.dtype, name="data")

        #if log_type == 'rw':
        #    # write info header
        #    out.write('# Date: %s \n' % time.asctime())
        #    out.write('# Timestamp receiver / s\t' + 'Timestamp data / s\t' + ' \t'.join('%s / V' % c for c in channels) + '\n')

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
            socket.connect("tcp://%s:%s" % (ip, port))

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

        # Set this to 0 since we want to manually calc the offset for each channel
        adc.ofc = 0

        # We're writing to file
        if log_type != 's':
            # Declare data type numpy style of incoming data
            meta_type = [('pga_gain', '<i2'), ('drate', '<f4')] + [(ch + "_offset", '<f4') for ch in channels]

            # Create buffer for incoming data
            meta_buffer = np.zeros(shape=1, dtype=meta_type)

            meta_table = out.create_table("/RPiData", description=meta_buffer.dtype, name="meta")

            meta_buffer["pga_gain"] = pga_gain
            meta_buffer["drate"] = drate
            for i, ch in enumerate(channels):
                meta_buffer[ch + "_offset"] = offset_volts[i]

            meta_table.append(meta_buffer)
            meta_table.flush()

    # save a copy of the used main_config.yaml file in the data path
    if not os.path.exists(full_path):
        try:
            os.makedirs(full_path)
        # This protects us from race conditions, if the directory was created between .exists and .makedir
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
    shutil.copyfile(sys.argv[-1], os.path.join(full_path, "used_config.yaml"))

    # try -except clause for ending logger
    try:
        print 'Start logging channel(s) %s to file %s.\nPress CTRL + C to stop.\n' % (', '.join(channels), full_path)
        start = time.time()
        while True:

            # get current channels
            if log_type == 'rw':
                readout_start = time.time()
                # receive actual voltage values including timestamp
                data = socket.recv_json()

                _meta, _data = data['meta'], data['data']

                data_buffer["timestamp_recv"] = time.time()
                data_buffer["timestamp_data"] = _meta['timestamp']
                for ch in _data:
                    data_buffer[ch] = _data[ch]

                readout_end = time.time()
            else:

                readout_start = time.time()

                raw = adc.read_continue(actual_channels)
                volts = [b * adc.v_per_digit for b in raw]

                # TODO: offset seems to be subtracted already in adc.cal_system_offset() in line 133 -> temporarily inserted factor 0.
                actual_volts = [volts[i] - offset_volts[i] for i in range(len(volts))]

                data_buffer["timestamp_data"] = readout_start
                for i, ch in enumerate(channels):
                    data_buffer[ch] = actual_volts[i]

                readout_end = time.time()

                # send data to
                if 's' in log_type:
                    data = {'meta': {'timestamp': readout_start}, 'data': dict(zip(channels, actual_volts))}
                    socket.send_json(data)

                # wait, if wanted
                if isinstance(rate, (int, float)):
                    time.sleep(1. / rate)

            # write voltages to file
            if 'w' in log_type:
                data_table.append(data_buffer)

            # User feedback about logging and readout rates every second
            if time.time() - start > 1:

                try:
                    data_table.flush()
                except NameError:
                    pass

                # actual logging and readout rate
                logging_rate = 1. / (time.time() - readout_start)
                readout_rate = 1. / (readout_end - readout_start)

                # print out with flushing
                if log_type =='rw':
                    log_string = 'Logging rate: %.2f Hz' % logging_rate + ',\t' + 'Readout rate: %.2f Hz for %i channel(s)'\
                             % (readout_rate, len(channels))
                else:
                    log_string = 'Logging rate: %.2f Hz' % logging_rate + ',\t' + 'Readout rate: %.2f Hz for %i channel(s)'\
                             % (readout_rate, len(actual_channels))

                # show values
                if show_data:
                    # print out with flushing
                    if log_type == 'rw':
                        log_string += ': %s' % ', '.join('{}: %.{}f V'.format(channels[i], n_digits) % _data[k] for i,k in enumerate(channels))
                    else:
                        log_string += ': %s' % ', '.join('{}: %.{}f V'.format(channels[i], n_digits) % actual_volts[i] for i in range(len(actual_volts)))

                # print out with flushing
                sys.stdout.write('\r' + log_string)
                sys.stdout.flush()

                # overwrite
                start = time.time()

    except (KeyboardInterrupt, SystemExit):
        if 'w' in log_type:
            print '\nStopping logger...\nClosing %s...' % str(out.filename)
            out.flush()
            out.close()

        if 's' in log_type or 'r' in log_type:
            socket.close()
            print('Stopped {} data'.format('sending' if 's' in log_type else 'receiving'))

    print 'Finished'


def main():
    # sys.argv is a list that contains the command line arguments which where given when this script was called (0th element is path to script itself)
    # The main_config.yaml should be the last argument, when you call the script.
    path_to_config_file = sys.argv[-1]
    config = load_config(path_to_config_file)
    check_config(config)
    _create_actual_adc_channels(config['channels'], config['mode'])
    logger(**config)  # Casting of dict into 'kwargs' aka keyword arguments a la key=value

    # TODO: add "socket" as argument: socket={"type": receiver|sender, "address": tcp://127.0.0.1.8888}
    # TODO: add 'logger_type' keyword which determines whether logger function will a) only write to a file b) only send data c) only receive data


if __name__ == '__main__':
    main()
