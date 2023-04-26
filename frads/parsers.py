"""
This module contains all data parsing routines.
"""
import argparse
import configparser
from datetime import datetime
from pathlib import Path
import re
from typing import Tuple, Any
from typing import Generator
from typing import List
from typing import Optional, Sequence
from typing import Union

from pyradiance import param as radparam
from pyradiance import model
from frads import geom
from frads.types import PaneProperty
from frads.sky import WeaMetaData
from frads.sky import WeaData


def parse_mrad_config(cfg_path: Path) -> configparser.ConfigParser:
    """Parse mrad configuration file."""
    if not cfg_path.is_file():
        raise FileNotFoundError(cfg_path)
    config = configparser.ConfigParser(
        allow_no_value=False,
        inline_comment_prefixes="#",
        interpolation=configparser.ExtendedInterpolation(),
        converters={
            "path": lambda x: Path(x.strip()),
            "paths": lambda x: [Path(i) for i in x.split()],
            # "options": parse_opt,
            "options": radparam.parse_rtrace_args,
            "view": parse_vu,
        },
    )
    config.read(Path(__file__).parent / "data" / "mrad_default.cfg")
    config.read(cfg_path)
    return config


def parse_epw(epw_str: str) -> tuple:
    """Parse epw file and return wea header and data."""
    raw = epw_str.splitlines()
    epw_header = raw[0].split(",")
    content = raw[8:]
    data = []
    for li in content:
        line = li.split(",")
        year = int(line[0])
        month = int(line[1])
        day = int(line[2])
        hour = int(line[3]) - 1
        dir_norm = float(line[14])
        dif_hor = float(line[15])
        cc = float(line[19])
        aod = float(line[26])
        data.append(
            WeaData(datetime(year, month, day, hour, 30), dir_norm, dif_hor, cc, aod)
        )
    city = epw_header[1]
    country = epw_header[3]
    latitude = float(epw_header[6])
    longitude = -1 * float(epw_header[7])
    tz = int(float(epw_header[8])) * (-15)
    elevation = float(epw_header[9].rstrip())
    meta_data = WeaMetaData(city, country, latitude, longitude, tz, elevation)
    return meta_data, data


def parse_igsdb_json(json_obj: dict) -> PaneProperty:
    """Parse a JSON file from IGSDB."""
    name = json_obj["name"].replace(" ", "_")
    gtype = json_obj["type"]
    coated_side = json_obj["coated_side"].lower()
    thickness = json_obj["measured_data"]["thickness"]
    spectral_data = json_obj["spectral_data"]["spectral_data"]

    wavelength = []
    transmittance = []
    reflectance_front = []
    reflectance_back = []

    for row in spectral_data:
        wavelength.append(row["wavelength"] * 1e3)  # um to nm
        transmittance.append(row["T"])
        reflectance_front.append(row["Rf"])
        reflectance_back.append(row["Rb"])
    return PaneProperty(
        name,
        thickness,
        gtype,
        coated_side,
        wavelength,
        transmittance,
        reflectance_front,
        reflectance_back,
    )


def parse_optics(fpath) -> PaneProperty:
    """Read and parse an optics file."""
    # enc = 'cp1250' #decoding needed to parse header
    with open(fpath, errors="ignore") as rdr:
        raw = rdr.read()
    header_lines = [i for i in raw.splitlines() if i.startswith("{")]
    if header_lines == []:
        raise Exception("No header in optics file")
    header = {}
    for line in header_lines:
        if line.strip().split("}")[-1] != "":
            key = re.search("{(.*?)}", line).group(1).strip()
            val = line.split("}")[-1].strip()
            header[key] = val
        elif line:
            content = re.search("{(.*?)}", line).group(1).strip()
            if content != "":
                key = content.split(":")[0].strip()
                val = content.split(":")[1].strip()
                header[key] = val
    name = header["Product Name"].replace(" ", "_")
    thickness = float(header["Thickness"])
    gtype = header["Type"]
    coated_side = header["Coated Side"].lower()
    data = [i.split() for i in raw.strip().splitlines() if not i.startswith("{")]
    wavelength = [float(row[0]) for row in data]
    transmittance = [float(row[1]) for row in data]
    reflectance_front = [float(row[2]) for row in data]
    reflectance_back = [float(row[3]) for row in data]
    if header["Units, Wavelength Units"] == "SI Microns":  # um to nm
        wavelength = [val * 1e3 for val in wavelength]
    return PaneProperty(
        name,
        thickness,
        gtype,
        coated_side,
        wavelength,
        transmittance,
        reflectance_front,
        reflectance_back,
    )


