import datetime
import json
from pathlib import Path


def ep_datetime_parser(inp):
    date, time = inp.strip().split()
    month, day = [int(i) for i in date.split("/")]
    hr, mi, sc = [int(i) for i in time.split(":")]
    if hr == 24 and mi == 0 and sc == 0:
        return datetime.datetime(1900, month, day, 0, mi, sc) + datetime.timedelta(days=1)
    else:
        return datetime.datetime(1900, month, day, hr, mi, sc)

class Handles:
    def __init__(self):
        self.outdoor_drybulb_temperature = None
        self.direct_normal_irradiance = None
        self.diffuse_horizontal_irradiance = None
        self.complex_fenestration_state = {}
        self.window_actuators = {}
        self.lights_electricity_energy = {}
        self.light_actuators = {}


class EnergyPlusSetup:

    def __init__(self, api, epjs):
        self.api = api
        self.epjs = epjs
        self.state = self.api.state_manager.new_state()
        self.handles = Handles()
        self.window_surfaces = self.epjs['FenestrationSurface:Detailed']
        self.lights = self.epjs['Lights']
        self.api.exchange.request_variable(self.state, "Site Outdoor Air Drybulb Temperature".encode(), "Environment".encode()) 
        self.api.exchange.request_variable(self.state, "Site Direct Solar Radiation Rate per Area".encode(), "Environment".encode())
        self.api.exchange.request_variable(self.state, "Site Diffuse Solar Radiation Rate per Area".encode(), "Environment".encode()) 
        for light in self.lights:
            self.api.exchange.request_variable(self.state, "Lights Total Heating Rate".encode(), light.encode())

        self.api.runtime.callback_begin_new_environment(self.state, self.get_handles())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.api.state_manager.delete_state(self.state)

    def actuate(self, obj, value):
        self.api.exchange.set_actuator_value(self.state, obj, value)

    def get_variable_value(self, handle):
        return self.api.exchange.get_variable_value(self.state, handle)

    def get_variable_handle(self, variable_name, variable_key):
        return self.api.exchange.get_variable_handle(self.state, variable_name, variable_key)

    def get_handles(self):
        def callback_function(state):
            self.handles.outdoor_drybulb_temperature = self.api.exchange.get_variable_handle(state, "Site Outdoor Air Drybulb Temperature", "Environment")
            self.handles.direct_normal_irradiance = self.api.exchange.get_variable_handle(state, "Site Direct Solar Radiation Rate per Area", "Environment")
            self.handles.diffuse_horizontal_irradiance = self.api.exchange.get_variable_handle(state, "Site Diffuse Solar Radiation Rate per Area", "Environment")
            construction_complex_fenestration_state = self.epjs['Construction:ComplexFenestrationState']
            
            for cfs in construction_complex_fenestration_state:
                self.handles.complex_fenestration_state[cfs] = self.api.api.getConstructionHandle(state, cfs.encode())
            for window in self.window_surfaces:
                self.handles.window_actuators[window] = self.api.exchange.get_actuator_handle(state, "Surface", "Construction State", window.encode())

            for light in self.lights:
                self.handles.lights_electricity_energy[light] = self.api.exchange.get_variable_handle(state, "Lights Electricity Energy", light.encode())
                self.handles.light_actuators[light] = self.api.exchange.get_actuator_handle(state, "Lights", "Electricity Rate", light.encode())

        return callback_function
        
    def run(self):
        with open("ep.json", "w") as wtr:
            json.dump(self.epjs, wtr)
        # self.api.runtime.run_energyplus(self.state, ["-d", "output", "-r", "ep.json"])
        self.api.runtime.run_energyplus(self.state, ["-r", "ep.json"])

    def set_callback(self, method_name: str, func):
        try:
            method = getattr(self.api.runtime, method_name)
        except AttributeError:
            raise AttributeError(f"Method {method_name} not found in EnergyPlus runtime API")
        # method(self.state, partial(func, self))
        method(self.state, func)


def load_epjs(fpath: Path, api) -> dict:
    """Load and parse input file into a JSON object.
    If the input file is in .idf fomart, use command-line
    energyplus program to convert it to epJSON format
    Args:
        fpath: input file path
    Returns:
        epjs: JSON object as a Python dictionary
    """
    epjson_path: Path
    if fpath.suffix == ".idf":
        state = api.state_manager.new_state()
        api.runtime.set_console_output_status(state, False)
        api.runtime.run_energyplus(state, ["--convert-only", str(fpath)])
        api.state_manager.delete_state(state)
        epjson_path = Path(fpath.with_suffix(".epJSON").name)
        if not epjson_path.is_file():
            raise FileNotFoundError(f"Converted {str(epjson_path)} not found.")
    elif fpath.suffix == ".epJSON":
        epjson_path = fpath
    else:
        raise Exception(f"Unknown file type {fpath}")
    with open(epjson_path) as rdr:
        epjs = json.load(rdr)
    return epjs
