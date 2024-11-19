#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

mac_table = {}
config = {}
port_states = {}
designated_ports = []

root_port = None
switch_id = None
root_bridge_id = None
root_path_cost = None
own_bridge_id = None

interfaces2 = None

def add_mac_to_table(mac, interface):
    if mac not in mac_table:
        mac_table[mac] = interface
        print(f'Added {mac} to the MAC table with interface {interface}')

def get_interface_from_mac(mac):
    return mac_table.get(mac, None)

def parse_switch_config(file_name):
    global config, switch_id
    firstLine = True
    with open(file_name, 'r') as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if firstLine:
                switch_id = int(line)
                firstLine = False
                continue

            parts = line.split()
            if len(parts) == 2:
                interface, iface_type = parts[0], parts[1]
                config[interface] = iface_type

def broadcast(interface, length, data, interfaces):
    if config[get_interface_name(interface)] == "T":
        for i in interfaces:
            if i != interface:
                if config[get_interface_name(i)] == "T":
                    if port_states[get_interface_name(i)] == "LISTENING" and get_interface_name(i) in designated_ports:
                        send_to_link(i, length, data)
                elif config[get_interface_name(i)] == str(parse_ethernet_header(data)[3]):
                    new_frame = data[0:12] + data[16:]
                    send_to_link(i, length - 4, new_frame)
    else:
        for i in interfaces:
            if i != interface:
                if config[get_interface_name(i)] == "T":
                    if port_states[get_interface_name(i)] == "LISTENING" and get_interface_name(i) in designated_ports:
                        tagged_frame = data[0:12] + create_vlan_tag(int(config[get_interface_name(interface)])) + data[12:]
                        send_to_link(i, length + 4, tagged_frame)
                elif config[get_interface_name(i)] == config[get_interface_name(interface)]:
                    send_to_link(i, length, data)

def create_ethernet_frame(root_bridge_id, sender_bridge_id, path_cost):
    dest_mac = bytes([0x01, 0x80, 0xc2, 0, 0, 0])
    switch_mac = get_switch_mac()
    packet = (dest_mac + switch_mac +
              struct.pack("!H", 0x4242) + 
              struct.pack("!H", root_bridge_id) + 
              struct.pack("!H", path_cost) + 
              struct.pack("!H", sender_bridge_id))
    return packet

def parse_ethernet_frame(data):
    root_bridge_id, root_path_cost, bridge_id = struct.unpack("!3H", data[14:20])
    return root_bridge_id, root_path_cost, bridge_id

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    #dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def send_bdpu_every_sec():
    global root_bridge_id, root_path_cost, own_bridge_id, interfaces2
    while True:
        if own_bridge_id == root_bridge_id:
            for i in interfaces2:
                if config[get_interface_name(i)] == "T":
                    pack = create_ethernet_frame(root_bridge_id, root_path_cost, own_bridge_id)
                    send_to_link(i, len(pack), pack)
        time.sleep(1)

