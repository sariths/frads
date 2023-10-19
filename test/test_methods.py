from datetime import datetime
from frads.methods import TwoPhaseMethod, ThreePhaseMethod, WorkflowConfig
from frads.window import GlazingSystem
from frads.ep2rad import epmodel_to_radmodel
from frads.eplus import EnergyPlusModel, load_energyplus_model
import frads as fr
import numpy as np
import pytest


@pytest.fixture
def cfg(resources_dir, objects_dir):
    return {
        "settings": {
            "method": "2phase",
            "sky_basis": "r1",
            "epw_file": "",
            "wea_file": resources_dir / "oak.wea",
            "sensor_sky_matrix": ["-ab", "0"],
            "view_sky_matrix": ["-ab", "0"],
            "sensor_window_matrix": ["-ab", "0"],
            "view_window_matrix": ["-ab", "0"],
            "daylight_matrix": ["-ab", "0"],
        },
        "model": {
            "scene": {
                "files": [
                    objects_dir / "walls.rad",
                    objects_dir / "ceiling.rad",
                    objects_dir / "floor.rad",
                    objects_dir / "ground.rad",
                ]
            },
            "windows": {
                "upper_glass": {
                    "file": objects_dir / "upper_glass.rad",
                    "matrix_file": resources_dir / "blinds30.xml",
                },
                "lower_glass": {
                    "file": objects_dir / "lower_glass.rad",
                    "matrix_file": resources_dir / "blinds30.xml",
                },
            },
            "materials": {
                "files": [objects_dir / "materials.mat"],
            },
            "sensors": {
                "wpi": {"file": resources_dir / "grid.txt"},
                "view1": {
                    "data": [[17, 5, 4, 1, 0, 0]],
                },
            },
            "views": {
                "view1": {"file": resources_dir / "v1a.vf", "xres": 16, "yres": 16}
            },
        },
    }


def test_two_phase(cfg):
    time = datetime(2023, 1, 1, 12)
    dni = 800
    dhi = 100
    config = WorkflowConfig.from_dict(cfg)
    with TwoPhaseMethod(config) as workflow:
        workflow.generate_matrices()
        res = workflow.calculate_sensor("wpi", time, dni, dhi)
    assert res.shape == (195, 1)


def test_three_phase(cfg, objects_dir):
    time = datetime(2023, 1, 1, 12)
    dni = 800
    dhi = 100
    config = WorkflowConfig.from_dict(cfg)
    lower_glass = objects_dir / "lower_glass.rad"
    upper_glass = objects_dir / "upper_glass.rad"
    with ThreePhaseMethod(config) as workflow:
        workflow.generate_matrices(view_matrices=False)
        workflow.calculate_sensor(
            "wpi",
            [workflow.window_bsdfs["upper_glass"], workflow.window_bsdfs["lower_glass"]],
            time,
            dni,
            dhi,
        )
        res = workflow.calculate_edgps(
            "view1",
            [lower_glass, upper_glass],
            [workflow.window_bsdfs["upper_glass"], workflow.window_bsdfs["lower_glass"]],
            time,
            dni,
            dhi,
        )
        res = workflow.calculate_sensor_from_wea("wpi")


def test_eprad_threephase(resources_dir):
    """
    Integration test for ThreePhaseMethod using EnergyPlusModel and GlazingSystem
    """
    idf_path = resources_dir / "RefBldgMediumOfficeNew2004_Chicago.idf"
    view_path = resources_dir / "view1.vf"
    epw_path = resources_dir / "USA_CA_Oakland.Intl.AP.724930_TMY3.epw"
    clear_glass_path = resources_dir / "CLEAR_3.DAT"
    product_7406_path = resources_dir / "igsdb_product_7406.json"
    shade_path = resources_dir / "ec60.rad"
    shade_bsdf_path = resources_dir / "ec60.xml"

    epmodel = load_energyplus_model(idf_path)
    gs_ec60 = GlazingSystem()
    gs_ec60.add_glazing_layer(product_7406_path)
    gs_ec60.add_glazing_layer(clear_glass_path)
    gs_ec60.gaps = [((fr.AIR, 0.1), (fr.ARGON, 0.9), 0.0127)]
    gs_ec60.name = "ec60"
    epmodel.add_glazing_system(gs_ec60)
    rad_models = epmodel_to_radmodel(epmodel, epw_file=epw_path)
    zone = "Perimeter_bot_ZN_1"
    zone_dict = rad_models[zone]
    zone_dict["model"]["views"]["view1"] = {"file": view_path, "xres": 16, "yres": 16}
    zone_dict["model"]["sensors"]["view1"] = {"data": [[17, 5, 4, 1, 0, 0]]}
    rad_cfg = WorkflowConfig.from_dict(zone_dict)
    rad_cfg.settings.sensor_window_matrix = ["-ab", "0"]
    rad_cfg.settings.view_window_matrix = ["-ab", "0"]
    rad_cfg.settings.daylight_matrix = ["-ab", "0"]
    with ThreePhaseMethod(rad_cfg) as rad_workflow:
        rad_workflow.generate_matrices(view_matrices=False)
        dni = 800
        dhi = 100
        dt = datetime(2023, 1, 1, 12)
        tmx = fr.load_matrix(shade_bsdf_path)
        edgps = rad_workflow.calculate_edgps(
            view="view1",
            shades=[shade_path],
            bsdf=tmx,
            date_time=dt,
            dni=dni,
            dhi=dhi,
            ambient_bounce=1,
        )

    assert "view1" in rad_workflow.view_senders
    assert rad_workflow.view_senders["view1"].view.vtype == "a"
    assert rad_workflow.view_senders["view1"].view.position == [6.0, 7.0, 0.76]
    assert rad_workflow.view_senders["view1"].view.direction == [0.0, -1.0, 0.0]
    assert rad_workflow.view_senders["view1"].view.horiz == 180
    assert rad_workflow.view_senders["view1"].view.vert == 180
    assert rad_workflow.view_senders["view1"].xres == 16

    assert np.sum(tmx) != 0
    assert tmx.shape == (145, 145, 3)
    assert list(rad_workflow.daylight_matrices.values())[0].array.shape == (145, 146, 3)
    assert (
        list(rad_workflow.sensor_window_matrices.values())[0].ncols == [145]
        and list(rad_workflow.sensor_window_matrices.values())[0].ncomp == 3
    )
    assert edgps >= 0 and edgps <= 1
