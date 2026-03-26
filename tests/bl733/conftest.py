import fabio
import numpy as np
import pytest

from als_tiled.bl733.adapters.gb import PILATUS_2M_PIXELS_X, PILATUS_2M_PIXELS_Y

SAMPLE_TXT_CONTENT = """\
401.000
10440.000
235561.000
Izero: 401.000
I1 normalization: 235561.000
Diode normalization: 10440.000
Normalize by: Diode
Exposure time s: 10.000
ALS Proposal #: 00622
ALS ESAF #: 00622-001
PI: PILastname
Calibration image path: /spot733-data/raw/userdata
Motors: 64
Sample X Stage: -88.245200
Sample Y Stage: 3.128650
Sample X Stage Large: 5.000500
Sample Y Stage Large: 34.997600
Sample Alpha Stage: 0.130909
Sample Phi Stage: 0.051610
M201 Feedback: 0.010372
M1 Pitch: 0.202033
M1 Bend: 48.399999
BS X: -1.357906
BS Y: 9.981358
Sample Y Stage Fine XPS: 0.000000
Sample Y Stage Labjack: 0.000000
Sample Rotation Stage: 0.000000
Slit1 top: 9.263500
Slit1 bottom: 11.732500
Slit1 right: 11.109500
Slit1 left: 11.356000
Exit Slit top: 7.781500
Exit Slit bottom: 10.976500
Exit Slit left: 6.961500
Exit Slit right: 8.903000
Sample Y Stage Robot: 0.000000
Detector Horizontal: 0.000000
Detector Vertical: 0.000000
GIWAXS beamstop X: 0.000000
GIWAXS beamstop Y: 0.000000
Beamstop X: 0.000000
Beamstop Y: 0.000000
Detector Left Motor: 0.000000
Detector Right Motor: 0.000000
Motorized Lab Jack: 0.000000
M1 Alignment Tune: 0.202033
print head height: 0.000000
Rotation New: 0.000000
printer roll: 0.000000
EZ fast tension stage: 0.000000
Motorized Lab Jack1: 0.000000
Sample Rotation Stage ESP: 0.000000
Printing motor: 0.000000
GIWAXS beamstop Y thorlabs: 0.000000
Sample Y Stage Arthur: 0.000000
Flight Tube Horizontal: 0.000000
Flight Tube Vertical: 0.000000
Hacked Ager Stage: 0.000000
Sample Rotation Stage Miller: 0.000000
Mono Angle: 0.000000
Xtal2 Pico 1 Feedback: 0.000000
Xtal2 Pico 2 Feedback: 0.000000
Xtal2 Pico 3 Feedback: 0.000000
Xtal2 Pico 1: 0.000000
Xtal2 Pico 2: 0.000000
Xtal2 Pico 3: 0.000000
Sample Y Stage_old: 0.000000
AO Waveform: 0.000000
AO0Traingle: 0.000000
AO1SquareWave: 0.000000
Lamda Zup heater: 0.000000
thermofeedback: 0.000000
spinCoaterMotor: 0.000000
BK Power Supply: 0.000000
BK Control: 0.000000
EPOS: 0.000000
EPOS2: 0.000000
DIOs: 14
SAXS Protector: 0.000000
Beamline Shutter Closed: 0.000000
Beam Current Over Threshold: 1.000000
Slit 1 in Position: 1.000000
Slit 2 in Position: 1.000000
Temp Beamline Shutter Open: 0.000000
Beamline Shutter Open: 1.000000
Feedback Interlock: 1.000000
Beamline Pass Beam: 1.000000
VacuumBadAtIG304: 0.000000
Gate Shutter: 0.000000
Bruker pulses: 0.000000
Slit Top Good: 1.000000
Slit Bottom Good: 1.000000
AIs: 38
Izero: 401.000000
GiSAXS Beamstop: 0.521687
slit1 top current: NaN
slit1 bottom current: NaN
Beam Current: 499.509338
Beamline Shutter AI: 1.000000
Beamline Pass Beam AI: 1.000000
Vertical Beam Position: NaN
IG304Epics: 11.052951
Izero AI: 0.000000
I1 AI: -0.235249
PHI Alignment Beamstop: 0.235471
AI Channel 6: -0.238456
AI Channel 7: 0.003273
thermocoupleAI3: -2.696180
Pyro: NaN
Raytec - Room Temp: 0.000000
BK Amps: NaN
BK Volts: NaN
BK Power: NaN
BK Resistance: NaN
Pilatus 300KW trigger pulse: 0.000000
Pilatus 1M Trigger Pulse: 0.000000
PCO Invert: 0.000000
Gate: 0.000000
I1: 235561.000000
GiSAXS Beamstop Counter: 522894.000000
Sum of Slit Current: 10.633427
Pilatus 100K exp out: 0.000000
Kramer strain data: 0.000000
Xtal2 Pico 1: NaN
Xtal2 Pico 2: NaN
Xtal2 Pico 3: NaN
M1 Pitch: 0.202057
ABS(Vertical Beam Position): NaN
AIat6221 Channel 6: NaN
DCVoltageMonitor: 0.000000
TC: 0.000000
!0
"""

