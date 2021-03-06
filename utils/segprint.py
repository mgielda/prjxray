#!/usr/bin/env python3

import getopt, sys, os, json, re

flag_z = False
flag_b = False
flag_d = False
flag_D = False


def usage():
    print("Usage: %s [options] <bits_file> [segments/tiles]" % sys.argv[0])
    print("")
    print("  -z")
    print("    do not print a 'seg' header for empty segments")
    print("")
    print("  -b")
    print("    print bits outside of known segments")
    print("")
    print("  -d")
    print("    decode known segment bits and write them as tags")
    print("")
    print("  -D")
    print("    decode known segment bits and omit them in the output")
    print("")
    sys.exit(0)


try:
    opts, args = getopt.getopt(sys.argv[1:], "zbdD")
except:
    usage()

if len(args) == 0:
    usage()

for o, a in opts:
    if o == "-z":
        flag_z = True
    elif o == "-b":
        flag_b = True
    elif o == "-d":
        flag_d = True
    elif o == "-D":
        flag_D = True
    else:
        usage()

with open("%s/%s/tilegrid.json" % (os.getenv("XRAY_DATABASE_DIR"),
                                   os.getenv("XRAY_DATABASE")), "r") as f:
    new_grid = json.load(f)

# TODO: Migrate to new tilegrid format via library.
grid = {'tiles': new_grid, 'segments': {}}

for tile in grid['tiles'].values():
    if 'segment' in tile:
        segment = tile['segment']
        grid['segments'][segment] = {
            'baseaddr': [
                tile['baseaddr'],
                tile['offset'],
            ],
            'type': tile['segment_type'],
            'frames': tile['frames'],
            'words': tile['words'],
        }

bitdata = dict()

# print("Loading %s." % sys.argv[1])
with open(args[0], "r") as f:
    for line in f:
        line = line.split("_")
        frame = int(line[1], 16)
        wordidx = int(line[2], 10)
        bitidx = int(line[3], 10)

        if frame not in bitdata:
            bitdata[frame] = dict()

        if wordidx not in bitdata[frame]:
            bitdata[frame][wordidx] = set()

        bitdata[frame][wordidx].add(bitidx)

segbitsdb = dict()


def get_database(segtype):
    if segtype in segbitsdb:
        return segbitsdb[segtype]

    segbitsdb[segtype] = list()

    with open("%s/%s/segbits_%s.db" % (os.getenv("XRAY_DATABASE_DIR"),
                                       os.getenv("XRAY_DATABASE"), segtype),
              "r") as f:
        for line in f:
            line = line.split()
            segbitsdb[segtype].append(line)

    with open("%s/%s/segbits_int_%s.db" %
              (os.getenv("XRAY_DATABASE_DIR"), os.getenv("XRAY_DATABASE"),
               segtype[-1]), "r") as f:
        for line in f:
            line = line.split()
            segbitsdb[segtype].append(line)

    return segbitsdb[segtype]


def handle_segment(segname):
    if segname is None:
        segframes = dict()
        for segname, segdata in grid["segments"].items():
            framebase = int(segdata["baseaddr"][0], 16)
            for i in range(segdata["frames"]):
                if (framebase + i) not in segframes:
                    segframes[framebase + i] = set()
                for j in range(segdata["baseaddr"][1],
                               segdata["baseaddr"][1] + segdata["words"]):
                    segframes[framebase + i].add(j)
        for frame in sorted(bitdata.keys()):
            for wordidx in sorted(bitdata[frame].keys()):
                if frame in segframes and wordidx in segframes[frame]:
                    continue
                for bitidx in sorted(bitdata[frame][wordidx]):
                    print("bit_%08x_%03d_%02d" % (frame, wordidx, bitidx))
        return
    if ":" in segname:
        seg1, seg2 = segname.split(":")

        if seg1 in grid["tiles"]:
            seg1 = grid["tiles"][seg1]["segment"]

        if seg2 in grid["tiles"]:
            seg2 = grid["tiles"][seg2]["segment"]

        seginfo1 = grid["segments"][seg1]
        seginfo2 = grid["segments"][seg2]

        frame1 = int(seginfo1["baseaddr"][0], 16)
        word1 = int(seginfo1["baseaddr"][1])

        frame2 = int(seginfo2["baseaddr"][0], 16)
        word2 = int(seginfo2["baseaddr"][1])

        if frame1 > frame2:
            frame1, frame2 = frame2, frame1

        if word1 > word2:
            word1, word2 = word2, word1

        segs = list()

        for seg, seginfo in sorted(grid["segments"].items()):
            frame = int(seginfo["baseaddr"][0], 16)
            word = int(seginfo["baseaddr"][1])
            if frame1 <= frame <= frame2 and word1 <= word <= word2:
                segs.append((frame, word, seg))

        for _, _, seg in sorted(segs):
            handle_segment(seg)
        return

    if segname in grid["tiles"]:
        segname = grid["tiles"][segname]["segment"]

    seginfo = grid["segments"][segname]

    baseframe = int(seginfo["baseaddr"][0], 16)
    basewordidx = int(seginfo["baseaddr"][1])
    numframes = int(seginfo["frames"])
    numwords = int(seginfo["words"])

    segbits = set()
    segtags = set()

    for frame in range(baseframe, baseframe + numframes):
        if frame not in bitdata:
            continue
        for wordidx in range(basewordidx, basewordidx + numwords):
            if wordidx not in bitdata[frame]:
                continue
            for bitidx in bitdata[frame][wordidx]:
                segbits.add(
                    "%02d_%02d" %
                    (frame - baseframe, 32 * (wordidx - basewordidx) + bitidx))

    if flag_d or flag_D:
        for entry in get_database(seginfo["type"]):
            match_entry = True
            for bit in entry[1:]:
                if bit[0] != "!" and bit not in segbits:
                    match_entry = False
                if bit[0] == "!" and bit[1:] in segbits:
                    match_entry = False
            if match_entry:
                for bit in entry[1:]:
                    if bit[0] != "!":
                        segbits.remove(bit)
                if flag_d:
                    segtags.add(entry[0])

    if not flag_z or len(segbits) > 0 or len(segtags) > 0:
        print()
        print("seg %s" % segname)

    for bit in sorted(segbits):
        print("bit %s" % bit)

    for tag in sorted(segtags):
        print("tag %s" % tag)


if flag_b:
    handle_segment(None)

if len(args) == 1:
    seglist = list()
    for seg, seginfo in grid["segments"].items():
        seglist.append((seginfo["baseaddr"][0], -seginfo["baseaddr"][1], seg))
    for _, _, seg in sorted(seglist):
        handle_segment(seg)
else:
    for arg in args[1:]:
        handle_segment(arg)
