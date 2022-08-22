# ==========================================================================
# Author : HyeAnn Lee
# ==========================================================================
import json
import logging
import logging.config
import sys
from collections import namedtuple

config = json.load(open("resources/logger.json"))
logging.config.dictConfig(config)
logger = logging.getLogger(__name__)


class SigControl:
    def __init__(self, name, offset_info):
        self.Name = name    # string
        self.offset_info = offset_info  # (Int, Int). (offset[sec], main 현시)
        self.SigInd = []    # 2D-list of characters 'R', 'G' or 'Y'.
        self.BreakAt = []   # 1D-list of int.
        self.total_simulation = 0    # int


class VehInput:
    def __init__(self, timeint):
        self.TimeInt = timeint  # positive int
        self.VehInfo = []       # elements will be namedtuple 'LinkInfo'.


NUM_DISCRIPTION_LINE = 3


def read_json(datainfo, filename):
    # Input
    # > 'datainfo' : dict.
    # > 'filename' : Absolute path of json file. <class 'pathlib.WindowsPath'>.
    #
    # Output
    # > 'data' : Init().

    with filename.open('r', encoding='UTF8') as init_json:
        data_dict = json.load(init_json)

    comp1 = data_dict['TargetFile']
    comp2 = data_dict['Settings']

    datainfo['signal_xlsx'] = comp1['Signal']
    datainfo['vehicle_input_xlsx'] = comp1['VehicleInput']
    datainfo['vissim_inpx'] = comp1['VissimInput']
    datainfo['vehicle_routes_xlsx'] = comp1['Static Vehicle Routes']

    datainfo['random_seed'] = comp2['RandomSeed']
    datainfo['quick_mode'] = comp2['Quick Mode']
    datainfo['simulation_time'] = comp2['Simulation period [sec]']
    datainfo['vehicle_input_period'] = comp2['TimeInterval of VehicleInput']
    datainfo['comment'] = comp2['Comment']

    if not isinstance(datainfo['random_seed'], int):
        logger.error(
            "RandomSeed should be an integer. Check json file again.")
    if not isinstance(datainfo['simulation_time'], int):
        logger.error(
            "Simulation period should be a positive integer.",
            "Check json file again.")
    if not isinstance(datainfo['vehicle_input_period'], int):
        logger.error(
            "TimeInterval of VehicleInput should be a positive integer.",
            "Check json file again.")

    return


