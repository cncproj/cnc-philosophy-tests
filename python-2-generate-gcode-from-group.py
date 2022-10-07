#!/usr/bin/env python
# generate-gcode-from-group.py


from xml.dom import minidom
from svg.path import parse_path as svg_parse_path
from svg.path.path import Line, Move


def read_svg_file(svg_file):
    doc = minidom.parse(svg_file)  # parseString also exists
    return doc

def get_all_paths(doc):
    paths = doc.getElementsByTagName('path')
    return paths
    #path_strings = [path.getAttribute('d') for path
    #                in paths]
    #doc.unlink()

def get_all_groups(doc):
    grps = doc.getElementsByTagName('g')
    return grps


def parse_svg_file(svg_file):
    doc = read_svg_file(svg_file)
    all_pths = get_all_paths(doc)
    all_grps = get_all_groups(doc)

    all_path_strings = {}
    all_path_ids = []
    for path in all_pths:
        pth_id = path.getAttribute('id')
        all_path_strings[ pth_id ] = path.getAttribute('d')
        all_path_ids.append(pth_id)

    grp_strings = [ [group.getAttribute('id'), group.getAttribute('d')] for group in all_grps ]

    # paths in a group: only one cutting-group
    gpths_initial = [ get_all_paths( x ) for x in all_grps ]
    group_path_strings = None
    group_path_ids = None
    for gpth in gpths_initial:
        if len(gpth) > 0:
            if group_path_strings is None:
                group_path_strings = {}
                group_path_ids = []
                for path in gpth:
                    pth_id = path.getAttribute('id')
                    group_path_strings[pth_id] = path.getAttribute('d')
                    group_path_ids.append(pth_id)
            else:
                raise RuntimeError("Only one group with paths is allowed")

    doc.unlink() # only unlink after parsed all paths.

    for k in all_path_ids:
        if k in group_path_ids:
            del(all_path_strings[k]) # all_path_strings becomes outer_paths.

    return [all_path_strings, group_path_strings, group_path_ids]


def parse_path_line(d_string):
    path = svg_parse_path(d_string)
    x0,y0,x1,y1 = 0.0, 0.0, 0.0, 0.0
    for e in path:
        if isinstance(e, Line):
            x0,y0, x1,y1 = e.start.real, e.start.imag, e.end.real, e.end.imag
            print("  Line: (%.2f, %.2f) - (%.2f, %.2f)" % (x0, y0, x1, y1))
        elif isinstance(e, Move):
            x0,y0, x1,y1 = e.start.real, e.start.imag, e.end.real, e.end.imag
            #print("  Move: (%.2f, %.2f) - (%.2f, %.2f)" % (x0, y0, x1, y1))
        else:
            print("  Unknown path element: ", e)
    return x0, y0, x1, y1


def parse_path_cut(d_string, id_str):
    path = svg_parse_path(d_string)
    segs = []
    segs.append([";", "id = " + id_str])
    for e in path:
        if isinstance(e, Line):
            x0,y0, x1,y1 = e.start.real, e.start.imag, e.end.real, e.end.imag
            #seg = "  Line: (%.2f, %.2f) - (%.2f, %.2f)" % (x0, y0, x1, y1)
            #print(seg)
            seg = ["Line", [x0, y0], [x1, y1]]
            segs.append(seg)
        elif isinstance(e, Move):
            x0,y0, x1,y1 = e.start.real, e.start.imag, e.end.real, e.end.imag
            #seg = "  Move: (%.2f, %.2f)" % (x0, y0)
            #print(seg)
            seg = ["Move", [x0, y0]]
            segs.append(seg)
        else:
            print("  Unknown path element: ", e)
            seg = ["Unknown: ", "id = " + id_str]
            segs.append(seg)
    return segs