def parse_polygon(real_args: Sequence[Union[int, float]]) -> geom.Polygon:
    """Parse real arguments to polygon.
    Args:
        primitive: a dictionary object containing a primitive

    Returns:
        modified primitive
    """
    coords = real_args
    arg_cnt = len(real_args)
    vertices = [geom.Vector(*coords[i : i + 3]) for i in range(0, arg_cnt, 3)]
    return geom.Polygon(vertices)


def parse_rad_header(header_str: str) -> tuple:
    """Parse a Radiance matrix file header.

    Args:
        header_str(str): header as string
    Returns:
        A tuple contain nrow, ncol, ncomp, datatype
    Raises:
        ValueError if any of NROWs NCOLS NCOMP FORMAT is not found.
        (This is problematic as it can happen)
    """
    compiled = re.compile(
        r" NROWS=(.*) | NCOLS=(.*) | NCOMP=(.*) | FORMAT=(.*) ", flags=re.X
    )
    matches = compiled.findall(header_str)
    if len(matches) != 4:
        raise ValueError("Can't find one of the header entries.")
    nrow = int([mat[0] for mat in matches if mat[0] != ""][0])
    ncol = int([mat[1] for mat in matches if mat[1] != ""][0])
    ncomp = int([mat[2] for mat in matches if mat[2] != ""][0])
    dtype = [mat[3] for mat in matches if mat[3] != ""][0].strip()
    return nrow, ncol, ncomp, dtype


def parse_vu(vu_str: str) -> Optional[model.View]:
    """Parse view string into a View object.

    Args:
        vu_str: view parameters as a string

    Returns:
        A view object
    """

    if vu_str.strip() == "":
        return
    args_list = vu_str.strip().split()
    vparser = argparse.ArgumentParser()
    vparser = radparam.add_view_args(vparser)
    vparser.add_argument("-x", type=int)
    vparser.add_argument("-y", type=int)
    args, _ = vparser.parse_known_args(args_list)
    if args.vf is not None:
        args, _ = vparser.parse_known_args(
            args.vf.readline().strip().split(), namespace=args
        )
        args.vf.close()
    if None in (args.vp, args.vd):
        raise ValueError("Invalid view")
    view = model.View(
        position=args.vp,
        direction=args.vd,
        vtype=args.vt[-1],
        horiz=args.vh,
        vert=args.vv,
        vfore=args.vo,
        vaft=args.va,
        hoff=args.vs,
        voff=args.vl,
    )
    if args.x is not None:
        view.xres = args.x
    if args.y is not None:
        view.yres = args.y
    return view


def tokenize(inp: str) -> Generator[str, None, None]:
    """Generator for tokenizing a string that
    is seperated by a space or a comma.
    Args:
       inp: input string
    Yields:
        next token
    """
    tokens = re.compile(
        " +|[-+]?(\d+([.,]\d*)?|[.,]\d+)([eE][-+]?\d+)+|[\d*\.\d+]+|[{}]"
    )
    for match in tokens.finditer(inp):
        if match.group(0)[0] in " ,":
            continue
        yield match.group(0)


