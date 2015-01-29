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
import csv
import struct
import os
import bz2
import zipfile
import re
import optparse

from osgrid_to_wgs84 import convert as to_wgs84
from osgrid_to_wgs84 import osgb36_to_wgs84

pcpath = "/usr/local/data/books/uk-post-codes-2009.bz2"
gazpath = "/usr/local/data/books/gaz50k2014_gb.zip"

fmt = "=8sdd8s"

cache_base = "/tmp/.postcode/"
txt_name = "pc.csv"
db_name = "pc.dat"
lat_name = "lat.dat"
lon_name = "lon.dat"
os_name = "os.dat"
gaz_name = "gaz"
county_name = "gaz.county.dat"

#
#   Make db and index files

def get_name(other):
    return os.path.join(cache_base, other)

def get_db_name():
    return get_name(db_name)

#
#   Decompress the bz2 source into a csv file.

def make_txt(opath):
    if not os.path.exists(cache_base):
        print >> sys.stderr, "mkdir", cache_base
        os.mkdir(cache_base)

    # bunzip2 <src.bz2>
    print >> sys.stderr, "creating", opath
    ifile = open(pcpath, "rb")
    ofile = open(opath, "wb")
    decompressor = bz2.BZ2Decompressor()

    BLOCK = 1024
    while True:
        data = ifile.read(BLOCK)
        if not data:
            break
        decom = decompressor.decompress(data)
        ofile.write(decom)
    ifile.close()
    ofile.close()

#
#   Create a binary file : "postcode", lat, lon
#   sorted by postcode.

def make_db(ipath, opath):
    if not os.path.exists(ipath):
        make_txt(ipath)

    f = open(ipath, "r")
    reader = csv.reader(f, delimiter=",")
    data = []

    print >> sys.stderr, "reading %s ..." % ipath

    # skip the header
    reader.next()

    for row in reader:
        pc = row[0]

        if pc.startswith("GIR"):
            continue # ignore this weird one

        lat, lon = [ float(x) for x in row[13:15] ]

        # lots of entries have no location data in ... yet
        if (lon == 0.0) and (lat == 0.0):
            continue

        # OS reference in form XX1234512345
        osref = row[15]
        # Keep the 6-figure part
        osref = osref[:5] + osref[7:10]
        # lat,lon are in OSGB36, so convert to WGS84
        #lat, lon = osgb36_to_wgs84(lat, lon)
        data.append((pc, lat, lon, osref))

    print >> sys.stderr, "sorting ..."

    data.sort()

    print >> sys.stderr, "writing %s ..." % opath
    ofile = open(opath, "wb")

    for pc, lon, lat, osref in data:
        binary = struct.pack(fmt, pc, lat, lon, osref)
        ofile.write(binary)

    ofile.close()

#
#

fmt_idx = "=dI"

def make_idx_db(path, lat_path, lon_path):

    class Index:
        def __init__(self):
            self.data = []

        def lat_fn(self, idx, pc, lat, lon, osref):
            self.data.append((lat, idx))

        def lon_fn(self, idx, pc, lat, lon, osref):
            self.data.append((lon, idx))

        def write(self, path):
            self.data.sort()
            fout = open(path, "wb")
            for coord, idx in self.data:
                binary = struct.pack(fmt_idx, coord, idx)
                fout.write(binary)
            fout.close()

    print >> sys.stderr, "Making", lat_path
    data = Index()
    visit(path, data.lat_fn)
    data.write(lat_path)

    print >> sys.stderr, "Making", lon_path
    data = Index()
    visit(path, data.lon_fn)
    data.write(lon_path)

def get_record_idx(ifile, idx):
    itemsize = struct.calcsize(fmt_idx)
    ifile.seek(idx * itemsize)
    blob = ifile.read(itemsize)
    return struct.unpack(fmt_idx, blob)

#
#   Make index for OS map reference

fmt_os = "=8sI"

def make_os_db(path, os_path):

    class Index:
        def __init__(self):
            self.data = []

        def handler(self, idx, pc, lat, lon, osref):
            if osref[0]:
                self.data.append((osref, idx))

        def write(self, path):
            self.data.sort()
            fout = open(path, "wb")
            for osref, idx in self.data:
                binary = struct.pack(fmt_os, osref, idx)
                fout.write(binary)
            fout.close()

    print >> sys.stderr, "Making", os_path
    data = Index()
    visit(path, data.handler)
    data.write(os_path)

