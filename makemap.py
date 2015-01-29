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

import sys
import os
import math
import zipfile

import Image, ImageChops, ImageDraw

from osgrid_to_wgs84 import osref_to_en, wgs84_to_en

import pc

#
#   Set map scaling

MAP_SCALE = 100

def scale_en(e, n):
    return [ int(x/MAP_SCALE) for x in (e,n) ]

#
#   Histogram Normalisation

class Hist:

    def __init__(self, max_pixel=255):
        self.vals = {}
        self.maxval = 0
        self.lut = None
        self.num_points = 0
        self.max_pixel = max_pixel

    def add(self, value):
        if not self.vals.get(value):
            self.vals[value] = 1
        else:
            v = self.vals[value] + 1
            self.vals[value] = v
            if v > self.maxval:
                self.maxval = v

        self.num_points += 1

    def colour(self, value):
        if self.lut is None:
            # cumulative density function
            cdf = {}
            keys = sorted(self.vals.keys())
            total = 0
            for key in keys:
                total += self.vals[key]
                cdf[key] = total
            # scale cdf to max_pixel
            for key, value in cdf.items():
                cdf[key] = int(value * self.max_pixel / float(total))
            assert total == self.num_points
            self.lut = cdf

        return self.lut.get(value, 0)

#
#   Make map of postcode distribution

def pc_map():
    pc.init(pcdb=True, gazdb=False)

    points = []

    def callback(idx, *record):
        postcode, lat, lon, osref = record
        if '\0' in osref:
            return
        e, n = osref_to_en(osref)
        e, n = scale_en(e, n)
        points.append((e, n))

    print >> sys.stderr, "reading all points"
    path = pc.get_db_name()
    pc.visit(path, callback)

    print >> sys.stderr, "count points"
    gb = {}
    for x, y in points:
        if not gb.get((x,y)):
            gb[(x,y)] = 1
        else:
            v = gb[(x,y)] + 1
            gb[(x,y)] = v

    print >> sys.stderr, "make histogram"
    hist = Hist()
    for (x, y), num in gb.items():
        if num:
            hist.add(num)

    print >> sys.stderr, "set colours"
    uk = Map()
    points = []
    for (x, y), num in gb.items():
        col = hist.colour(num)
        points.append((x, y, (col,col,col)))

    uk.plotc(points)

    return uk.gb

#
#   Search gaz for matching places, plot on map

def gaz_map(search, colour):
    print >> sys.stderr, "make gaz map '%s'" % search
    pc.init(pcdb=False, gazdb=True)
    print >> sys.stderr, "search gaz"
    places = pc.search_gaz(search)
    points = []
    for name, os4, county in places:
        e, n = osref_to_en(os4)
        e, n = scale_en(e, n)
        if n < 0:
            continue
        points.append((e, n))

    gb = Map()
    gb.plot(points, colour)
    return gb


def save_map(im, path):
    print >> sys.stderr, "save map", path
    im.save(path)

#
#   County Map

county_map_base = '/tmp/.postcode/county'

def make_county_db():
    # see http://www.nearby.org.uk/counties/
    # http://www.nearby.org.uk/counties/ZipFiles/BICountyBoundaryWGS84.zip
    # copied to /usr/local/data/books/BICountyBoundaryWGS84.zip

    base = county_map_base
    if os.path.exists(base):
        return base

    src = '/usr/local/data/books/BICountyBoundaryWGS84.zip'
    z = zipfile.ZipFile(src, "r")
    names = z.namelist()
    paths = []
    for name in names:
        if name.endswith("ALL.txt"):
            paths.append(name)

    for path in paths:
        xpath = z.extract(path, base)
        print >> sys.stderr, "unzip", xpath
    return base

#
#   Bound the UK map in OS e/n refs (/10)

def get_uk_map_bounds():
    # Frame the UK
    mine, maxe = scale_en(4000, 660000)
    minn, maxn = scale_en(5000, 1220000)
    return mine, maxe, minn, maxn

#
#   Make map of county boundaries

def make_county_map(colour):
    mine, maxe, minn, maxn = get_uk_map_bounds()

    base = make_county_db()
    gb = Map()

    for fname in os.listdir(base):
        points = []
        if not fname.endswith("ALL.txt"):
            continue
        path = os.path.join(base, fname)
        print >> sys.stderr, path

        for line in file(path):
            line = line.strip()
            if line.startswith("#"):
                continue
            if not line:
                gb.plot_lines(points, colour)
                points = []
                continue
            lat, lon = [ float(x) for x in line.split(",") ]
            e, n = wgs84_to_en(lat, lon)
            e, n = scale_en(e, n)
            if mine <= e <= maxe:
                if minn <= n <= maxn:
                    points.append((e, n))

        gb.plot_lines(points, colour)

    return gb.gb

#
#   Make, or loaded cached map of county boundaries

def county_map(colour):
    colstr = str(colour).replace(" ","")
    scale = MAP_SCALE
    name = "county_%s_%s.png" % (colstr, scale)
    path = os.path.join('/tmp', name)
    if os.path.exists(path):
        print >> sys.stderr, "loading", path
        im = Image.open(path)
        return im
    im = make_county_map(colour)
    print >> sys.stderr, "saving", path
    im.save(path)
    return im

#
#   Make a UK map from EN points

class Map:

    def __init__(self):
        self.mine, self.maxe, self.minn, self.maxn = get_uk_map_bounds()

        dx = self.makex(self.maxe) - self.makex(self.mine)
        dy = self.makey(self.minn) - self.makey(self.maxn)

        self.gb = Image.new("RGB", (dx, dy))

    def makex(self, e):
        return int(e - self.mine) / 10

    def makey(self, n):
        return int(self.maxn - n) / 10

    def plot_lines(self, points, colour):
        if not points:
            return
        print >> sys.stderr, "plot lines", len(points)

        draw = ImageDraw.Draw(self.gb)
        prev = None
        for e, n in points:
            x = self.makex(e)
            y = self.makey(n)
            if prev is None:
                prev = x, y
                continue

            draw.line(prev + (x, y), fill=colour)
            prev = x, y

    def plot(self, points, colour):
        print >> sys.stderr, "plot points", len(points)
        for e, n in points:
            x = self.makex(e)
            y = self.makey(n)
            try:
                self.gb.putpixel((x, y), colour)
            except IndexError, ex:
                print >> sys.stderr, str(ex)

    def plotc(self, points):
        print >> sys.stderr, "plot colour points", len(points)
        for e, n, colour in points:
            x = self.makex(e)
            y = self.makey(n)
            try:
                self.gb.putpixel((x, y), colour)
            except IndexError, ex:
                print >> sys.stderr, str(ex)

#
#

if __name__ == "__main__":
    if len(sys.argv) == 2:
        if sys.argv[1] == 'postcode':
            image = pc_map()
            save_map(image, "map.png")
            sys.exit()

    county_colour = 0, 0, 96
    image = county_map(county_colour)

    colours = (
        (255,255,255),
        (255,0,0),
        (0,255,0),
        (128,128,0),
    )
    colour_idx = 0

    for regex in sys.argv[1:]:
        im = gaz_map(regex, colours[colour_idx])
        if image is None:
            image = im.gb
        else:
            image = ImageChops.add(image, im.gb)
        colour_idx = (colour_idx + 1) % len(colours)

    save_map(image, "map.png")

# FIN