def parse_branch(token: Generator[str, None, None]) -> Any:
    """Prase tensor tree branches recursively by opening and closing curly braces.
    Args:
        token: token generator object.
    Return:
        children: parsed branches as nexted list
    """
    children = []
    while True:
        value = next(token)
        if value == "{":
            children.append(parse_branch(token))
        elif value == "}":
            return children
        else:
            children.append(float(value))


def parse_ttree(data_str: str) -> list:
    """Parse a tensor tree.
    Args:
        data_str: input data string
    Returns:
        A nested list that is the tree
    """
    tokenized = tokenize(data_str)
    if next(tokenized) != "{":
        raise ValueError("Tensor tree data not starting with {")
    return parse_branch(tokenized)


def get_nested_list_levels(nested_list: list) -> int:
    """Calculate the number of levels given a nested list."""
    return (
        isinstance(nested_list, list)
        and max(map(get_nested_list_levels, nested_list)) + 1
    )


class TensorTree:
    """The tensor tree object.
    Anisotropic tensor tree has should have 16 lists
    Attributes:
        parsed: parsed tensor tree object)
        depth: number of tree levels
    """

    def __init__(self, parsed) -> None:
        self.parsed = parsed
        self.depth = get_nested_list_levels(parsed)

    def lookup(self, xp, yp) -> list:
        """Traverses a parsed tensor tree (a nexted list) given a input position."""
        branch_idx = self.get_branch_index(xp, yp)
        quads = [self.parsed[i] for i in branch_idx]
        return [self.traverse(quad, xp, yp) for quad in quads]

    def get_leaf_index(self, xp, yp) -> range:
        if xp < 0:
            if yp < 0:
                return range(0, 4)
            return range(4, 8)
        if yp < 0:
            return range(8, 12)
        return range(12, 16)

    def get_branch_index(self, xp, yp) -> range:
        """Gets a set of index."""
        if xp < 0:
            if yp < 0:
                return range(0, 16, 4)
            return range(2, 16, 4)
        if yp < 0:
            return range(1, 16, 4)
        return range(3, 16, 4)

    def traverse(self, quad, xp, yp, n: int = 1) -> list:
        """Traverse a quadrant."""
        if len(quad) == 1:  # single leaf
            res = quad
        else:
            res = []
            # get x, y signage in relation to branches
            _x = xp + 1 / (2**n) if xp < 0 else xp - 1 / (2**n)
            _y = yp + 1 / (2**n) if yp < 0 else yp - 1 / (2**n)
            n += 1
            # which four branches to get? get index for them
            if n < self.depth:
                ochild = self.get_branch_index(_x, _y)
            else:
                ochild = self.get_leaf_index(_x, _y)
            sub_quad = [quad[i] for i in ochild]
            if all(isinstance(i, float) for i in sub_quad):
                res = sub_quad  # single leaf for each branch
            else:  # branches within this quadrant
                for sq in sub_quad:
                    if len(sq) > 4:  # there is another branch
                        res.append(self.traverse(sq, _x, _y, n=n))
                    else:  # just a leaf
                        res.append(sq)
        return res


def parse_wea(wea_str: str) -> Tuple[WeaMetaData, List[WeaData]]:
    """Parse a wea file in its entirety."""
    lines = wea_str.splitlines()
    place = lines[0].split(" ", 1)[1]
    lat = float(lines[1].split(" ", 1)[1])
    lon = float(lines[2].split(" ", 1)[1])
    tz = int(float(lines[3].split(" ", 1)[1]))
    ele = float(lines[4].split(" ", 1)[1])
    meta_data = WeaMetaData(place, "", lat, lon, tz, ele)
    year = datetime.today().year
    data = []
    for li in lines[6:]:
        if li.strip() == "":
            continue
        line = li.split()
        month = int(line[0])
        day = int(line[1])
        hours = float(line[2])
        hour = int(hours)
        minute = int((hours - hour) * 60)
        dir_norm = float(line[3])
        dif_hor = float(line[4])
        data.append(
            WeaData(datetime(year, month, day, hour, minute), dir_norm, dif_hor)
        )
    return meta_data, data
