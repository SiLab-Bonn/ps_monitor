import sys
import os
import yaml
import logging
import multiprocessing
from irrad_control.utils.proc_manager import ProcessManager
from ps_monitor.monitor import main as DoTheMonitoringThing
from ps_monitor import logger

logging.getLogger().setLevel("INFO")


def _configure_rpi_server(config, pm):

    # Prepare RPi
    ip = config["ip"]

    # Connect
    pm.connect_to_server(hostname=ip, username='pi')

    # Configure
    pm.configure_server(hostname=ip, branch="development", git_pull=False)


def main():

    path_to_config_file = sys.argv[-1]
    config = logger.load_config(path_to_config_file)

    pm = ProcessManager()

    # 1) Configure all RPi s
    for rpi in config['rpis']:

        logger.check_config(config['rpis'][rpi])
        _configure_rpi_server(config=config['rpis'][rpi], pm=pm)

        hostname = config['rpis'][rpi]["ip"]

        # Create config yaml per RPi
        with open("{}_config.yaml".format(rpi), "w") as rpi_config:
            yaml.safe_dump(data=config['rpis'][rpi], stream=rpi_config)

        # Create start script per RPi
        cmd = 'echo "{}"'.format("source /home/pi/miniconda2/bin/activate; python logger.py %s_config.yaml" % rpi) + ' > ${HOME}/start_logger.sh'
        pm._exec_cmd(hostname, cmd)

        # Copy config_yaml and logger.py to home folder of Rpi
        pm.copy_to_server(hostname, os.path.join(os.getcwd(), "{}_config.yaml".format(rpi)), "/home/pi/{}_config.yaml".format(rpi))
        pm.copy_to_server(hostname, os.path.join(os.path.dirname(__file__), 'logger.py'), "/home/pi/logger.py")

        pm._exec_cmd(hostname, 'nohup bash /home/pi/start_logger.sh &')

    workers = []
    for rpi in config["rpis"]:
        config["rpis"][rpi]["log_type"] = "rw"
        worker = multiprocessing.Process(target=logger.logger, kwargs=config["rpis"][rpi])
        workers.append(worker)
        worker.start()

    # Step 1) is done here
    # Step 2: move the logger.py + config + start_script to all RPis
    if config['monitor']:
        worker = multiprocessing.Process(target=DoTheMonitoringThing, args=(config["rpis"],))
        workers.append(worker)
        worker.start()

    try:
        for w in workers:
            w.join()

    except KeyboardInterrupt:
        for w in workers:
            w.terminate()


if __name__ == "__main__":
    main()
