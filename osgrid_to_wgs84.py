#!/usr/bin/python
#
# Copyright (C) 2015 Dave Berkeley projects@rotwang.co.uk
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA

import csv
import sys

# import geo_helper, see http://gagravarr.org/code/
import geo_helper

# Convert National Grid letters to km.

grid = [
    [ 'V', 'W', 'X', 'Y', 'Z' ],
    [ 'Q', 'R', 'S', 'T', 'U' ],
    [ 'L', 'M', 'N', 'O', 'P' ],
    [ 'F', 'G', 'H', 'J', 'K' ],
    [ 'A', 'B', 'C', 'D', 'E' ],
]

def cell_to_xy(cell):
    for y in range(5):
        if cell in grid[y]:
            x = grid[y].index(cell)
            return x, y
    raise ValueError

def grid_to_xy(area):
    x1, y1 = cell_to_xy(area[0])
    x2, y2 = cell_to_xy(area[1])
    return (100 * (x2 + (5 * (x1 - 2)))), (100 * (y2 + (5 * (y1 - 1))))

def osref_to_en(osref):
    region, osref = osref[:2], osref[2:]
    if region == "AA":
        return 0.0, 0.0
    digits = len(osref)/2
    east, north = osref[:digits], osref[digits:]
    # get "XX" region in km east,north
    e, n = grid_to_xy(region)
    # convert to km. Digits ABCDE.. are 10km, 1km, 100m, 10m, 1m, ...
    if digits == 4:
        div = 100.0
    elif digits == 3:
        div = 10.0
    elif digits == 2:
        div = 1.0
    east, north = [ (int(x,10)/div) for x in [ east, north ] ]
    # full OS grid ref east, northings in metres
    e, n = 1000 * (e + east), 1000 * (n + north)
    return e, n

    # in the form "SXxxxyyy"
    grid, e, n = osref[:2], int(osref[2:5], 10), int(osref[5:], 10)
    xx, yy = grid_to_xy(grid)
    return (xx*10) + e, (yy*10) + n

#
#

def convert(osref):
    """ Converts n figure OS Grid reference into WGS84 lat/lon """
    # full OS grid ref east, northings in metres
    e, n = osref_to_en(osref)
    # convert to OSGB36
    la, lo = geo_helper.turn_eastingnorthing_into_osgb36(e, n)
    # convert to WGS84
    lat, lon, h = geo_helper.turn_osgb36_into_wgs84(la, lo, 0.0)
    return lat, lon

def wgs84_to_en(lat, lon):
    # convert to OSGB36
    lat, lon, h = geo_helper.turn_wgs84_into_osgb36(lat, lon, 0.0)
    # convert to OS eastings, northings in metres
    e, n = geo_helper.turn_osgb36_into_eastingnorthing(lat, lon)
    return e, n

def osgb36_to_wgs84(lat, lon):
    lat, lon, h = geo_helper.turn_osgb36_into_wgs84(lat, lon, 0.0)
    return lat, lon

# FIN