def read_signal(wb, Signal, sim_len):
    # Input
    # > 'wb' : Excel file with contents of signal information.
    # > 'Signal' : Empty list.
    # > 'sim_len' : simulation period in seconds.

    def _read_signal_seq(sigcon):
        # Input
        #   'sigcon' : SigControl() with self.Name.
        #
        # Read signal information of '현시' table.

        sg_nums = []    # Signal group No's.

        # Read signal group No.
        row = NUM_DISCRIPTION_LINE + 1
        while isinstance(ws.Cells(row, 3).Value, str):
            sg_no = ws.Cells(row, 2).Value
            sg_nums.append(int(sg_no))
            row += 1
        sg_nums = tuple(sg_nums)

        # Read and store signal information.
        column = 3
        while ws.Cells(NUM_DISCRIPTION_LINE + 1, column).Value:
            # Each element of 'SigInd' will contain signal information
            # ('R', 'G', 'Y') from all "signal group"s in one signal step.

            sigind = [None] * max(sg_nums)

            for row in range(1, max(sg_nums)+1):
                value = ws.Cells(NUM_DISCRIPTION_LINE + row, column).Value

                # Break if signal time met.
                if isinstance(value, float):
                    break

                if value not in ['R', 'G', 'Y']:
                    logger.error("_read_signal_seq():\t"
                                 + "Invalid signal from xlsx. "
                                 + "You must use either 'R', 'G' or 'Y'.")
                sigind[sg_nums[row-1]-1] = value

            sigcon.SigInd.append(sigind)
            column += 1

        return

    def _read_signal_time(sigcon):
        # Input
        #   'sigcon' : SigControl() with self.Name and self.SigInd.
        #
        # Read signal information of '현시 시간 배분' table.

        actual_sg = len(sigcon.SigInd[0]) - sigcon.SigInd.count(None)
        row = NUM_DISCRIPTION_LINE + actual_sg + 1
        offset = sigcon.offset_info
        column = 3 + offset[1] - 1

        period = 0
        accTime = offset[0]
        sigcon.BreakAt.append(accTime)

        while ws.Cells(row, column).Value:
            time = ws.Cells(row, column).Value
            if not isinstance(time, float):
                logger.error("_read_signal_time():\t"
                             + "You should use an integer for signal time.")
            if (int(time) != time) or (time < 1):
                logger.error("_read_signal_time():\t"
                             + "Signal time should be a positive integer.")

            period += time
            accTime += time
            sigcon.BreakAt.append(accTime)
            column += 1
            if column - 3 == len(sigcon.SigInd):
                if row != (NUM_DISCRIPTION_LINE + len(sigcon.SigInd[0]) + 1)\
                 and offset[0] > period:
                    logger.error(
                        "at _read_signal_time():\t"
                        + f"Signal offset ({offset[0]} sec) is larger than "
                        + f"signal period ({int(period)} sec). "
                        + f"Check '{sigcon.Name}' sheet again.")
                period = 0
                row += 1
                column = 3

        sigcon.BreakAt = [0 for _ in range(offset[1]-1)] + sigcon.BreakAt
        sigcon.total_simulation = int(accTime)

        return

    try:
        num_worksheets = wb.Worksheets.Count
        num_intersections = num_worksheets - 1

        # signal offset of each intersection
        offset_info = dict()    # (Int, Int) = (offset[sec], main 현시)
        ws = wb.Worksheets(1)
        for col in range(2, num_intersections+2):
            name = ws.Cells(NUM_DISCRIPTION_LINE + 1, col).Value
            offset = int(ws.Cells(NUM_DISCRIPTION_LINE + 2, col).Value)
            main_signal = int(ws.Cells(NUM_DISCRIPTION_LINE + 3, col).Value)
            offset_info[name] = (offset, main_signal)

        for i in range(1, num_intersections+1):
            ws = wb.Worksheets(i+1)

            # SigControl.Name & .offset_info
            sigcontrol = SigControl(ws.name, offset_info[ws.name])

            # SigControl.SigInd
            _read_signal_seq(sigcontrol)
            main_signal = sigcontrol.offset_info[1]
            sigcontrol.SigInd =\
                sigcontrol.SigInd[main_signal-2:]\
                + sigcontrol.SigInd[:main_signal-2]

            # SigControl.BreakAt
            _read_signal_time(sigcontrol)

            Signal.append(sigcontrol)

    except Exception as e:
        print('\t', sys.exc_info()[0], e)

    finally:
        ws = None

    # 'Signal' becomes a 1D-list of SigControl().
    if not Signal:
        logger.error("read_signal():\t"
                     + "Signal file is empty. Check json file again.")

    for sigcontrol in Signal:
        if sigcontrol.total_simulation > sim_len:
            sigcontrol.BreakAt = [i for i in sigcontrol.BreakAt if i < sim_len]
            sigcontrol.BreakAt.append(sim_len)
            sigcontrol.total_simulation = sim_len
            logger.info(
                sigcontrol.Name
                + f'\tsimulation time changed to: {sim_len} [s]')

        if sigcontrol.total_simulation < sim_len:
            logger.error(
                "read_signal():"
                + "\tSimulation time of each sheet should be"
                + f"at least {sim_len} [s]."
                + f"(Currently {sigcontrol.total_simulation} [s])"
                + f"Check '{sigcontrol.Name}' sheet again.")

    return


