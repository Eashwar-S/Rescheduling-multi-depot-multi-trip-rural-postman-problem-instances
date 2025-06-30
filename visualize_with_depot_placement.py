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
    if 'edge weight' in text:
        weight_str = text.split('edge weight')[1].strip()
    elif 'cost' in text:
        weight_str = text.split('cost')[1].strip()
    else:
        weight_str = '1.0'
    try:
        return float(weight_str)
    except:
        return 1.0


def compute_coverage(G, radius):
    coverage = {}
    for node in G.nodes():
        lengths = nx.single_source_dijkstra_path_length(G, node, cutoff=radius, weight='travel_time')
        coverage[node] = set(lengths.keys())
    return coverage


def select_depots(G, battery_capacity):
    # treat 'weight' as travel_time
    for u, v, data in G.edges(data=True):
        data['travel_time'] = data.get('weight', 1.0)
    radius = battery_capacity / 2.0
    coverage = compute_coverage(G, radius)
    all_nodes = set(G.nodes())
    selected = set()
    covered = set()
    while covered != all_nodes:
        best_node = None
        best_gain = -1
        for node in G.nodes():
            if node in selected:
                continue
            gain = len(coverage[node] - covered)
            if gain > best_gain:
                best_gain = gain
                best_node = node
        if best_node is None:
            break
        selected.add(best_node)
        covered |= coverage[best_node]
    return selected


def visualize_graph(G, depots, title):
    pos = nx.spring_layout(G, seed=42)
    node_colors = ['darkgreen' if node in depots else 'lightgreen' for node in G.nodes()]
    required_edges = [(u, v) for u, v in G.edges() if G[u][v].get('required', False)]
    non_required_edges = [(u, v) for u, v in G.edges() if not G[u][v].get('required', False)]
    edge_labels = {(u, v): f"{G[u][v]['weight']:.1f}" for u, v in G.edges()}

    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=500)
    nx.draw_networkx_edges(G, pos, edgelist=required_edges, edge_color='red', width=2)
    nx.draw_networkx_edges(G, pos, edgelist=non_required_edges, edge_color='black')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='blue')
    nx.draw_networkx_labels(G, pos, font_size=10, font_color='black')

    depot_patch = mpatches.Patch(color='darkgreen', label='Depot Nodes')
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
        print('Invalid instance name.')

    max_scenario = {'gdb':37, 'bccm':108, 'eglese':112}[instance_name]
    while True:
        try:
            scenario_number = int(input(f"Enter failure scenario number [1-{max_scenario}]: ").strip())
            if 1 <= scenario_number <= max_scenario:
                break
        except:
            pass
        print('Invalid scenario number.')

    folder_name = f"Failure_Scenarios/{instance_name}_failure_scenarios"
    file_path = os.path.join(folder_name, f"{instance_name}.{scenario_number}.txt")
    if not os.path.exists(file_path):
        print(f"File {file_path} not found.")
        return

    # parse scenario file (extract graph, original depots, and battery capacity)
    G, original_depots, battery_capacity = parse_text_file(file_path)
    visualize_graph(G, original_depots, f"Scenario {instance_name}.{scenario_number} - Before Depot Placement")

    # compute new depots and visualize
    new_depots = select_depots(G, battery_capacity)
    visualize_graph(G, new_depots, f"Scenario {instance_name}.{scenario_number} - After Depot Placement")

if __name__ == "__main__":
    main()