SAMPLE_TXT_CONTENT_HI = """\
1070.000
80.231
1320.000
Izero: 1070.000
I1 normalization: 1320.000
Diode normalization: 80.231
Normalize by: Diode
Exposure time s: 0.100
ALS Proposal #: ALS-00000
ALS ESAF #: ALS-00000-000
PI: PILastname
Calibration image path: /spot733-data/raw/userdata
Motors: 71
Vertical Lift: 100.000000
Sample X Stage: -6.894300
Sample Y Stage: 12.023278
Sample X Stage Large: -25.500000
Sample Y Stage large: 26.053500
Sample Alpha Stage: 0.007603
Sample Phi Stage: 0.000000
Kapton blocker: 0.000000
Pinhole Vertical: 0.000000
Pinhole Horizontal: 0.000000
M201 Feedback: -0.898026
M1 Pitch: 0.183040
M1 Bend: 48.399999
BS X: -2.540780
BS Y: 10.369954
Sample Y Stage Labjack: 0.000000
Sample Rotation Stage: 0.000000
Slit1 top: 8.854500
Slit1 bottom: 11.534500
Slit1 right: 10.679500
Slit1 left: 11.434500
Exit Slit top: 7.082500
Exit Slit bottom: 7.384500
Exit Slit left: 7.683000
Exit Slit right: 8.030000
Kapton Blocker Horizontal: 0.000000
Kapton Blocker Vertical: 0.000000
Sample Y Stage Robot: 0.000000
Detector Horizontal: 0.000000
Detector Vertical: 0.000000
GIWAXS beamstop X: 0.000000
GIWAXS beamstop Y: 0.000000
Beamstop X: 0.000000
Beamstop Y: 0.000000
Detector Left Motor: 0.000000
Detector Right Motor: 0.000000
Motorized Lab Jack: 0.000000
M1 Alignment Tune: 0.183040
print head height: 0.000000
Rotation New: 0.000000
printer roll: 0.000000
EZ fast tension stage: 0.000000
Motorized Lab Jack1: 0.000000
Sample Rotation Stage ESP: 0.000000
Printing motor: 0.000000
GIWAXS beamstop Y thorlabs: 0.000000
Sample Y Stage Arthur: 0.000000
Flight Tube Horizontal: 0.000000
Flight Tube Vertical: 0.000000
Hacked Ager Stage: 0.000000
Sample Rotation Stage Miller: 0.000000
Mono Angle: 0.000000
Xtal2 Pico 1 Feedback: 0.000000
Xtal2 Pico 2 Feedback: 0.000000
Xtal2 Pico 3 Feedback: 0.000000
Xtal2 Pico 1: 0.000000
Xtal2 Pico 2: 0.000000
Xtal2 Pico 3: 0.000000
Sample Y Stage_old: 0.000000
AO Waveform: 0.000000
AO0Traingle: 0.000000
AO1SquareWave: 0.000000
Lamda Zup heater: 0.000000
thermofeedback: 0.000000
spinCoaterMotor: 0.000000
BK Power Supply: 0.000000
BK Control: 0.000000
EPOS: 0.000000
EPOS2: 0.000000
Fake Motor 1: 0.000000
Fake Motor 2: 0.000000
DIOs: 14
SAXS Protector: 0.000000
Beamline Shutter Closed: 0.000000
Beam Current Over Threshold: 1.000000
Slit 1 in Position: 1.000000
Slit 2 in Position: 1.000000
Temp Beamline Shutter Open: 0.000000
Beamline Shutter Open: 1.000000
Feedback Interlock: 0.000000
Beamline Pass Beam: 1.000000
VacuumBadAtIG304: 0.000000
Gate Shutter: 0.000000
Bruker pulses: 0.000000
Slit Top Good: 1.000000
Slit Bottom Good: 1.000000
AIs: 39
Izero: 1070.000000
GiSAXS Beamstop: 0.378450
slit1 top current: NaN
slit1 bottom current: NaN
Beam Current: 500.487475
Beamline Shutter AI: 1.000000
Beamline Pass Beam AI: 1.000000
Vertical Beam Position: NaN
IG304Epics: 59.738999
Izero AI: 0.000000
I1 AI: -0.124054
PHI Alignment Beamstop: 0.117137
AI Channel 6: -0.087247
AI Channel 7: 0.003600
thermocoupleAI3: -2.696388
Pyro: NaN
Raytec - Room Temp: 0.000000
BK Amps: NaN
BK Volts: NaN
BK Power: NaN
BK Resistance: NaN
Pilatus 300KW trigger pulse: 0.000000
Pilatus 1M Trigger Pulse: 0.000000
PCO Invert: 0.000000
Gate: 0.000000
I1: 1320.000000
GiSAXS Beamstop Counter: 4007.000000
Sum of Slit Current: 4.565782
Pilatus 100K exp out: 0.000000
Kramer strain data: 0.000000
Xtal2 Pico 1: NaN
Xtal2 Pico 2: NaN
Xtal2 Pico 3: NaN
M1 Pitch: 0.183040
ABS(Vertical Beam Position): NaN
AIat6221 Channel 6: NaN
DCVoltageMonitor: 0.000000
TC: 0.000000
Fake Motor 1: 0.000000
!0
"""