def main():
    global root_bridge_id, root_path_cost, own_bridge_id, root_port, switch_id, interfaces2
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_idd = sys.argv[1]

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)

    print("# Starting switch with id {}".format(switch_idd), flush=True)
    print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))

    parse_switch_config("configs/switch" + switch_idd + ".cfg")

    for i in interfaces:
        if config[get_interface_name(i)] == "T":
            port_states[get_interface_name(i)] = "BLOCKING"
    
    own_bridge_id = switch_id
    interfaces2 = interfaces

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec)
    t.start()

    # Printing interface names
    for i in interfaces:
        print(get_interface_name(i))

    own_bridge_id = switch_id
    root_bridge_id = own_bridge_id
    root_path_cost = 0

    if own_bridge_id == root_bridge_id:
        for i in interfaces:
            if config[get_interface_name(i)] == "T":
                port_states[get_interface_name(i)] = "LISTENING"
                designated_ports.append(get_interface_name(i))

    while True:
        # Note that data is of type bytes([...]).
        # b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
        # b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
        # b3 = b1[0:2] + b[3:4].
        interface, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        # Print the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        # Note. Adding a VLAN tag can be as easy as
        # tagged_frame = data[0:12] + create_vlan_tag(10) + data[12:]
        # new_frame = data[0:12] + data[16:]

        print(f'Destination MAC: {dest_mac}')
        print(f'Source MAC: {src_mac}')
        print(f'EtherType: {ethertype}')

        print("Received frame of size {} on interface {}".format(length, interface), flush=True)

        if ethertype == 0x4242:
            local_root_bridge_id, local_root_path_cost, local_bridge_id = parse_ethernet_frame(data)
            if local_root_bridge_id < root_bridge_id:
                old_root_bridge_id = root_bridge_id
                root_bridge_id = local_root_bridge_id
                root_path_cost = local_root_path_cost + 10
                root_port = get_interface_name(interface)
            
                if own_bridge_id == old_root_bridge_id:
                    for i in interfaces:
                        if config[get_interface_name(i)] == "T":
                            if i != interface:
                                port_states[get_interface_name(i)] = "BLOCKING"
                                designated_ports.remove(get_interface_name(i))

                if port_states[get_interface_name(interface)] == "BLOCKING":
                    port_states[get_interface_name(interface)] = "LISTENING"
                
                for i in interfaces:
                    if config[get_interface_name(i)] == "T":
                        if i != interface:
                            pack = create_ethernet_frame(root_bridge_id, root_path_cost, own_bridge_id)
                            send_to_link(i, len(pack), pack)
            elif local_root_bridge_id == root_bridge_id:
                if get_interface_name(interface) == root_port and local_root_path_cost + 10 < root_path_cost:
                    root_path_cost = local_root_path_cost + 10
                elif get_interface_name(interface) != root_port:
                    if local_root_path_cost > root_path_cost:
                        if get_interface_name(interface) not in designated_ports:
                            designated_ports.append(get_interface_name(interface))
                            port_states[get_interface_name(interface)] = "LISTENING"

            elif local_root_bridge_id == own_bridge_id:
                port_states[get_interface_name(interface)] = "BLOCKING"
                designated_ports.remove(get_interface_name(interface))
            else:
                continue

            if own_bridge_id == root_bridge_id:
                for i in interfaces:
                    if get_interface_name(i) != root_port and config[get_interface_name(i)] == "T":
                        port_states[get_interface_name(i)] = "LISTENING"
                        designated_ports.append(get_interface_name(i))
            continue

        add_mac_to_table(src_mac, interface)

        if dest_mac == "FF:FF:FF:FF:FF:FF":
            broadcast(interface, length, data, interfaces)

        else:
            if dest_mac in mac_table:
                dest_interface = get_interface_from_mac(dest_mac)
                if  config[get_interface_name(interface)] == "T":
                    if config[get_interface_name(dest_interface)] == "T":
                        if port_states[get_interface_name(dest_interface)] == "LISTENING" and get_interface_name(dest_interface) in designated_ports:
                            send_to_link(dest_interface, length, data)
                    elif config[get_interface_name(dest_interface)] == str(parse_ethernet_header(data)[3]):
                        new_frame = data[0:12] + data[16:]
                        send_to_link(dest_interface, length - 4, new_frame)
                else:
                    if config[get_interface_name(dest_interface)] == "T":
                        if port_states[get_interface_name(dest_interface)] == "LISTENING" and get_interface_name(dest_interface) in designated_ports:
                            tagged_frame = data[0:12] + create_vlan_tag(int(config[get_interface_name(interface)])) + data[12:]
                            send_to_link(dest_interface, length + 4, tagged_frame)
                    elif config[get_interface_name(dest_interface)] == config[get_interface_name(interface)]:
                        send_to_link(dest_interface, length, data)
            else:
                broadcast(interface, length, data, interfaces)

        # data is of type bytes.
        # send_to_link(i, length, data)

if __name__ == "__main__":
    main()
