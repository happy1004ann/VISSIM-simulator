# ==========================================================================
# Author : HyeAnn Lee
# ==========================================================================
import json
import logging
import logging.config
import math
import os
import random

config = json.load(open("./logger.json"))
logging.config.dictConfig(config)
logger = logging.getLogger(__name__)


def convert_signal_to_enum(Signal):
    # Input
    # > 'Signal' : 1D-list of SigControl().

    switcher = {'R': 'RED', 'G': 'GREEN', 'Y': 'AMBER'}
    for sigcon in Signal:
        for i in range(len(sigcon.SigInd)):
            for j in range(len(sigcon.SigInd[i])):
                sigcon.SigInd[i][j] = switcher.get(sigcon.SigInd[i][j])
    return


def set_randomseed(seed):
    # Input
    # > 'seed' : int.
    #
    # Output
    # > int in range [1, (1 << 31) - 1]
    #
    # Set appropirate random seed for Vissim simulation.

    if 0 < seed < (1<<31):
        return seed

    return random.randint(1, (1 << 31) - 1)


def check_sig_file(Vissim):
    # Check if all .sig files are valid or not.

    SC_Iter = Vissim.Net.SignalControllers.Iterator
    while SC_Iter.Valid:
        sig_file = SC_Iter.Item.AttValue('SupplyFile2')
        if (sig_file != "") and (not os.path.exists(sig_file)):
            logger.error("check_sig_file() : At least one of sig files is missing.")

        SC_Iter.Next()

    return


def get_travtm_info(Vissim):
    # Output
    # > 'link' : 1D list of (str, str)

    link = Vissim.Net.VehicleTravelTimeMeasurements.GetMultipleAttributes(('StartLink', 'EndLink'))

    # Check for duplicates
    tempset = set(link)
    if len(link) != len(tempset):
        logger.error("get_travtm_info() : There is an invalid Vehicle Travel Time Measurement.")

    return link


def get_node_info(Vissim):
    # Output
    # > 'nodeno' : 1D list of int

    nodeno = []
    node_numbers = Vissim.Net.Nodes.GetMultiAttValues('No')
    for _, No in node_numbers:
        nodeno.append(No)

    return nodeno


def find_incoming_lane(Vissim, lanes_with_SH):
    # Input
    # > 'lanes_with_SH' : Empty list.
    #
    # Find all lanes with signal heads.

    SH_Iter = Vissim.Net.SignalHeads.Iterator
    while SH_Iter.Valid:
        SH = SH_Iter.Item
        linkNo, laneNo = SH.AttValue('Lane').split('-')
        linkNo = int(linkNo)
        laneNo = int(laneNo)
        length = Vissim.Net.Links.ItemByKey(linkNo).AttValue('Length2D')
        lanes_with_SH.append((linkNo, laneNo, SH.AttValue('Pos'), length))
        SH_Iter.Next()

    # 'lanes_with_SH' becomes a 1D list of
    #               (int, int, double, double) = (linkNo of SH, laneNo of SH, pos of SH, length of link)
    lanes_with_SH.sort()

    return


def set_Vissim(Vissim, simLen, seed):
    ## Evaluation
    Vissim.Evaluation.SetAttValue('KeepPrevResults', 1)

    Vissim.Evaluation.SetAttValue('DataCollCollectData',    True)
    Vissim.Evaluation.SetAttValue('LinkResCollectData',     True)
    Vissim.Evaluation.SetAttValue('NodeResCollectData',     True)
    Vissim.Evaluation.SetAttValue('QueuesCollectData',      True)
    Vissim.Evaluation.SetAttValue('VehTravTmsCollectData',  True)

    Vissim.Evaluation.SetAttValue('DataCollInterval',   3600)
    Vissim.Evaluation.SetAttValue('LinkResInterval',    99999)
    Vissim.Evaluation.SetAttValue('NodeResInterval',    3600)
    Vissim.Evaluation.SetAttValue('QueuesInterval',     3600)
    Vissim.Evaluation.SetAttValue('VehTravTmsInterval', 3600)

    ## Net
    Vissim.Net.NetPara.SetAttValue('UnitAccel', 0)          # m/s^2
    Vissim.Net.NetPara.SetAttValue('UnitLenLong', 0)        # km
    Vissim.Net.NetPara.SetAttValue('UnitLenShort', 0)       # m
    Vissim.Net.NetPara.SetAttValue('UnitLenVeryShort', 0)   # mm
    Vissim.Net.NetPara.SetAttValue('UnitSpeed', 0)          # km/h
    Vissim.Net.NetPara.SetAttValue('UnitSpeedSmall', 0)     # m/s

    ## Simulation
    Vissim.Simulation.SetAttValue('SimPeriod', simLen)      # Set simulation period
    Vissim.Simulation.SetAttValue('RandSeed', seed)         # Choose Random Seed
    Vissim.Simulation.SetAttValue('UseMaxSimSpeed', True)   # Set Maximum Speed

    ## Others
    Vissim.Graphics.CurrentNetworkWindow.SetAttValue("QuickMode", 1)    # Activate QuickMode
    Vissim.SuspendUpdateGUI()   # Stop updating Vissim workspace (network editor, list and chart)

    return