# Keys that differ between hi and lo are replaced; keys only in hi or lo are appended.
# All keys in these files are shared between hi and lo — only values differ.
SAMPLE_TXT_CONTENT_LO = (
    SAMPLE_TXT_CONTENT_HI
    # Unnamed header lines (Izero, Diode, I1 raw counts)
    .replace("1070.000\n80.231\n1320.000\n", "1071.000\n80.199\n1325.000\n")
    # Named scan metadata
    .replace("Izero: 1070.000\n", "Izero: 1071.000\n")
    .replace("I1 normalization: 1320.000\n", "I1 normalization: 1325.000\n")
    .replace("Diode normalization: 80.231\n", "Diode normalization: 80.199\n")
    # Motor readbacks that drifted between hi and lo exposures
    .replace("M201 Feedback: -0.898026\n", "M201 Feedback: -0.898142\n")
    .replace(
        "M1 Pitch: 0.183040\n", "M1 Pitch: 0.183044\n"
    )  # two occurrences, both change
    .replace("M1 Alignment Tune: 0.183040\n", "M1 Alignment Tune: 0.183044\n")
    # AI channel readbacks
    .replace("Izero: 1070.000000\n", "Izero: 1071.000000\n")
    .replace("GiSAXS Beamstop: 0.378450\n", "GiSAXS Beamstop: 0.378298\n")
    .replace("Beam Current: 500.487475\n", "Beam Current: 500.640318\n")
    .replace("I1 AI: -0.124054\n", "I1 AI: -0.124429\n")
    .replace("PHI Alignment Beamstop: 0.117137\n", "PHI Alignment Beamstop: 0.117747\n")
    .replace("AI Channel 6: -0.087247\n", "AI Channel 6: -0.087482\n")
    .replace("AI Channel 7: 0.003600\n", "AI Channel 7: 0.003118\n")
    .replace("thermocoupleAI3: -2.696388\n", "thermocoupleAI3: -2.696346\n")
    .replace("I1: 1320.000000\n", "I1: 1325.000000\n")
    .replace(
        "GiSAXS Beamstop Counter: 4007.000000\n",
        "GiSAXS Beamstop Counter: 3988.000000\n",
    )
    .replace("Sum of Slit Current: 4.565782\n", "Sum of Slit Current: 4.569032\n")
)

