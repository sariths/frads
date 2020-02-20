#!/usr/bin/env python3
"""."""

import csv
import datetime
import pdb
import tempfile as tf
import os
import subprocess as sp
from frads import radutil

LINESEP = os.linesep

def basis_glow(sky_basis):
    grnd_str = grndglow()
    sky_str = skyglow(sky_basis)
    return grnd_str + sky_str


def skyglow(basis, upvect='+Y'):
    sky_string = f"#@rfluxmtx u={upvect} h={basis}\n\n"
    sky_string += "void glow skyglow\n"
    sky_string += "0\n0\n4 1 1 1 0\n\n"
    sky_string += "skyglow source sky\n"
    sky_string += "0\n0\n4 0 0 1 180\n"
    return sky_string


def grndglow(basis='u'):
    ground_string = f"#@rfluxmtx h={basis}\n\n"
    ground_string += "void glow groundglow\n"
    ground_string += "0\n0\n4 1 1 1 0\n\n"
    ground_string += "groundglow source ground\n"
    ground_string += "0\n0\n4 0 0 -1 180\n\n"
    return ground_string


class Gensun(object):
    """Generate sun sources for matrix generation."""

    def __init__(self, mf):
        """."""
        self.runlen = 144 * mf**2 + 3
        self.rsrc = radutil.reinsrc(mf)
        self.mod_str = '\n'.join([f'sol{i}' for i in range(1, self.runlen)])

    def gen_full(self):
        """Generate full treganza based sun sources."""
        out_lines = []
        mod_lines = []
        for i in range(1, self.runlen):
            dirs = self.rsrc.dir_calc(i)
            line = f"void light sol{i} 0 0 3 1 1 1 sol{i} "
            line += "source sun 0 0 4 {:.6g} {:.6g} {:.6g} 0.533".format(*dirs)
            out_lines.append(line)
            mod_lines.append(f'sol{i}')
        return LINESEP.join(out_lines)+LINESEP, LINESEP.join(mod_lines)+LINESEP

    def gen_cull(self, smx_path=None, window_paths=None):
        """Generate culled sun sources based on window orientation and climate based
        sky matrix. The reduced sun sources will significantly speed up the matrix
        generation."""
        if window_paths is not None:
            wprims = [radutil.parse_primitive(wpath) for wpath in window_paths]
            wprims = [i for g in wprims for i in g]
            win_norm = [
                p['polygon'].normal().to_list() for p in wprims
                if p['type'] == 'polygon'
            ]
        else:
            win_norm = [[0, 0, -1]]
        if smx_path is not None:
            cmd = f"rmtxop -ff -c .3 .6 .1 -t {smx_path} "
            cmd += "| getinfo - | total -if5186 -t,"
            dtot = [float(i) for i in sp.check_output(cmd, shell=True).split(b',')]
        else:
            dtot = [1] * self.runlen
        out_lines = []
        mod_lines = []
        for i in range(1, self.runlen):
            dirs = self.rsrc.dir_calc(i)
            if dtot[i - 1] > 0:
                for norm in win_norm:
                    v = 0
                    if sum([i * j for i, j in zip(norm, dirs)]) < 0:
                        v = 1
                        break
            else:
                v = 0
            line = f"void light sol{i} 0 0 3 {v} {v} {v} sol{i} "
            line += "source sun 0 0 4 {:.6g} {:.6g} {:.6g} 0.533".format(*dirs)
            out_lines.append(line)
            mod_lines.append(f'sol{i}')
        return '\n'.join(out_lines), '\n'.join(mod_lines)


def epw2sunmtx(epw_path):
    """Generate reinhart 6 sun matrix file from a epw file."""
    smx_path = radutil.basename(epw_path) + ".smx"
    with tf.NamedTemporaryFile() as wea:
        cmd = f"epw2wea {epw_path} {wea.name}"
        sp.call(cmd, shell=True)
        cmd = f"gendaymtx -od -m 6 -d -5 .533 {wea.name} > {smx_path}"  # large file
        sp.call(cmd, shell=True)
    return smx_path


def loc2sunmtx(basis, lat, lon, ele):
    """Generate a psuedo reinhart 6 sun matrix file given lat, lon, etc..."""
    tz = int(5 * round(lon / 5))
    header = "place city_country\n"
    header += f"latitude {lat}\n"
    header += f"longitude {lon}\n"
    header += f"time_zone {tz}\n"
    header += f"site_elevation {ele}\n"
    header += "weather_data_file_units 1\n"
    header = str.encode(header)
    string = ""
    mday = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    for mo in range(12):
        for da in range(mday[mo]):
            for ho in range(24):
                string += f"{mo+1} {da+1} {ho+.5} 100 100"
    string = str.encode(string)
    smx_path = f"sun_{lat}_{lon}_{basis}.smx"
    with tf.NamedTemporaryFile() as wea:
        wea.write(header)
        wea.write(string)
        cmd = f"gendaymtx -od -m 6 -d -5 .533 {wea.name} > {smx_path}"
        sp.call(cmd, shell=True)
    return smx_path