#
#   Read OS gazeteer and create db

idx_fmt = "=IIH6s"

def make_gaz_db(path):
    if os.path.exists(path + ".idx"):
        return

    z = zipfile.ZipFile(gazpath, "r")
    names = z.namelist()
    data = None
    for name in names:
        if name.startswith("data/"):
            if name.endswith(".txt"):
                data = name

    print >> sys.stderr, "unzip", gazpath
    gaz_text_path = z.extract(data, cache_base)

    print >> sys.stderr, "reading", gaz_text_path

    ftext = open(path + ".txt", "wb")
    fidx = open(path + ".idx", "wb")

    f = open(gaz_text_path, "r")
    reader = csv.reader(f, delimiter=":")
    offset = 0
    data = []
    county_idx = {}
    counties = []
    print >> sys.stderr, "create gaz db"
    for row in reader:
        osref, text = row[1], row[2]

        # county index
        county = row[13]
        if county_idx.get(county) is None:
            county_idx[county] = len(counties)
            counties.append(county)

        # ditch the dual-language stuff
        text = text.split("/", 1)[0]

        ftext.write(text)
        data.append((text, offset, osref, county_idx[county]))

        offset += len(text)

    print >> sys.stderr, "sorting gaz"
    data.sort()
    print >> sys.stderr, "create gaz index"
    for idx, (text, offset, osref, cidx) in enumerate(data):
        length = len(text)
        raw = struct.pack(idx_fmt, cidx, offset, length, osref)
        fidx.write(raw)

    print >> sys.stderr, "remove", gaz_text_path
    f.close()
    os.unlink(gaz_text_path)

    print >> sys.stderr, "write county db"
    f = open(get_name(county_name), "wb")
    f.write("\0".join(counties))
    f.close()

#
#

def can_binary_search(match):
    # return True if regex is just at end of match, or not at all
    regex_chars = ".*?[]+{}"
    # TODO :
    if not any((c in regex_chars) for c in match):
        return True
    return False

#
#   Search the gaz for a name

class GazMatcher:

    def __init__(self, ftxt, name, itemsize, records):
        self.ftxt = ftxt
        self.itemsize = itemsize
        self.records = records
        self.last = None
        self.name = name

    def match(self, idx, *record):
        place = record[0]
        #print idx, self.name, place
        if re.match(self.name, place):
            return 0

        if self.name < place:
            return 1
        return -1

    def get(self, fidx, idx):
        fidx.seek(self.itemsize * idx)
        raw = fidx.read(self.itemsize)
        county_idx, offset, length, osref = struct.unpack(idx_fmt, raw)
        county = county_data[county_idx]

        self.ftxt.seek(offset)
        placename = self.ftxt.read(length)
        result = (placename, osref, county)
        self.last = (idx,) + result
        return result

#
#

def search_gaz_re(fidx, matcher, name):

    data = []
    # Iterate through the whole db
    for idx in range(0, matcher.records):
        record = matcher.get(fidx, idx)
        if matcher.match(idx, *record) == 0:
            data.append(record)

    return data

def search_gaz(name):
    idx_path = get_name(gaz_name + ".idx")
    txt_path = get_name(gaz_name + ".txt")

    itemsize = struct.calcsize(idx_fmt)
    records = os.path.getsize(idx_path) / itemsize

    fidx = open(idx_path, "rb")
    ftxt = open(txt_path, "rb")

    if not can_binary_search(name):
        matcher = GazMatcher(ftxt, name, itemsize, records)
        return search_gaz_re(fidx, matcher, name)

    class Matcher(GazMatcher):
        def match(self, idx, *record):
            place = record[0]
            #print idx, self.name, place
            part = place[:len(self.name)]
            if part == self.name:
                return 0
            if self.name < place:
                return 1
            return -1

    matcher = Matcher(ftxt, name, itemsize, records)

    result = binary_search(fidx, 0, records, matcher.match, matcher.get)
    # get result or nearest match
    if not result:
        return None
        #result = matcher.last
    idx, place, osref, county = result

    # search for any other places with the same name
    idxs = search_adjacent(fidx, records, idx, matcher.match, matcher.get)

    data = []
    for idx in idxs:
        record = matcher.get(fidx, idx)
        data.append(record)

    return data

#
#   find all the (adjacent) matching records 