SAMPLE_EDF_HEADER = {
    "HeaderID": "EH:000001:000000:000000",
    "Image": "1",
    "VersionNumber": "0.10",
    "ByteOrder": "LowByteFirst",
    "DataType": "SignedInteger",
    "Dim_1": "1475",
    "Dim_2": "1679",
    "Date": "Mon Mar 25 17:06:51 2024",
    "count_time": "10.000000000",
    "title": "# Pixel_size 172e-6 m x 172e-6 m",
    "run": "0",
}

# Hi is acquired after lo; the GB adapter selects the later date.
SAMPLE_EDF_HEADER_HI = {
    **SAMPLE_EDF_HEADER,
    "count_time": "0.100000001",
    "Date": "Wed Oct 29 20:15:23 2025",
}
SAMPLE_EDF_HEADER_LO = {
    **SAMPLE_EDF_HEADER,
    "count_time": "0.100000001",
    "Date": "Wed Oct 29 20:15:16 2025",
}

SAMPLE_EDF_DATA = np.arange(
    PILATUS_2M_PIXELS_X * PILATUS_2M_PIXELS_Y, dtype=np.int32
).reshape(PILATUS_2M_PIXELS_Y, PILATUS_2M_PIXELS_X)

SAMPLE_GB_DATA = np.arange(
    PILATUS_2M_PIXELS_X * PILATUS_2M_PIXELS_Y, dtype="<f4"
).reshape(PILATUS_2M_PIXELS_Y, PILATUS_2M_PIXELS_X)


@pytest.fixture
def bl733_txt_path(tmp_path, scan_name="scan_name_2m"):
    """Write the sample BL7.3.3 .txt metadata string to a temporary file and
    return its path. Useful when the code under test requires a real file."""
    txt_file = tmp_path / f"{scan_name}.txt"
    txt_file.write_text(SAMPLE_TXT_CONTENT)
    return txt_file


@pytest.fixture
def bl733_edf_path(tmp_path, scan_name="scan_name_2m"):
    """Write a minimal EDF file (with SAMPLE_EDF_HEADER and SAMPLE_EDF_DATA)
    and its companion .txt to tmp_path. Returns the path to the .edf file."""
    edf_file = tmp_path / f"{scan_name}.edf"
    img = fabio.edfimage.EdfImage(data=SAMPLE_EDF_DATA, header=SAMPLE_EDF_HEADER)
    img.write(str(edf_file))

    txt_file = edf_file.with_suffix(".txt")
    txt_file.write_text(SAMPLE_TXT_CONTENT)

    return edf_file


@pytest.fixture
def bl733_gb_path(tmp_path, scan_name="scan_name"):
    """Write a .gb binary file and its hi/lo EDF companions (each with a .txt)
    to tmp_path. Returns the path to the .gb file.

    Files written:
      {scan_name}_sfloat_2m.gb
      {scan_name}_hi_2m.edf  +  {scan_name}_hi_2m.txt
      {scan_name}_lo_2m.edf  +  {scan_name}_lo_2m.txt
    """
    gb_file = tmp_path / f"{scan_name}_sfloat_2m.gb"
    SAMPLE_GB_DATA.flatten().tofile(gb_file)

    for variant, header in [("hi", SAMPLE_EDF_HEADER_HI), ("lo", SAMPLE_EDF_HEADER_LO)]:
        edf_file = tmp_path / f"{scan_name}_{variant}_2m.edf"
        img = fabio.edfimage.EdfImage(data=SAMPLE_EDF_DATA, header=header)
        img.write(str(edf_file))
        txt_content = (
            SAMPLE_TXT_CONTENT_HI if variant == "hi" else SAMPLE_TXT_CONTENT_LO
        )
        edf_file.with_suffix(".txt").write_text(txt_content)

    return gb_file
