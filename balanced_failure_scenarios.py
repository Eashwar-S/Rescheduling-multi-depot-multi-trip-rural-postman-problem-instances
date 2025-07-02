#!/usr/bin/env python3

import os
import shutil
import math
import re
import networkx as nx

def parse_text_file(file_path):
    G = nx.Graph()
    depots = []
    battery_capacity = None
    with open(file_path, 'r') as f:
        lines = f.readlines()
    current_section = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('NAME'):
            continue
        elif line.startswith('NUMBER OF VERTICES'):
            num_vertices = int(line.split(':')[1].strip())
            G.add_nodes_from(range(1, num_vertices + 1))
        elif line.startswith('VEHICLE CAPACITY'):
            # battery capacity is given in time units
            battery_capacity = float(line.split(':')[1].strip())
        elif line.startswith('LIST_REQUIRED_EDGES:'):
            current_section = 'required_edges'
        elif line.startswith('LIST_NON_REQUIRED_EDGES:'):
            current_section = 'non_required_edges'
        elif line.startswith('FAILURE_SCENARIO:'):
            current_section = 'failure_scenario'
        elif line.startswith('DEPOT:'):
            depots_line = line.split(':', 1)[1].strip()
            depots = [int(x.strip()) for x in depots_line.split(',')]
        else:
            if current_section in ('required_edges', 'non_required_edges'):
                u_v, rest = line.split(') ', 1)
                u_v = u_v.strip('(')
                u, v = map(int, u_v.split(','))
                weight = extract_weight(rest)
                required = (current_section == 'required_edges')
                G.add_edge(u, v, weight=weight, required=required)
    if battery_capacity is None:
        raise ValueError('VEHICLE CAPACITY not found in file')
    return G, depots, battery_capacity

def extract_weight(text):
    if 'edge weight' in text:
        weight_str = text.split('edge weight')[1].strip()
    elif 'cost' in text:
        weight_str = text.split('cost')[1].strip()
    else:
        print("[!] Warning: No edge weight found, using default 1.0")
        weight_str = '1.0'
    try:
        return float(weight_str)
    except:
        return 1.0

def rebalance_required_edges(text_lines):
    """
    Given the lines of a scenario file,
    split into header, required, non-required, footer;
    rebalance so that required edges = half of total edges;
    if there is exactly one depot, force NUMBER OF VEHICLES to 2.
    Return the new list of lines, depot_count, and vehicle_count.
    """
    header = []
    req_lines = []
    nonreq_lines = []
    footer = []
    section = None

    # 1) parse into sections
    for line in text_lines:
        stripped = line.strip()
        if stripped.startswith("LIST_REQUIRED_EDGES:"):
            section = "required"
            header.append(line)
            continue
        elif stripped.startswith("LIST_NON_REQUIRED_EDGES:"):
            section = "nonrequired"
            continue
        # when we hit the next section (e.g. FAILURE_SCENARIO:)
        elif stripped.endswith(":") and section in ("required", "nonrequired"):
            section = "footer"
            footer.append(line)
            continue

        if section is None:
            header.append(line)
        elif section == "required":
            if stripped.startswith("("):
                req_lines.append(line)
            else:
                header.append(line)
        elif section == "nonrequired":
            if stripped.startswith("("):
                nonreq_lines.append(line)
        else:  # footer
            footer.append(line)

    # 2) compute how many to move
    total_edges = len(req_lines) + len(nonreq_lines)
    target_req = math.ceil(total_edges / 2)

    if len(req_lines) > target_req:
        # move extras back to non-required at front
        for _ in range(len(req_lines) - target_req):
            nonreq_lines.insert(0, req_lines.pop())
    else:
        # move from non-required into required
        for _ in range(target_req - len(req_lines)):
            if not nonreq_lines:
                break
            req_lines.append(nonreq_lines.pop(0))

    # 3) rebuild file in order
    out = []
    # header up to LIST_REQUIRED_EDGES:
    for line in header:
        out.append(line)
        if line.strip().startswith("LIST_REQUIRED_EDGES:"):
            break

    # write the rebalanced required edges
    for l in req_lines:
        out.append(l)
    # out.append("\n")

    # write non-required
    out.append("LIST_NON_REQUIRED_EDGES:\n")
    for l in nonreq_lines:
        out.append(l)
    # out.append("\n")

    # append footer (FAILURE_SCENARIO, NUMBER OF VEHICLES, DEPOT, etc)
    out.extend(footer)

    # 4) detect depot count so we can override vehicles if needed
    depot_count = 0
    for l in out:
        if l.strip().startswith("DEPOT:"):
            parts = l.split(":", 1)[1].strip()
            tokens = [t for t in re.split(r'[, \t]+', parts) if t]
            depot_count = len(tokens)
            break

    # decide vehicle count: if only one depot, force 2
    vehicle_count = 2 if depot_count == 1 else depot_count

    # 5) fix the counts lines
    fixed = []
    for line in out:
        if line.strip().startswith("NUMBER OF REQUIRED_EDGES:"):
            fixed.append(f"NUMBER OF REQUIRED_EDGES: {len(req_lines)}\n")
        elif line.strip().startswith("NUMBER OF NON_REQUIRED_EDGES:"):
            fixed.append(f"NUMBER OF NON_REQUIRED_EDGES: {len(nonreq_lines)}\n")
        elif line.strip().startswith("NUMBER OF VEHICLES:"):
            fixed.append(f"NUMBER OF VEHICLES: {vehicle_count}\n")
        else:
            fixed.append(line)

    return fixed, depot_count, vehicle_count