def search_adjacent(fin, max_records, idx, matcher, get_record):
    idxs = [ idx ]
    # look backwards
    for i in range(idx-1, -1, -1):
        record = get_record(fin, i)
        if matcher(0, *record) == 0:
            idxs.append(i)
        else:
            break
    # look forwards
    for i in range(idx+1, max_records):
        record = get_record(fin, i)
        if matcher(0, *record) == 0:
            idxs.append(i)
        else:
            break

    idxs.sort()
    return idxs

#
#

def search_os(match):
    os_path = get_name(os_name)
    itemsize = struct.calcsize(fmt_os)
    records = os.path.getsize(os_path) / itemsize
    fin = open(os_path, "rb")

    def matcher(idx, *record):
        osref, idxdb = record
        if match == osref:
            return 0;
        if match < osref:
            return 1
        return -1
    def get_record(fin, idx):
        fin.seek(idx * itemsize)
        blob = fin.read(itemsize)
        return struct.unpack(fmt_os, blob)

    # find any matching record
    found, osref, idxb = binary_search(fin, 0, records, matcher, get_record)

    idxs = search_adjacent(fin, records, found, matcher, get_record)
    data = []
    for i in idxs:
        record = get_record(fin, i)
        osref, idxdb = record
        data.append(idxdb)

    return data

#
#   Create any database and index files

county_data = None

def make_all(pcdb, gazdb):
    txt_path = get_name(txt_name)
    path = get_db_name()

    if pcdb:
        # create the main db
        if not os.path.exists(path):
            make_db(txt_path, path)
            # don't need the csv file any more ..
            print >> sys.stderr, "Removing", txt_path 
            os.remove(txt_path)

        lat_path = get_name(lat_name)
        lon_path = get_name(lon_name)
        if not os.path.exists(lat_path):
            make_idx_db(path, lat_path, lon_path)

        os_path = get_name(os_name)
        if not os.path.exists(os_path):
            make_os_db(path, os_path)

    if gazdb:
        gaz_path = get_name(gaz_name)
        if not os.path.exists(gaz_path):
            make_gaz_db(gaz_path)

        global county_data
        f = open(get_name(county_name), "rb")
        raw = f.read()
        county_data = raw.split("\0")
        f.close()

#
# binary search on records

def get_record(fin, idx):
    # load the record at idx
    itemsize = struct.calcsize(fmt)
    offset = idx * itemsize
    fin.seek(offset)
    blob = fin.read(itemsize)
    pc, lat, lon, osref = struct.unpack(fmt, blob)
    pc = pc[:7]
    return pc, lat, lon, osref

def num_records(path):
    itemsize = struct.calcsize(fmt)
    fsize = os.path.getsize(path)
    return fsize / itemsize

#
#   Generic visitor function

def visit(path, callback, num_records=num_records, get_record=get_record):
    records = num_records(path)
    fin = open(path, "rb")
    for idx in range(records):
        record = get_record(fin, idx)
        callback(idx, *record)

#
#

def binary_search(fin, start, end, match_fn, get_record_fn):
    if start == end:
        return None

    idx = (start + end) / 2
    record = get_record_fn(fin, idx)

    compare = match_fn(idx, *record)
    if compare == 0:
        return (idx,) + record
    if compare < 0:
        return binary_search(fin, idx+1, end, match_fn, get_record_fn)
    else:
        return binary_search(fin, start, idx, match_fn, get_record_fn)

#
#

def find_coord(path, coord):
    itemsize = struct.calcsize(fmt_idx)
    fsize = os.path.getsize(path)
    records = fsize / itemsize

    class CoordMatcher:
        def __init__(self):
            self.last = None
        def match(self, idx, co, data):
            self.last = idx, co, data
            if co == coord:
                return 0
            if co < coord:
                return -1
            return 1;

    matcher = CoordMatcher()
    fin = open(path, "r")
    binary_search(fin, 0, records, matcher.match, get_record_idx)
    fin.close()
    # return the last item checked, even if no match was found
    return matcher.last

#
#   Return the idx into the db for a range of lon / lat values

def between(path, lo, hi):
    slo = find_coord(path, lo)[0]
    shi = find_coord(path, hi)[0]

    idxs = []
    fin = open(path, "r")
    for idx in range(slo, shi+1):
        coord, db = get_record_idx(fin, idx)
        idxs.append(db)
    fin.close()
    return idxs

#
#