def set_link_segment(Vissim):
    # Set [link evaluation segment length] to [length of the link].

    Link_Iter = Vissim.Net.Links.Iterator
    while Link_Iter.Valid:
        link = Link_Iter.Item
        link.SetAttValue('LinkEvalSegLen', link.AttValue('Length2D'))
        Link_Iter.Next()

    return


def set_queue_counter(Vissim, lanes_with_SH):
    # Input
    # > 'lanes_with_SH' : 1D list of (int, int, double, double)
    #
    # Set queue counters at links with signal head.

    def _add_QC(Link):
        key = Vissim.Net.QueueCounters.Count + 1
        Vissim.Net.QueueCounters.AddQueueCounter(key, Link, QC[-1])

    # Remove existing QC
    All_QCs = Vissim.Net.QueueCounters.GetAll()
    for QC in All_QCs:
        Vissim.Net.QueueCounters.RemoveQueueCounter(QC)

    # 'SHs'
    SHs = []
    for linkNo, _, pos, _ in lanes_with_SH:
        if (not SHs) or (SHs[-1][0] != linkNo):
            SHs.append([linkNo, pos])
        else:
            SHs[-1].append(pos)

    # 'SHs' becomes a list of [linkNo, pos1, pos2, ..., posN].
    # Set New QC.
    for linkNo, *pos_list in SHs:
        pos_list.sort()

        QC = []
        for Pos in pos_list:
            if (not QC) or (abs(QC[-1] - Pos) < 10):
                QC.append(Pos)
            else:   # abs(QC[-1] - pos) >= 10
                _add_QC(Vissim.Net.Links.ItemByKey(linkNo)) # Set QueueCounter for previous 'Pos'es.
                QC = [Pos]                                  # Reset 'QC' to current 'Pos'.

        _add_QC(Vissim.Net.Links.ItemByKey(linkNo))

    return


def set_data_collection(Vissim, lanes_with_SH):
    # Input
    # > 'lanes_with_SH' : 1D list of (int, int, double, double)
    #
    # Set data collection points at lanes with signal head.

    # Remove existing DC
    All_DCPs = Vissim.Net.DataCollectionPoints.GetAll()
    for DCP in All_DCPs:
        Vissim.Net.DataCollectionPoints.RemoveDataCollectionPoint(DCP)

    # Remove existing DC measurements
    All_DCMs = Vissim.Net.DataCollectionMeasurements.GetAll()
    for DCM in All_DCMs:
        Vissim.Net.DataCollectionMeasurements.RemoveDataCollectionMeasurement(DCM)

    # Set New DC and DC measurements
    for linkNo, laneNo, pos, _ in lanes_with_SH:
        key = Vissim.Net.DataCollectionPoints.Count + 1

        # data collection point
        lane = Vissim.Net.Links.ItemByKey(linkNo).Lanes.ItemByKey(laneNo)
        Vissim.Net.DataCollectionPoints.AddDataCollectionPoint(key, lane, pos - 1.6)

        # data collection measurement
        Vissim.Net.DataCollectionMeasurements.AddDataCollectionMeasurement(key)
        Vissim.Net.DataCollectionMeasurements.ItemByKey(key).SetAttValue('DataCollectionPoints', key)

    return


