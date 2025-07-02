#!/usr/bin/env python3

import os
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines

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
    """
    Extract numeric weight from a string containing 'edge weight' or 'cost'.
    """
    text = text.strip()
    if 'edge weight' in text:
        value = text.split('edge weight', 1)[1].strip()
    elif 'cost' in text:
        value = text.split('cost', 1)[1].strip()
    else:
        return 1.0
    try:
        return float(value)
    except ValueError:
        return 1.0

def compute_coverage(G, radius):
    """
    For each node, compute the set of nodes reachable within 'radius' using Dijkstra.
    """
    coverage = {}
    for node in G.nodes():
        lengths = nx.single_source_dijkstra_path_length(G, node, cutoff=radius, weight='travel_time')
        coverage[node] = set(lengths.keys())
    return coverage

def select_depots(G, battery_capacity):
    """
    Greedily select depot locations so that every node is within radius = battery_capacity/2.
    """
    # annotate edges with travel_time = weight
    for u, v, data in G.edges(data=True):
        data['travel_time'] = data.get('weight', 1.0)

    radius = battery_capacity / 2.0
    coverage = compute_coverage(G, radius)
    all_nodes = set(G.nodes())
    selected = set()
    covered = set()

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

def update_all_instances():
    """
    Iterate over all failure scenarios, compute new depot placements,
    set number of vehicles = number of depots, and write updated .txt files.
    """
    instances = {
        'gdb': 37,
        'bccm': 108,
        'eglese': 112
    }
    input_base = "Failure_Scenarios"
    output_base = "Updated_Failure_Scenarios"

    os.makedirs(output_base, exist_ok=True)

    for inst, max_num in instances.items():
        in_folder = os.path.join(input_base, f"{inst}_failure_scenarios")
        out_folder = os.path.join(output_base, f"{inst}_failure_scenarios")
        os.makedirs(out_folder, exist_ok=True)

        for scenario in range(1, max_num + 1):
            infile = os.path.join(in_folder, f"{inst}.{scenario}.txt")
            if not os.path.exists(infile):
                print(f"[!] Missing file: {infile}, skipping.")
                continue

            # parse and compute new depots
            G, _ , battery_capacity = parse_text_file(infile)
            new_depots = select_depots(G, battery_capacity)
            num_vehicles = len(new_depots)

            # read original lines and strip old DEPOT and VEHICLE COUNT lines
            with open(infile, 'r') as f:
                lines = f.readlines()
            filtered = [
                l for l in lines
                if not l.strip().startswith('DEPOT:')
                and not l.strip().startswith('NUMBER OF VEHICLES')
            ]

            # prepare new header lines
            vehicle_line = f"NUMBER OF VEHICLES: {num_vehicles}\n"
            depot_line   = f"DEPOT: {','.join(str(d) for d in sorted(new_depots))}\n"

            # find where to insert vehicle count (after VEHICLE CAPACITY)
            vc_idx = next(
                (i for i, l in enumerate(filtered) if l.strip().startswith('VEHICLE CAPACITY')),
                None
            )
            # if vc_idx is not None:
            #     filtered.insert(vc_idx + 1, vehicle_line)
            # else:
            #     # fallback to top
            #     filtered.insert(0, vehicle_line)

            # find where to insert DEPOT line (before first edge line)
            edge_idx = next(
                (i for i, l in enumerate(filtered) if l.strip().startswith('(')),
                len(filtered)
            )
            # filtered.insert(edge_idx, depot_line)
            filtered.append(vehicle_line)
            filtered.append(depot_line)
            # write out updated file
            outfile = os.path.join(out_folder, f"{inst}.{scenario}.txt")
            with open(outfile, 'w') as f:
                f.writelines(filtered)

            print(f"Updated {inst}.{scenario} → {outfile}")


def visualize_graph(G, depots, title):
    pos = nx.spring_layout(G, seed=42)
    node_colors = ['orange' if node in depots else 'lightgreen' for node in G.nodes()]
    required_edges = [(u, v) for u, v in G.edges() if G[u][v].get('required', False)]
    non_required_edges = [(u, v) for u, v in G.edges() if not G[u][v].get('required', False)]
    edge_labels = {(u, v): f"{G[u][v]['weight']:.1f}" for u, v in G.edges()}

    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=75)
    nx.draw_networkx_edges(G, pos, edgelist=required_edges, edge_color='red', width=2)
    nx.draw_networkx_edges(G, pos, edgelist=non_required_edges, edge_color='black')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='blue')
    nx.draw_networkx_labels(G, pos, font_size=7, font_color='black')

    depot_patch = mpatches.Patch(color='orange', label='Depot Nodes')
    node_patch = mpatches.Patch(color='lightgreen', label='Other Nodes')
    required_edge_line = mlines.Line2D([], [], color='red', label='Required Edges', linewidth=2)
    non_required_edge_line = mlines.Line2D([], [], color='black', label='Non-required Edges')
    plt.legend(handles=[depot_patch, node_patch, required_edge_line, non_required_edge_line], loc='best')

    plt.title(title)
    plt.axis('off')
    plt.show()

def main():
    # choose instance
    while True:
        instance_name = input("Enter instance name (gdb, bccm, eglese): ").strip().lower()
        if instance_name in ['gdb', 'bccm', 'eglese']:
            break
        print("Invalid instance name.")

    max_scenario = {'gdb': 37, 'bccm': 108, 'eglese': 112}[instance_name]
    while True:
        try:
            n = int(input(f"Enter failure scenario number [1-{max_scenario}]: ").strip())
            if 1 <= n <= max_scenario:
                scenario_number = n
                break
        except ValueError:
            pass
        print("Invalid scenario number.")


    folder = f"Balanced_Failure_Scenarios/{instance_name}_failure_scenarios_third"
    file_path = os.path.join(folder, f"{instance_name}.{scenario_number}.txt")
    if not os.path.exists(file_path):
        print(f"[!] File not found: {file_path}")
        return

    # parse original scenario (graph + original depots + capacity)
    G, original_depots, battery_capacity = parse_text_file(file_path)

    visualize_graph(
        G,
        original_depots,
        f"Scenario {instance_name}.{scenario_number} — Random Depot Placement - ({len(original_depots)} depots)"
    )

    folder = f"Balanced_Failure_Scenarios/{instance_name}_failure_scenarios_fourth"
    file_path = os.path.join(folder, f"{instance_name}.{scenario_number}.txt")
    if not os.path.exists(file_path):
        print(f"[!] File not found: {file_path}")
        return

    # parse original scenario (graph + original depots + capacity)
    G, new_depots, battery_capacity = parse_text_file(file_path)

    # visualize before placement
    visualize_graph(
        G,
        new_depots,
        f"Scenario {instance_name}.{scenario_number} — Heuristic Depot Placement - ({len(new_depots)} depots)"
    )

if __name__ == "__main__":
    # Uncomment the line below to update all instances
    # update_all_instances()
    main()