def process_all(instances, input_base, output_base):
    """
    For each instance type and scenario, rebalance required edges and write to new folder.
    """
    if os.path.exists(output_base):
        shutil.rmtree(output_base)
    os.makedirs(output_base, exist_ok=True)

    for inst, max_n in instances.items():
        in_dir  = os.path.join(input_base,  f"{inst}_failure_scenarios")
        out_dir = os.path.join(output_base, f"{inst}_failure_scenarios")
        os.makedirs(out_dir, exist_ok=True)

        for i in range(1, max_n + 1):
            infile  = os.path.join(in_dir,  f"{inst}.{i}.txt")
            outfile = os.path.join(out_dir, f"{inst}.{i}.txt")
            if not os.path.exists(infile):
                print(f"[!] Missing {infile}, skipping.")
                continue

            with open(infile, 'r') as f:
                lines = f.readlines()

            new_lines, depot_count, vehicle_count = rebalance_required_edges(lines)

            with open(outfile, 'w') as f:
                f.writelines(new_lines)

            # report new required-edge count
            req_idx    = next(idx for idx, l in enumerate(new_lines) if l.strip() == "LIST_REQUIRED_EDGES:")
            nonreq_idx = next(idx for idx, l in enumerate(new_lines) if l.strip() == "LIST_NON_REQUIRED_EDGES:")
            req_count  = sum(1 for l in new_lines[req_idx+1:nonreq_idx] if l.strip().startswith("("))
            print(f"Rebalanced {inst}.{i}: now {req_count} required edges; vehicles set to {vehicle_count if depot_count==1 else depot_count}")

def select_depots_with_factor(G, battery_capacity, factor):
    """
    Greedy cover: pick depots so every node is within battery_capacity/factor.
    """
    # annotate travel_time
    for u, v, data in G.edges(data=True):
        data['travel_time'] = data.get('weight', 1.0)

    radius = battery_capacity / factor
    # precompute coverage balls
    coverage = {}
    for node in G.nodes():
        lengths = nx.single_source_dijkstra_path_length(
            G, node, cutoff=radius, weight='travel_time'
        )
        coverage[node] = set(lengths.keys())

    all_nodes = set(G.nodes())
    selected, covered = set(), set()

    while covered != all_nodes:
        best_node, best_gain = None, -1
        for node in G.nodes():
            if node in selected:
                continue
            gain = len(coverage[node] - covered)
            if gain > best_gain:
                best_gain, best_node = gain, node
        if best_node is None:
            break
        selected.add(best_node)
        covered |= coverage[best_node]

    return selected

def update_gdb_with_third_radius():
    """
    For each GDB scenario, place depots so all nodes lie within battery_capacity/3,
    set #vehicles = #depots, and write into a new folder.
    """
    in_dir  = "Balanced_Failure_Scenarios/gdb_failure_scenarios"
    out_dir = "Balanced_Failure_Scenarios/gdb_failure_scenarios_third"
    os.makedirs(out_dir, exist_ok=True)

    for fname in os.listdir(in_dir):
        if not fname.endswith(".txt"):
            continue
        src = os.path.join(in_dir,  fname)
        dst = os.path.join(out_dir, fname)

        # parse graph & capacity
        G, _, battery_capacity = parse_text_file(src)

        # pick depots with 1/3 radius
        new_depots = select_depots_with_factor(G, battery_capacity, factor=2)
        n_veh = len(new_depots)

        # rewrite exactly as before, stripping old DEPOT/VEHICLE lines
        lines = open(src).read().splitlines(True)
        filtered = [l for l in lines
                    if not l.startswith("DEPOT:")
                    and not l.startswith("NUMBER OF VEHICLES:")]

        # insert new vehicle count
        for i, l in enumerate(filtered):
            if l.startswith("VEHICLE CAPACITY"):
                filtered.insert(i+1, f"NUMBER OF VEHICLES: {n_veh}\n")
                break

        # insert new DEPOT list
        for i, l in enumerate(filtered):
            if l.strip().startswith("("):
                filtered.insert(i, "DEPOT: " + ",".join(map(str, sorted(new_depots))) + "\n")
                break

        with open(dst, "w") as f:
            f.writelines(filtered)

        print(f"  GDB {fname}: placed {n_veh} depots with radius=C/3")




if __name__ == "__main__":
    # instances   = {'gdb': 37, 'bccm': 108, 'eglese': 112}
    # input_base  = "Updated_Failure_Scenarios"
    # output_base = "Balanced_Failure_Scenarios"
    # process_all(instances, input_base, output_base)

    update_gdb_with_third_radius()