def set_vehicleinput(Vissim, SimLen, TimeInterval, VehicleInput):
    # Input
    # > 'SimLen' : int.
    # > 'TimeInterval' : int.
    # > 'VehicleInput' : 1D-list of VehInput().

    def _change_models():
        # Add motorbike, SUV, small truck models.

        v3d_file_path = "C:\\Program Files\\PTV Vision\\PTV Vissim 11\\Exe\\3DModels\\Vehicles\\Road\\"
        list_filename = os.listdir(v3d_file_path)
        typeNkey = {'LtTruck': 51, 'Bike': 61, 'SUV': 71}

        while list_filename:
            filename = list_filename.pop()
            modeltype, modelname = filename.split(' - ', 1)
            if ((modeltype == "Bike") and (modelname[:-4] in ["Motorbike 01", "Scooter 01"])) or (modeltype in ["LtTruck", "SUV"]):
                # Check if the model already exists
                Model_name = Vissim.Net.Models2D3D.GetMultiAttValues('Name')
                exist = False
                for _, model in Model_name:
                    if filename[:-4] in model:
                        exist = True
                        break
                if exist:
                    continue

                # Find appropriate key
                modelkey = typeNkey.get(modeltype)

                while Vissim.Net.Models2D3D.ItemKeyExists(modelkey):
                    modelkey += 1

                # Add model
                Vissim.Net.Models2D3D.AddModel2D3D(modelkey, [v3d_file_path + filename])
                Vissim.Net.Models2D3D.ItemByKey(modelkey).SetAttValue("Name", filename[:-4])

        return

    def _change_distr():
        # Add model2d3ddistributions.

        carSUVs = []
        LtTrucks = []
        Bikes = []

        Models = Vissim.Net.Models2D3D.GetMultipleAttributes(('Name', 'No'))
        for name, no in Models:
            if name.startswith(('Car', 'SUV')):
                carSUVs.append(no)
            elif name.startswith('LtTruck'):
                LtTrucks.append(no)
            elif name.startswith('Bike'):
                Bikes.append(no)

        newdistr = [(1, carSUVs, "CarSUV"), (2, LtTrucks, "LtTruck"), (3, Bikes, "Bike")]
        for distrKey, distrEl, distrName in newdistr:
            Vissim.Net.Model2D3DDistributions.AddModel2D3DDistribution(distrKey, distrEl)
            Vissim.Net.Model2D3DDistributions.ItemByKey(distrKey).SetAttValue("Name", distrName)

        return

    def _change_types():
        # Set vehicle type according to 안양시.
        # : 승용차, 소형트럭, 대형트럭, 특수차, 버스, 오토바이.

        def _find_dist_key(dist_name):
            # Input
            # > 'dist_name' : str.
            #
            # Output
            # > 'ele_no' : int.
            #
            # Find key by name.

            for ele_no, ele_name in dist_attrs:
                if ele_name == dist_name:
                    return ele_no

        dist_attrs = Vissim.Net.Model2D3DDistributions.GetMultipleAttributes(('No', 'Name'))
        vehicle_types = [("Vehicle", _find_dist_key('CarSUV')),     ("Small Truck", _find_dist_key('LtTruck')),
                         ("Large Truck", _find_dist_key('HGV')),    ("Special Car", _find_dist_key('HGV')),
                         ("Bus", _find_dist_key('Bus')),            ("Motor Cycle", _find_dist_key('Bike'))]

        # New types are assigned successively from key 1.
        key_vehicletype = 1
        for name_type, key_dist in vehicle_types:
            Vissim.Net.VehicleTypes.AddVehicleType(key_vehicletype)
            VT = Vissim.Net.VehicleTypes.ItemByKey(key_vehicletype)
            VT.SetAttValue("Name", name_type)
            VT.SetAttValue("Model2D3DDistr", Vissim.Net.Model2D3DDistributions.ItemByKey(key_dist))
            key_vehicletype += 1

        return

    def _set_time_interval(timestep):
        # Input
        # > 'timestep' : int.

        TI_VI = Vissim.Net.TimeIntervalSets.ItemByKey(1).TimeInts
        for TIkey in range(1, timestep):
            TI_VI.AddTimeInterval(TIkey + 1)    # Here, interval is automatically set to 15min (= 900sec).
            if TimeInterval != 900:
                TI_VI.ItemByKey(TIkey + 1).SetAttValue('Start', TimeInterval * TIkey)

        return

    def _set_vehcomp(vehcompkey, DesSpeed):
        # Input
        # > 'vehcompkey' : int.
        # > 'DesSpeed' : int.

        # Add new DesSpeedDistribution if necessary.
        if not Vissim.Net.DesSpeedDistributions.ItemKeyExists(DesSpeed):
            Vissim.Net.DesSpeedDistributions.AddDesSpeedDistribution(DesSpeed, ())
            SDDP_getall = Vissim.Net.DesSpeedDistributions.ItemByKey(DesSpeed).SpeedDistrDatPts.GetAll()
            SDDP_getall[0].SetAttValue('X', DesSpeed - 2)
            SDDP_getall[1].SetAttValue('X', DesSpeed + 8)

        # Add new vehicle composition.
        Vissim.Net.VehicleCompositions.AddVehicleComposition(vehcompkey, ())
        # Then, first vehicle type (here, [Vehicle]) is automatically added to relative flow table with DesSpeedDistr 5.
        VC = Vissim.Net.VehicleCompositions.ItemByKey(vehcompkey)

        # Add all vehicle types (except above first one) to relative flow table.
        for veh_type in range(1, num_vehtype):
            vt = Vissim.Net.VehicleTypes.ItemByKey(veh_type + 1)
            dsd = Vissim.Net.DesSpeedDistributions.ItemByKey(DesSpeed)
            VC.VehCompRelFlows.AddVehicleCompositionRelativeFlow(vt, dsd)

        # Set DesSpeedDistr of above first one to 'DesSpeed'.
        Rel_flows = VC.VehCompRelFlows.GetAll()
        Rel_flows[0].SetAttValue('DesSpeedDistr', DesSpeed)

        # Set appropriate RelFlows.
        for i in range(num_vehtype-1, -1, -1):
            volume = VehicleInput[index_timeint].VehInfo[index_link].VehComp[i] # float
            if volume == 0:
                VC.VehCompRelFlows.RemoveVehicleCompositionRelativeFlow(Rel_flows[i])
            else:
                Rel_flows[i].SetAttValue('RelFlow', volume)

        return

    num_timeint = len(VehicleInput)
    num_link    = len(VehicleInput[0].VehInfo)
    num_vehtype = len(VehicleInput[0].VehInfo[0].VehComp)

    # Validation check
    if math.ceil(SimLen / TimeInterval) != num_timeint:
        logger.error("set_vehicleinput() : The number of sheets in VehicleInput Excel file is incorrect... Check the file again.")

    # Remove existing VI
    All_VIs = Vissim.Net.VehicleInputs.GetAll()
    for VI in All_VIs:
        Vissim.Net.VehicleInputs.RemoveVehicleInput(VI)

    # init
    _change_models()
    _change_distr()
    _change_types()     # <- Set to 안양 version.

    _set_time_interval(num_timeint)

    for index_link in range(num_link):   # for each link
        # Add vehicle input to Vissim network
        linkno = VehicleInput[0].VehInfo[index_link].LinkNo
        Vissim.Net.VehicleInputs.AddVehicleInput(linkno, Vissim.Net.Links.ItemByKey(linkno))

        VI = Vissim.Net.VehicleInputs.ItemByKey(linkno)
        for index_timeint in range(num_timeint):    # for each time interval
            timeint_str = '(' + str(index_timeint + 1) + ')'

            # Set volume
            if index_timeint != 0:
                VI.SetAttValue('Cont' + timeint_str, False)
            VI.SetAttValue('Volume' + timeint_str, sum(VehicleInput[index_timeint].VehInfo[index_link].VehComp))

            # Set vehcomp
            key = Vissim.Net.VehicleCompositions.Count + 1
            _set_vehcomp(key, 50)
            VI.SetAttValue('VehComp' + timeint_str, Vissim.Net.VehicleCompositions.ItemByKey(key))

    return
