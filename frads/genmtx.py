"""
Command-line tool for generating matrices for different scenarios.
TWang
"""

import argparse
import logging
import shutil
from frads import radmtx as rm
from frads import radutil


def genmtx_args(parser):
    parser.add_argument('-st', choices=['s','v','p'], required=True, help='Sender object type')
    parser.add_argument('-s', help='Sender object')
    parser.add_argument('-r', nargs='+', required=True, help='Receiver objects')
    parser.add_argument('-i', help='Scene octree file path')
    parser.add_argument('-o', nargs='+', required=True, help='Output file path | directory')
    parser.add_argument('-mod', help='modifier path for sun sources')
    parser.add_argument('-env', nargs='+', default='', help='Environment file paths')
    parser.add_argument('-rs', required=True, choices=['r1','r2','r4','r6','kf','sc25'],
                        help='Receiver sampling basis, kf|r1|r2|....')
    parser.add_argument('-ss', help='Sender sampling basis, kf|r1|r2|....')
    parser.add_argument('-ro', type=float,
                        help='Move receiver surface in normal direction')
    parser.add_argument('-so', type=float,
                        help='Move sender surface in normal direction')
    parser.add_argument('-opt', type=str, default='-ab 1', help='Simulation parameters')
    parser.add_argument('-rc', type=int, default=1, help='Ray count')
    parser.add_argument('-xres', type=int, help='X resolution')
    parser.add_argument('-yres', type=int, help='Y resolution')
    parser.add_argument('-smx', help='Sky matrix file path')
    parser.add_argument('-wpths', nargs='+', help='Windows polygon paths')
    parser.add_argument('-v', '--verbose', action='count', default=0, help='verbose mode')
    return parser


def main():
    """Generate a matrix."""
    parser = argparse.ArgumentParser()
    genmtx_parser = genmtx_args(parser)
    args = genmtx_parser.parse_args()
    argmap = vars(args)
    logger = logging.getLogger('frads')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    _level = args.verbose * 10
    logger.setLevel(_level)
    console_handler.setLevel(_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    assert len(argmap['r']) == len(argmap['o'])
    # what's the environment
    env = ' '.join(argmap['env'])
    if argmap['i'] is not None:
        env = "{} -i {}".format(env, argmap['i'])
    # what's the sender
    with open(argmap['s']) as rdr:
        sndrlines = rdr.readlines()
    if argmap['st'] == 's':
        prim_list = radutil.parse_primitive(sndrlines)
        sender = rm.Sender.as_surface(prim_list=prim_list, basis=argmap['ss'], offset=argmap['so'])
    elif argmap['st'] == 'v':
        vudict = radutil.parse_vu(sndrlines[-1]) # use the last view from a view file
        sender = rm.Sender.as_view(vu_dict=vudict, ray_cnt=argmap['rc'],
                                   xres=argmap['xres'], yres=argmap['yres'])
    elif argmap['st'] == 'p':
        pts_list = [l.split() for l in sndrlines]
        sender = rm.Sender.as_pts(pts_list=pts_list, ray_cnt=argmap['rc'])
    # figure out receiver
    if argmap['r'][0] == 'sky':
        receiver = rm.Receiver.as_sky(argmap['rs'])
        argmap['o'] = argmap['o'][0]
    elif argmap['r'][0] == 'sun':
        receiver = rm.Receiver.as_sun(basis=argmap['rs'], smx_path=argmap['smx'],
                                      window_paths=argmap['wpths'])
    else: # assuming multiple receivers
        rcvr_prims = []
        for path in argmap['r']:
            with open(path) as rdr:
                rlines = rdr.readlines()
            rcvr_prims.extend(radutil.parse_primitive(rlines))
        modifiers = set([prim['modifier'] for prim in rcvr_prims])
        receiver = rm.Receiver(receiver='', basis=argmap['rs'], modifier=None)
        for mod, op in zip(modifiers, argmap['o']):
            _receiver = [prim for prim in rcvr_prims
                         if prim['modifier'] == mod and prim['type'] in ('polygon', 'ring') ]
            if _receiver != []:
                receiver += rm.Receiver.as_surface(
                    prim_list=_receiver, basis=argmap['rs'], offset=argmap['ro'],
                    left=None, source='glow', out=op)
        argmap['o'] = None
    # generate matrices
    if argmap['r'][0] == 'sun':
        sun_oct = 'sun.oct'
        rm.rcvr_oct(receiver, argmap['env'], sun_oct)
        rm.rcontrib(sender=sender, modifier=receiver.modifier, octree=sun_oct,
                   out=argmap['o'], opt=argmap['opt'])
    else:
        res = rm.rfluxmtx(sender=sender, receiver=receiver, env=argmap['env'], opt=argmap['opt'])
        with open(argmap['o'], 'wb') as wtr:
            wtr.write(res)