def parse_origin(paths, origin_id1, origin_id2):
    x0, y0 = None, None
    for p in paths.keys():
        if p == origin_id1 or p == origin_id2:
            print("id parse for origin: ", p)
            x1, y1, x2, y2 = parse_path_line( paths[p] )
            if x1 == x2 and x1 != 0:
                x0 = x1
            elif y1 == y2 and y1 != 0:
                y0 = y1
        else:
            print("id skipt for origin: ", p)
    if x0 != None and y0 != None:
        return x0, y0
    raise RuntimeError("Error in parse_origin(): no origin found")


def parse_cut_paths(paths, x0, y0):
    cuts = []
    for p in paths.keys():
        print("id parse for cut: ", p)
        segs = parse_path_cut( paths[p], p )
        cuts.append(segs)
    return cuts


def generate_gcode(cuts, x0, y0, z_depth, in_file_name, in_origin_id1, in_origin_id2):
    out_f_name = "gcode_out.gcode"
    last_line_x, last_line_y = None,None
    last_rapid_x, last_rapid_y = None,None
    with open(out_f_name, "w") as out_f:
        def output_footer():
            out_f.write("\n")
            out_f.write("; Footer\n")
            out_f.write("M5              ; Spindle stop\n")
            out_f.write("M2              ; Program stop\n")
            out_f.write("\n")

        def output_header():
            out_f.write("; Header\n")
            out_f.write("G21             ; Set units to mm\n")
            out_f.write("G90             ; Absolute positioning\n")
            out_f.write("G1 Z10 F1227      ; Move to clearance level\n")
            out_f.write("\n")
            out_f.write("; file name: %s\n" % in_file_name)
            out_f.write("; origin ids: %s %s\n" % (in_origin_id1, in_origin_id2))
            out_f.write("; origin x : %.2f\n" % x0)
            out_f.write("; origin y : %.2f\n" % y0)
            out_f.write("; cut depth: %.2f\n" % z_depth)
            out_f.write("\n")
        output_header()

        def output_retract():
            cmd = "G1 Z10 F1227"
            out_f.write("%-30s ; Move to clearance level\n" % cmd)

        def output_rapid(x,y):
            cmd = "G1 X%.2f Y%.2f F1227"  % (x,y)
            out_f.write("%-30s ; Rapid to \n" % cmd)
            out_f.write("G1 Z0\n")

        def output_plunge(z):
            cmd = "G1 Z%.2f F127" % z
            out_f.write("%-30s ; Plunge\n" % cmd)

        def output_cut(x, y):
            cmd = "G1 X%.2f Y%.2f F127" % (x, y)
            out_f.write("%-30s ; Cut\n" % cmd)

        z_step = 0.3
        z_run_depth = 0
        if z_depth < 0: z_depth = - z_depth # positive value only
        z_run_max = int(z_depth/z_step)
        z_depth_max = z_run_max * z_step
        if abs(z_depth_max - z_depth) > 0.001: z_run_max += 1
        error_count = 0
        for z_run in range(z_run_max):
            z_run_depth -= z_step
            if z_run_depth < -z_depth: z_run_depth = -z_depth
            for cut in cuts:
                for act in cut:
                    if act[0] == ";":
                        out_f.write("\n; " + str(act[1]) + "\n")
                    elif act[0] == "Move":
                        if last_line_x != None:
                            output_retract()
                            last_line_x, last_line_y = None,None
                        x,y = act[1][0]-x0, y0-act[1][1]
                        output_rapid(x,y)
                        last_rapid_x,last_rapid_y = x,y
                    elif act[0] == "Line":
                        x1,y1 = act[1][0]-x0, y0-act[1][1]
                        x2,y2 = act[2][0]-x0, y0-act[2][1]
                        if last_line_x == None:
                            if last_rapid_x != x1 or last_rapid_y != y1:
                                output_rapid(x1,y1)
                                last_rapid_x, last_rapid_y = x1,y1
                            output_plunge(z_run_depth)
                            last_line_x, last_line_y = x1,y1
                        if last_line_x != x1 or last_line_y != y1:
                            out_f.write("%s%s\n" % (
                                        "M2 ; Error ",
                                        "last_line_x=%.2f last_line_y=%.2f x1=%.2f y1=%.2f\n" % (
                                            last_line_x, last_line_y, x1, y1) ))
                            error_count += 1
                        output_cut(x2,y2)
                        last_line_x, last_line_y = x2, y2
                        last_rapid_x, last_rapid_y = None, None

            if last_line_x != None:
                out_f.write("\n; End current depth\n")
                output_retract()
                out_f.write("\n")
                last_line_x, last_line_y = None, None
                last_rapid_x, last_rapid_y = None, None

        output_footer()
        out_f.close()

        if error_count != 0:
            print("\nError occured in generating g-code. error_count %d\n" % error_count)


