import sys
import zmq
import time
import argparse
from PyQt5 import QtCore, QtWidgets, QtGui
from threading import Event

# Package imports
from irrad_control.utils.worker import Worker
from irrad_control.gui.widgets import ScrollingIrradDataPlot, PlotWrapperWidget

PROJECT_NAME = 'PS Monitor'


class PSMonitorWin(QtWidgets.QMainWindow):

    data_received = QtCore.pyqtSignal(dict)

    def __init__(self, channels, ip, port, parent=None):
        super(PSMonitorWin, self).__init__(parent)

        self.stop_recv_data = Event()

        # ZMQ context; THIS IS THREADSAFE! SOCKETS ARE NOT!
        # EACH SOCKET NEEDS TO BE CREATED WITHIN ITS RESPECTIVE THREAD/PROCESS!
        self.context = zmq.Context()

        # QThreadPool manages GUI threads on its own; every runnable started via start(runnable) is auto-deleted after.
        self.threadpool = QtCore.QThreadPool()

        self.port = port
        self.ip = ip
        self.tcp_addr = 'tcp://%s:%s' % (self.ip, self.port)
        self.channels = channels

        # Create worker to listen to data stream
        worker = Worker(self.recv_data)
        self.threadpool.start(worker)

        # Create UI
        self._init_ui()

    def _init_ui(self):

        # Main window settings
        self.setWindowTitle(PROJECT_NAME)
        self.screen = QtWidgets.QDesktopWidget().screenGeometry()
        self.resize(self.screen.width(), self.screen.height())
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        # Create main layout
        self.main_widget = QtWidgets.QWidget()
        self.main_layout = QtWidgets.QVBoxLayout(self.main_widget)
        self.setCentralWidget(self.main_widget)

        plot = ScrollingIrradDataPlot(channels=self.channels, units={'left': 'V', 'right': 'V'}, name='PowerSupplyMonitor')
        self.data_received.connect(lambda data: plot.set_data(data))

        monitor_widget = PlotWrapperWidget(plot)
        self.setCentralWidget(monitor_widget)

    def recv_data(self):

        # Data subscriber
        data_sub = self.context.socket(zmq.SUB)

        # Connect to interpreter data stream
        data_sub.connect(self.tcp_addr)

        data_sub.setsockopt(zmq.SUBSCRIBE, '')
        data_timestamp = None

        while not self.stop_recv_data.is_set():

            data = data_sub.recv_json()

            if data_timestamp is None:
                data_timestamp = time.time()
            else:
                now = time.time()
                drate = 1. / (now - data_timestamp)
                data_timestamp = now
                data['meta']['data_rate'] = drate

            self.data_received.emit(data)


def main():
    # parse args from command line
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--channels', help='Channel names', required=True)
    parser.add_argument('-ip', '--ip_address', help='IP address', required=True)
    parser.add_argument('-p', '--port', help='Port', required=True)
    args = vars(parser.parse_args())
    app = QtWidgets.QApplication(sys.argv)
    font = QtGui.QFont()
    font.setPointSize(11)
    app.setFont(font)
    psm = PSMonitorWin(channels=args['channels'].split(' '), ip=args['ip_address'], port=args['port'])
    psm.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