def search(match):
    path = get_db_name()

    def match_fn(idx, pc, lat, lon, osref):
        if pc == match:
            return 0;
        if pc < match:
            return -1
        return 1

    records = num_records(path)
    fin = open(path, "r")
    found = binary_search(fin, 0, records, match_fn, get_record)
    fin.close()
    return found

#
#   Get the db indexes for a bounded region

def get_range(lat_lo, lat_hi, lon_lo, lon_hi):
    lat_path = get_name(lat_name)
    lon_path = get_name(lon_name)
    lats = between(lat_path, lat_lo, lat_hi)
    lons = between(lon_path, lon_lo, lon_hi)

    lons = set(lons)
    lats = set(lats)
    idxs = lons.intersection(lats)

    return idxs

#
#

def get_nearest(lat, lon, margin=None, find=None):

    # search a square for extant postcodes
    if margin is None:
        marg = 0.0002
    else:
        marg = margin

    while True:
        #print "search", margin
        idxs = get_range(lat-marg, lat+marg, lon-marg, lon+marg)
        if find:
            if len(idxs) >= find:
                return idxs
        else:
            if idxs:
                break
        # none found, so increase the search area
        marg += marg

    return idxs

#
#   use for eg. http://www.openstreetmap.org/#map=14/51.0640/-1.7820

def open_street_map(lat, lon, zoom=14):
    return "http://www.openstreetmap.org/#map=%d/%f/%f" % (zoom, lat, lon)

def google_maps(lat, lon, zoom=15):
    maptype="m" # m=map, s=sat, h=hybrid
    url = "http://maps.google.com/maps?hl=en&ie=UTF8&z=%d&ll=%f,%f&t=%s"
    return url % (zoom, lat, lon, maptype) # TODO : check this 

#
#   Convert into 7-char form used in database

class BadPostcode(Exception):
    pass

re_pc = re.compile("([A-Z][A-Z]?(?:\d\d?|\d[A-Z])) ? ?(\d\d?[A-Z][A-Z])")

def to7pc(pc):
    # convert postcode into 7-char format
    match = re_pc.match(pc.upper())
    try:
        a, b = match.groups()
        assert len(b) == 3
    except:
        raise BadPostcode(pc)

    pc = a
    # pad the first part with spaces
    pc += ' ' * (4 - len(a))
    pc += b
    assert len(pc) == 7
    return pc

#
#   Convert OS 4-figure to 6-figure

def os4to6(osref):
    return osref[:4] + "0" + osref[4:] + "0"

#
#

def init(pcdb=True, gazdb=True):
    make_all(pcdb, gazdb)

#
#

if __name__ == "__main__":

    p = optparse.OptionParser()
    p.add_option("-g", "--gaz", dest="gaz")
    p.add_option("-p", "--postcode", dest="postcode")
    p.add_option("-l", "--location", dest="location")
    p.add_option("-o", "--osref", dest="osref")
    p.add_option("-m", "--margin", dest="margin", type="float")
    p.add_option("-f", "--find", dest="find", type="int")

    opts, args = p.parse_args()

    init()

    path = get_db_name()
    pc = opts.postcode

    def show(idxs):
        ifile = open(path, "rb")
        for idx in idxs:
            r = get_record(ifile, idx)
            print idx, r

    if opts.gaz:
        print "find gaz", opts.gaz
        places = search_gaz(opts.gaz)

        if places:
            for place, osref4, county in places:
                osref = os4to6(osref4)
                lat, lon = to_wgs84(osref)
                print "found", place, osref, lat, lon, county
                print " ", open_street_map(lat, lon)

    is_lat_lon = False
    if opts.location:
        lat, lon = [ float(x) for x in opts.location.split(",") ]
        is_lat_lon = True

    if opts.osref:
        lat, lon = to_wgs84(opts.osref)
        print opts.osref, "is", lat, lon
        is_lat_lon = True

        print "search_os"
        print search_os(opts.osref)

    if is_lat_lon:
        print "get nearest", lat, lon
        idxs = get_nearest(lat, lon, margin=opts.margin, find=opts.find)
        print idxs
        show(idxs)

    if opts.postcode:
        _, pc, lat, lon, osref = search(to7pc(pc))
        print open_street_map(lat, lon)
        print osref

        if opts.margin:
            margin = opts.margin
        else:
            margin = 0.001
        idxs = get_range(lat-margin, lat+margin, lon-margin, lon+margin)

        print "nearby", lat, lon
        show(idxs)

# FIN