def read_vehicleinput(wb, VehicleInput):
    # Input
    # > 'wb' : Excel file with contents of vehicle input information.
    # > 'VehicleInput' : Empty list.

    def _set_vehinfo(ws, vehin):
        # Input
        # > 'ws' : Excel worksheet.
        # > 'vehin' : VehInput() with self.TimeInt.

        num_vehcomp = 0
        while ws.Cells(NUM_DISCRIPTION_LINE + 2, num_vehcomp + 2).Value:
            num_vehcomp += 1

        row = NUM_DISCRIPTION_LINE + 3
        while ws.Cells(row, 1).Value:
            # linkinfo.LinkNo   : int
            LinkNo = int(ws.Cells(row, 1).Value)

            # linkinfo.VehComp  : 1D-tuple of positive floats
            temp_list = []
            for column in range(2, num_vehcomp + 2):
                volume = ws.Cells(row, column).Value
                if not isinstance(volume, (int, float)):
                    volume = 0
                temp_list.append(volume)
            VehComp = tuple(temp_list)

            # add linkInfo to VehInfo
            vehin.VehInfo.append(LinkInfo(LinkNo, VehComp))
            row += 1

        return

    LinkInfo = namedtuple('namedtuple_linkinfo', ['LinkNo', 'VehComp'])

    try:
        for i in range(wb.Worksheets.Count):
            # set VehInput.TimeInt
            vehinput = VehInput(i + 1)

            # set VehInput.VehInfo
            ws = wb.WorkSheets(i + 1)
            _set_vehinfo(ws, vehinput)

            # add vehinput
            VehicleInput.append(vehinput)

    except Exception as e:
        print(e)

    finally:
        ws = None

    # 'VehicleInput' becomes a 1D-list of VehInput().
    if not VehicleInput:
        logger.error("read_vehicleinput():\t"
                     + "VehicleInput file is empty. Check json file again.")
    num_link = len(VehicleInput[0].VehInfo)
    for vehinput in VehicleInput:
        if len(vehinput.VehInfo) != num_link:
            logger.error("read_vehicleinput():\t"
                         + "The number of links in VehicleInput Excel file is "
                         + "different in some sheets. Check the file again.")

    return


def read_static_vehicle_routes(wb, Static_Vehicle_Routes):
    try:
        ws = wb.Worksheets(1)

        # cell A1: "$VISION"
        # cell A2: "* File: ..."
        row = 2
        while ws.Cells(row, 1).Value.startswith('*'):
            row += 1

        # cell A{row}: "$VEHICLEROUTESTATIC ..."
        col = 1
        column_names = []
        while True:
            value = ws.Cells(row, col).Value
            if not value:
                break
            column_names.append(value.split(':')[-1])
            col += 1

        Static_Vehicle_Routes.append(tuple(column_names))
        row += 1

        # cell A{row}: "6", B{row}: "1", ...
        data = []
        while ws.Cells(row, 1).Value:
            single_route = []
            for col in range(1, len(column_names)+1):
                value = ws.Cells(row, col).Value
                single_route.append(str(value))
            data.append(tuple(single_route))
            row += 1

        Static_Vehicle_Routes.append(data)

    except Exception as e:
        print('\t', sys.exc_info()[0], e)

    finally:
        ws = None

    # Static_Vehicle_Routes ==
    # [
    #  ('VEHROUTDEC', 'NO', 'NAME', 'FORMULA', 'DESTLINK', 'DESTPOS', 'RELFLOW(1)'),
    #  [('6.0', '1.0', 'None', 'None', '10028.0', '9.649', '3.0'),
    #   ('6.0', '2.0', 'None', 'None', '10027.0', '9.763', '6.0'),
    #   ('6.0', '3.0', 'None', 'None', '10029.0', '10.284', '1.0'),
    #   ('7.0', '1.0', 'None', 'None', '10025.0', '11.319', '3.0'),
    #   ('7.0', '2.0', 'None', 'None', '10024.0', '12.447', '6.0'),
    #   ('7.0', '3.0', 'None', 'None', '10026.0', '14.177', '1.0'),
    #   ('9.0', '1.0', 'None', 'None', '10042.0', '15.812', '6.0'),
    #   ...]
    # ]

    return


def set_accum_break(list_of_SigControl):
    # Input
    # > 'list_of_SigControl' : 1D-list of SigControl().
    #
    # Output
    # > 'accum_break' : 1D-list of int.
    #
    # Aggregate breakpoints of all SigControls.

    accum_break = []
    for sigcon in list_of_SigControl:
        accum_break += sigcon.BreakAt
    temp_set = set(accum_break)
    accum_break = list(temp_set)
    accum_break.sort()
    accum_break.remove(0)
    if not accum_break:
        logger.error("set_accum_break():\t"
                     + "Simulation time is 0. Check signal Excel file again.")

    return accum_break[:-1]