def optimize_distances(cuts_raw):
    cuts_out = []

    # mark cuts_used all false
    cuts_used = [False for x in cuts_raw]

    # pick next 10 closest elements
    def pick_next_chain(cuts_raw, cuts_out, cuts_used, current_index):
        # current_index already consumed

        found_last_index = None # will assign to the last element index

        #form a distance array:
        avail = [ [i, x] for i,x in enumerate(cuts_raw) if cuts_used[i] == False ]
        current = cuts_raw[current_index]
        def calc_distance(x, b):
            if b[1][0] == "Move" or b[1][0] == "Line": # base
                b_x = b[1][1][0]
                b_y = b[1][1][1]
            else:
                raise RuntimeError("Error calc_distance for b")
            if x[1][1][0] == "Move" or x[1][1][0] == "Line": # test
                t_x = x[1][1][1][0]
                t_y = x[1][1][1][1]

            else:
                raise RuntimeError("Error calc_distance for b")
            dist = abs(b_x - t_x) + abs(b_y - t_y)
            return dist
        avail_sorted = sorted(avail, key=lambda x:calc_distance(x, current) )
        if len(avail_sorted) > 0:
            # pick 100 elements:
            for i,x in enumerate(avail_sorted):
                idx = x[0]
                data = x[1]
                cuts_out.append(data)
                cuts_used[idx] = True
                found_last_index = idx
                if i >= 9:
                    break

        return found_last_index

    current_index = None
    for i,x in enumerate(cuts_raw):
        if current_index == None and cuts_used[i] == False:
            current_index = i
            cuts_used[i] = True
            cuts_out.append(x)
            while current_index is not None:
                found_last_index = pick_next_chain(cuts_raw, cuts_out, cuts_used, current_index)
                current_index = None
                if found_last_index is not None:
                    current_index = found_last_index

    return cuts_out


cfg_file = "drawing-eco2-char3mm.svg" # kicad pdf plot, grouped by inkscape.
cfg_origin_id1 = "path1204" # origin assistant line id
cfg_origin_id2 = "path1202" # origin assistant line id
        # note that: all the cut traces imported from pdf are grouped 
        #            into one group in inkscape. no other groups.
        #            work-zero origin is drawn in inkscape and the two 
        #            lines are identified by _id1 and _id2 here.

print("\nAction 1: ", "parse_svg_file ")
outer_paths, cut_paths, cut_ids = parse_svg_file(cfg_file)
        # outer_paths holds paths not belonging to the cut group.
        # cut_paths are all the paths to be cut in the group.

print("\nAction 2: ", "parse_origin ")
x0,y0 = parse_origin(outer_paths, cfg_origin_id1, cfg_origin_id2)
print("Origin at: (%.2f, %.2f)" % (x0, y0))
        # the origin is recognized by the _id1 and _id2.

print("\nAction 3: ", "parse_cut_paths ")
cuts_raw = parse_cut_paths(cut_paths, x0, y0)
        # svg paths are converted into "Move" and "Line" in array.

print("\nAction 4: ", "optimize distances ")
cuts = optimize_distances(cuts_raw)
        # re-order paths so the next is not far from the current.
        # not really optimized well. 

print("\nAction 5: ", "generate_gcode ")
generate_gcode(cuts, x0, y0, -0.8, cfg_file, cfg_origin_id1, cfg_origin_id2)

print(" all done. ")


