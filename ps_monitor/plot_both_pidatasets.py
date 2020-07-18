
import datetime as dt #import datetime  # Same as datetime.datetime
import numpy as np
from matplotlib import pyplot as plt
import h5py

def get_all(name):
   print(name)

with h5py.File('/home/jannes/ps_monitor/ps_monitor/ps_monitor/RaspberryA_data/2020-07-18/16-57-15/data.h5', "r") as f:
    # List all groups
    calibration_factor_milli = (1000 / 17)
    n1 = f.get('RPiData/data')
    n2 = np.array(n1)
    n3 = np.array(n2.tolist())
    timestamps_A_data = n3[:,1]
    gateon = - calibration_factor_milli * n3[:,2]
    gateoff = calibration_factor_milli * n3[:,3]

with h5py.File('/home/jannes/ps_monitor/ps_monitor/ps_monitor/RaspberryB_data/2020-07-18/16-57-15/data.h5', "r") as f2:
    b1 = f2.get('RPiData/data')
    b2 = np.array(b1)
    b3 = np.array(b2.tolist())
    timestamps_B_data = b3[:,1]
    clearon = - calibration_factor_milli * b3[:,2]
    clearoff = calibration_factor_milli * b3[:,3]
    swsub = calibration_factor_milli * b3[:, 4]

    my_format = "Tue 16h 15m 45s"
    timestampsA_str = [dt.datetime.fromtimestamp(x) for x in timestamps_A_data]
    timestampsB_str = [dt.datetime.fromtimestamp(x) for x in timestamps_B_data]
    fig, ax = plt.subplots(5, sharex='col', sharey='row')
    fig.autofmt_xdate()
    ax[2].set(ylabel="Uncalibrated Currents / mA \n")
    ax[0].plot(timestampsA_str, gateon, label='GateOn1', marker=",",linestyle="", color='tab:blue')
    ax[1].plot(timestampsA_str, gateoff, label='GateOff', marker=",", linestyle="", color='tab:purple')
    ax[2].plot(timestampsB_str, clearon, label='ClearOn', marker=",", linestyle="", color='tab:green')
    ax[3].plot(timestampsB_str, clearoff, label='ClearOff', marker=",", linestyle="", color='tab:red')
    ax[4].plot(timestampsB_str, swsub, label='SwSub', marker=",", linestyle="", color='tab:orange')
    #ax[0].grid(True)
    #ax[1].grid(True)
    #ax[2].grid(True)
    #ax[3].grid(True)
    #ax[4].grid(True)

    ax[0].legend()
    ax[1].legend()
    ax[2].legend()
    ax[3].legend()
    ax[4].legend()
    plt.subplots_adjust(hspace=0)
    plt.show()