def gendaymtx(data_entry, lat, lon, timezone, ele, mf=4, direct=False,
              solar=False, onesun=False, rotate=0, binary=False):
    """."""
    sun_only = ' -d' if direct else ''
    spect = ' -O1' if solar else ' -O0'
    _five = ' -5 .533' if onesun else ''
    bi = '' if binary == False or os.name == 'nt' else ' -o' + binary
    linesep = r'& echo' if os.name == 'nt' else r'\n'
    wea_head = f"place test{linesep}latitude {lat}{linesep}longitude {lon}{linesep}"
    wea_head += f"time_zone {timezone}{linesep}site_elevation {ele}{linesep}"
    wea_head += f"weather_data_file_units 1{linesep}"
    skv_cmd = f"gendaymtx -r {rotate} -m {mf}{sun_only}{_five}{spect}{bi}"
    if len(data_entry) > 1000:
        _wea, _path = tf.mkstemp()
        with open(_path, 'w') as wtr:
            wtr.write(wea_head.replace('\\n', '\n'))
            wtr.write('\n'.join(data_entry))
        cmd = skv_cmd + " " + _path
        return cmd, _path
    else:
        wea_data = linesep.join(data_entry)
        if os.name == 'nt':
            wea_cmd = f'(echo {wea_head}{wea_data}) | '
        else:
            wea_cmd = f'echo "{wea_head}{wea_data}" | '
        cmd = wea_cmd + skv_cmd
        return cmd, None


def parse_csv(csv_path, ftype='csv', dt_col="date_time", dt_format="%Y%m%d %H:%M:%S",
              dni_col='DNI', dhi_col='DHI', stime=None, etime=None):
    """Parse a csv file containing direct normal
    and diffuse horizontal data, ignoring NULL
    and zero values.

    Parameters:
        csv_path: str
            Path to the csv/tsv file.
        ftype: str, default csv
            File type to choose between csv and tsv.
        dt_col: str, default date_time
            name of the datetime column.
        dt_format: str, default %Y%m%d %H:%M:%S
            Python datetime format.
        dni_col: str, default DNI
            Column name containing direct normal
            irradiation data.
        dhi_col: str, default DHI
            Column name containing diffuse horizontal
            irradiation data.
        stime: str, default None
            Exclude the data before this time. e.g.'09:00'
        etime: str, default None
            Exclude the data after this time. e.g.'17:00'
    Returns: list object
        a list of strings containing datetime
        and solar radiation values
    """

    data_entry = []
    if None not in (stime, etime):
        stime = datetime.datetime.strptime(stime, "%H:%M")
        etime = datetime.datetime.strptime(etime, "%H:%M")
        shours = stime.hour + stime.minute / 60.0
        ehours = etime.hour + etime.minute / 60.0
    else:
        shours = 0
        ehours = 24
    ftypes = {'csv': 'excel', 'tsv': 'excel-tab'}
    with open(csv_path, encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile, dialect=ftypes[ftype])
        for row in reader:
            _dt = datetime.datetime.strptime(row[dt_col], dt_format)
            _month = str(_dt.month)
            _day = str(_dt.day)
            _hour = _dt.hour
            _minute = _dt.minute
            _hours = round(_hour + _minute / 60.0, 2)
            if _hours < shours or _hours > ehours:
                continue
            try:
                _dni = float(row[dni_col])
                _dhi = float(row[dhi_col])
            except ValueError:
                continue
            if int(_dni) == 0 and int(_dhi) == 0:
                continue
            data_entry.append([_month, _day, _hour, _minute, _hours, _dni, _dhi])
    return data_entry


def sky_cont(mon, day, hrs, lat, lon, mer, dni, dhi, year=None, grefl=.2, spect='0'):
    out_str = f'!gendaylit {mon} {day} {hrs} '
    out_str += f'-a {lat} -o {lon} -m {mer} '
    if year is not None:
        out_str += f'-y {year} '
    out_str += f'-W {dni} {dhi} -g {grefl} -O {spect}\n\n'
    out_str += 'skyfunc glow skyglow\n0\n0\n4 1 1 1 0\n\n'
    out_str += 'skyglow source sky\n0\n0\n4 0 0 1 180\n\n'
    out_str += 'skyfunc glow groundglow\n0\n0\n4 1 1 1 0\n\n'
    out_str += 'groundglow source ground\n0\n0\n4 0 0 -1 180\n'
    return out_str