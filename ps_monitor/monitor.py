import sys
import zmq
import time
from PyQt5 import QtCore, QtWidgets, QtGui
from threading import Event
import logger

# Package imports
from irrad_control.utils.worker import Worker
from irrad_control.gui.widgets import ScrollingIrradDataPlot, PlotWrapperWidget

PROJECT_NAME = 'PS Monitor'


def tcp_addr(ip, port):
    return 'tcp://%s:%s' % (ip, port)


class PSMonitorWin(QtWidgets.QMainWindow):

    data_received = QtCore.pyqtSignal(dict)

    def __init__(self, config, parent=None):
        super(PSMonitorWin, self).__init__(parent)

        self.stop_recv_data = Event()

        # ZMQ context; THIS IS THREADSAFE! SOCKETS ARE NOT!
        # EACH SOCKET NEEDS TO BE CREATED WITHIN ITS RESPECTIVE THREAD/PROCESS!
        self.context = zmq.Context()

        # QThreadPool manages GUI threads on its own; every runnable started via start(runnable) is auto-deleted after.
        self.threadpool = QtCore.QThreadPool()

        self.config = config
        self.port = {}
        self.ip = {}
        self.channels = []

        # Create worker to listen to data stream

        # Create UI
        self._setup_config()
        self._init_ui()

        worker = Worker(self.recv_data)
        self.threadpool.start(worker)

    def _setup_config(self):
        # Do amazing with config dict

        for rpi in self.config:
            # Write info to instance attributes
            self.port[rpi] = self.config[rpi]["port"]
            self.ip[rpi] = self.config[rpi]["ip"]
            self.channels += self.config[rpi]["channels"]

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
        for rpi in self.config:
            data_sub.connect(tcp_addr(ip=self.ip[rpi], port=self.port[rpi]))

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

        data_sub.close()

    def close(self):

        self.context.close()

        super(self, PSMonitorWin).close()


def main(config):
    app = QtWidgets.QApplication(sys.argv)
    font = QtGui.QFont()
    font.setPointSize(11)
    app.setFont(font)
    psm = PSMonitorWin(config=config)
    psm.show()
    app.exec_()


if __name__ == '__main__':
    # parse args from command line

    path_to_config_file = sys.argv[-1]
    config = logger.load_config(path_to_config_file)
    sys.exit(main(config=config["rpis"]))
