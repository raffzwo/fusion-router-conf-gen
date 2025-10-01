#!/usr/bin/env python3
"""
Cisco Fusion Router Configuration Generator
Flask web application for generating BGP/BFD configurations for fusion routers
that peer with SDA fabric border nodes.
"""

import os
import re
import ipaddress
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import io

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max file size
app.config['UPLOAD_FOLDER'] = '/tmp'

# Allowed file extensions
ALLOWED_EXTENSIONS = {'txt', 'cfg', 'conf'}


def allowed_file(filename):
    """Check if uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_outputs_directory():
    """Create outputs directory if it doesn't exist."""
    outputs_dir = os.path.join(os.path.dirname(__file__), 'outputs')
    if not os.path.exists(outputs_dir):
        os.makedirs(outputs_dir)
    return outputs_dir


def generate_timestamp():
    """Generate timestamp for filenames."""
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def save_config_to_file(config, hostname, timestamp):
    """
    Save configuration to outputs directory.

    Args:
        config: Configuration text
        hostname: Fusion router hostname
        timestamp: Timestamp string

    Returns:
        filepath: Path to saved file
    """
    outputs_dir = ensure_outputs_directory()
    filename = f"{hostname}-config-{timestamp}.txt"
    filepath = os.path.join(outputs_dir, filename)

    with open(filepath, 'w') as f:
        f.write(config)

    return filepath


def save_generation_summary(summary_data, timestamp):
    """
    Save generation summary as JSON.

    Args:
        summary_data: Dict with generation details
        timestamp: Timestamp string

    Returns:
        filepath: Path to saved summary file
    """
    outputs_dir = ensure_outputs_directory()
    filename = f"generation-summary-{timestamp}.json"
    filepath = os.path.join(outputs_dir, filename)

    with open(filepath, 'w') as f:
        json.dump(summary_data, f, indent=2)

    return filepath


class CiscoConfigParser:
    """Parser for Cisco IOS configuration files."""

    def __init__(self, config_text):
        self.config_text = config_text
        # Clean up lines: remove line numbers if present (format: "    1 |content")
        cleaned_lines = []
        for line in config_text.split('\n'):
            # Remove line number prefix if present
            if '|' in line:
                # Format is something like "    123 |content"
                parts = line.split('|', 1)
                if len(parts) == 2:
                    line = parts[1]
            cleaned_lines.append(line)
        self.lines = cleaned_lines

    def get_hostname(self):
        """Extract hostname from configuration."""
        for line in self.lines:
            if line.startswith('hostname '):
                return line.split('hostname ')[1].strip()
        return None

    def get_loopback0_ip(self):
        """Extract Loopback0 IP address."""
        in_loopback0 = False
        for line in self.lines:
            if line.startswith('interface Loopback0'):
                in_loopback0 = True
            elif in_loopback0:
                if line.startswith(' ip address '):
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        return parts[2]  # IP address
                elif line.startswith('interface '):
                    break
        return None

    def get_bgp_config(self):
        """Extract BGP configuration details."""
        bgp_config = {
            'as_number': None,
            'default_vrf_neighbors': [],
            'vrf_neighbors': {}
        }

        current_vrf = None
        in_bgp = False

        for line in self.lines:
            if line.startswith('router bgp '):
                bgp_config['as_number'] = line.split('router bgp ')[1].strip()
                in_bgp = True
            elif in_bgp:
                if line.startswith('!'):
                    in_bgp = False
                    current_vrf = None
                elif line.strip().startswith('address-family ipv4 vrf '):
                    vrf_name = line.strip().split('vrf ')[1].strip()
                    current_vrf = vrf_name
                    if vrf_name not in bgp_config['vrf_neighbors']:
                        bgp_config['vrf_neighbors'][vrf_name] = []
                elif line.strip().startswith('exit-address-family'):
                    current_vrf = None
                elif line.strip().startswith('neighbor '):
                    neighbor_match = re.match(r'\s*neighbor\s+([\d\.]+)\s+remote-as\s+(\d+)', line)
                    if neighbor_match:
                        neighbor_ip = neighbor_match.group(1)
                        remote_as = neighbor_match.group(2)

                        neighbor_info = {
                            'ip': neighbor_ip,
                            'remote_as': remote_as
                        }

                        if current_vrf:
                            bgp_config['vrf_neighbors'][current_vrf].append(neighbor_info)
                        else:
                            # Check if we're in default VRF address-family
                            if any('address-family ipv4' in l and 'vrf' not in l for l in self.lines[:self.lines.index(line)]):
                                bgp_config['default_vrf_neighbors'].append(neighbor_info)

        return bgp_config

    def get_vlan_interfaces(self):
        """Extract VLAN interface configurations with BFD."""
        vlan_interfaces = []
        current_vlan = None
        current_config = {}

        for line in self.lines:
            if line.startswith('interface Vlan'):
                if current_vlan and current_config:
                    vlan_interfaces.append(current_config)

                vlan_num = line.split('Vlan')[1].strip()
                current_config = {
                    'vlan': vlan_num,
                    'ip_address': None,
                    'subnet_mask': None,
                    'vrf': None,
                    'description': None,
                    'bfd_enabled': False,
                    'bfd_interval': None,
                    'bfd_min_rx': None,
                    'bfd_multiplier': None
                }
                current_vlan = vlan_num

            elif current_vlan:
                line_stripped = line.strip()

                if line.startswith('interface '):
                    if current_config:
                        vlan_interfaces.append(current_config)
                    current_vlan = None
                    current_config = {}

                elif line_stripped.startswith('ip address '):
                    parts = line_stripped.split()
                    if len(parts) >= 4:
                        current_config['ip_address'] = parts[2]
                        current_config['subnet_mask'] = parts[3]

                elif line_stripped.startswith('vrf forwarding '):
                    current_config['vrf'] = line_stripped.split('vrf forwarding ')[1]

                elif line_stripped.startswith('description '):
                    current_config['description'] = line_stripped.split('description ', 1)[1]

                elif line_stripped.startswith('bfd interval '):
                    current_config['bfd_enabled'] = True
                    bfd_match = re.match(r'bfd interval (\d+) min_rx (\d+) multiplier (\d+)', line_stripped)
                    if bfd_match:
                        current_config['bfd_interval'] = bfd_match.group(1)
                        current_config['bfd_min_rx'] = bfd_match.group(2)
                        current_config['bfd_multiplier'] = bfd_match.group(3)

        # Add the last VLAN if exists
        if current_vlan and current_config:
            vlan_interfaces.append(current_config)

        # Filter for /30 subnets only
        filtered_vlans = []
        for vlan in vlan_interfaces:
            if vlan['ip_address'] and vlan['subnet_mask'] == '255.255.255.252':
                filtered_vlans.append(vlan)

        return filtered_vlans

    def extract_physical_interfaces(self):
        """Extract physical interface configurations from border node."""
        physical_interfaces = []
        current_interface = None
        current_config = {}

        # Pattern to match physical interfaces (not VLANs, not Loopbacks)
        physical_interface_pattern = re.compile(
            r'^interface (GigabitEthernet|TenGigabitEthernet|FortyGigE|HundredGigE|TwentyFiveGigE|Port-channel)[\d/.]+'
        )

        for line in self.lines:
            match = physical_interface_pattern.match(line)
            if match:
                # Save previous interface if exists
                if current_interface and current_config:
                    physical_interfaces.append(current_config)

                current_interface = line.split('interface ')[1].strip()
                current_config = {
                    'name': current_interface,
                    'description': None,
                    'mode': None,  # access, trunk, routed
                    'allowed_vlans': None,
                    'access_vlan': None,
                    'shutdown': False
                }
            elif current_interface:
                line_stripped = line.strip()

                # Check if we've moved to next interface or end of interface config
                if line.startswith('interface ') or line.startswith('!'):
                    if current_config:
                        physical_interfaces.append(current_config)
                    current_interface = None
                    current_config = {}
                    continue

                if line_stripped.startswith('description '):
                    current_config['description'] = line_stripped.split('description ', 1)[1]
                elif line_stripped == 'switchport mode trunk':
                    current_config['mode'] = 'trunk'
                elif line_stripped == 'switchport mode access':
                    current_config['mode'] = 'access'
                elif line_stripped.startswith('switchport trunk allowed vlan '):
                    current_config['allowed_vlans'] = line_stripped.split('switchport trunk allowed vlan ')[1]
                elif line_stripped.startswith('switchport access vlan '):
                    current_config['access_vlan'] = line_stripped.split('switchport access vlan ')[1]
                elif line_stripped == 'shutdown':
                    current_config['shutdown'] = True
                elif line_stripped.startswith('ip address '):
                    # This is a routed interface (L3)
                    current_config['mode'] = 'routed'
                    parts = line_stripped.split()
                    if len(parts) >= 4:
                        current_config['ip_address'] = parts[2]
                        current_config['subnet_mask'] = parts[3]

        # Add last interface if exists
        if current_interface and current_config:
            physical_interfaces.append(current_config)

        return physical_interfaces

    def detect_vrf_status(self, vlan_id):
        """
        Check if a VLAN interface is in a VRF or global routing table.

        Args:
            vlan_id: The VLAN ID to check

        Returns:
            None if in global table, VRF name if in a VRF
        """
        in_target_vlan = False

        for line in self.lines:
            if line.startswith(f'interface Vlan{vlan_id}'):
                in_target_vlan = True
            elif in_target_vlan:
                if line.startswith('interface '):
                    # Moved to next interface without finding VRF
                    return None
                elif line.strip().startswith('vrf forwarding '):
                    return line.strip().split('vrf forwarding ')[1]

        return None

    def parse(self):
        """Parse the configuration and return all relevant information."""
        return {
            'hostname': self.get_hostname(),
            'loopback0_ip': self.get_loopback0_ip(),
            'bgp': self.get_bgp_config(),
            'vlan_interfaces': self.get_vlan_interfaces(),
            'physical_interfaces': self.extract_physical_interfaces()
        }


def calculate_fusion_router_ip(border_node_ip):
    """
    Calculate the fusion router IP address from border node IP.
    For a /30 subnet, there are 4 addresses:
    - Network address (unusable)
    - First usable (typically border node)
    - Second usable (typically fusion router)
    - Broadcast address (unusable)
    """
    try:
        # Parse the IP and create a /30 network
        ip_obj = ipaddress.ip_address(border_node_ip)
        # Find the /30 network this IP belongs to
        network = ipaddress.ip_network(f"{border_node_ip}/30", strict=False)

        # Get all usable hosts
        hosts = list(network.hosts())

        if len(hosts) != 2:
            return None

        # If border node is first host, fusion router is second
        if str(hosts[0]) == border_node_ip:
            return str(hosts[1])
        # If border node is second host, fusion router is first
        elif str(hosts[1]) == border_node_ip:
            return str(hosts[0])
        else:
            return None

    except Exception:
        return None


def validate_vrf_name(vrf_name):
    """
    Validate VRF name format.

    Args:
        vrf_name: VRF name to validate

    Returns:
        tuple: (is_valid, error_message)
    """
    if not vrf_name:
        return False, "VRF name is required"

    if len(vrf_name) > 32:
        return False, "VRF name must be 32 characters or less"

    # VRF names should be alphanumeric with underscores and hyphens
    if not re.match(r'^[a-zA-Z0-9_-]+$', vrf_name):
        return False, "VRF name must contain only letters, numbers, underscores, and hyphens"

    return True, None


def validate_route_distinguisher(rd):
    """
    Validate Route Distinguisher format.

    Valid formats:
    - ASN:NN (e.g., 65000:100)
    - IP:NN (e.g., 10.0.0.1:100)

    Args:
        rd: Route Distinguisher string

    Returns:
        tuple: (is_valid, error_message)
    """
    if not rd:
        return False, "Route Distinguisher is required"

    # Check ASN:NN format
    asn_format = re.match(r'^(\d+):(\d+)$', rd)
    if asn_format:
        asn = int(asn_format.group(1))
        nn = int(asn_format.group(2))
        if asn <= 4294967295 and nn <= 65535:
            return True, None

    # Check IP:NN format
    ip_format = re.match(r'^([\d\.]+):(\d+)$', rd)
    if ip_format:
        try:
            ipaddress.ip_address(ip_format.group(1))
            nn = int(ip_format.group(2))
            if nn <= 65535:
                return True, None
        except ValueError:
            pass

    return False, "Route Distinguisher must be in format 'ASN:NN' (e.g., 65000:100) or 'IP:NN' (e.g., 10.0.0.1:100)"


def validate_ip_address(ip_str):
    """
    Validate IP address format.

    Args:
        ip_str: IP address string

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        ipaddress.ip_address(ip_str)
        return True, None
    except ValueError:
        return False, f"Invalid IP address: {ip_str}"


def validate_ospf_params(ospf_params):
    """
    Validate OSPF configuration parameters.

    Args:
        ospf_params: Dict with OSPF parameters
            {
                'enabled': True,
                'process_id': 1,
                'area': 0,
                'interface_mode': 'physical|svi|subinterface',
                'router1_interface': 'GigabitEthernet0/0/10',
                'router1_ip': '10.255.255.0',
                'router2_interface': 'GigabitEthernet0/0/10',
                'router2_ip': '10.255.255.1',
                'subnet_mask': '255.255.255.252',
                'vlan_id': 999,  # for SVI/subinterface modes
                'cost': 100,  # optional
                'bfd_enabled': True,
                'authentication': 'none|md5',
                'md5_key_id': 1,
                'md5_key': 'secret'
            }

    Returns:
        tuple: (is_valid, error_message)

    Raises:
        ValueError: If validation fails
    """
    if not ospf_params or not ospf_params.get('enabled'):
        return True, None

    # Validate process ID (1-65535)
    process_id = ospf_params.get('process_id')
    if not process_id or not isinstance(process_id, int) or process_id < 1 or process_id > 65535:
        raise ValueError("OSPF process ID must be between 1 and 65535")

    # Validate area (0-4294967295)
    area = ospf_params.get('area')
    if area is None or not isinstance(area, int) or area < 0 or area > 4294967295:
        raise ValueError("OSPF area must be between 0 and 4294967295")

    # Validate IP addresses
    router1_ip = ospf_params.get('router1_ip')
    router2_ip = ospf_params.get('router2_ip')
    if not router1_ip or not router2_ip:
        raise ValueError("Both router IP addresses are required for OSPF")

    is_valid, error = validate_ip_address(router1_ip)
    if not is_valid:
        raise ValueError(f"Router 1 IP: {error}")

    is_valid, error = validate_ip_address(router2_ip)
    if not is_valid:
        raise ValueError(f"Router 2 IP: {error}")

    # Validate subnet mask
    subnet_mask = ospf_params.get('subnet_mask')
    if not subnet_mask:
        raise ValueError("Subnet mask is required for OSPF")

    try:
        # Validate it's a valid netmask
        ipaddress.IPv4Network(f"0.0.0.0/{subnet_mask}", strict=False)
    except ValueError:
        raise ValueError(f"Invalid subnet mask: {subnet_mask}")

    # Validate interface names with regex (support both full and abbreviated forms)
    interface_pattern = re.compile(
        r'^(GigabitEthernet|Gi|TenGigabitEthernet|Ten|Te|FastEthernet|Fa|FortyGigabitEthernet|FortyGigE|Fo|HundredGigE|Hu|TwentyFiveGigE|Twe|Port-channel|Po)[\d/\.]+$',
        re.IGNORECASE
    )

    router1_interface = ospf_params.get('router1_interface')
    router2_interface = ospf_params.get('router2_interface')

    if not router1_interface or not router2_interface:
        raise ValueError("Both router interface names are required for OSPF")

    if not interface_pattern.match(router1_interface):
        raise ValueError(f"Invalid interface name format: {router1_interface}")

    if not interface_pattern.match(router2_interface):
        raise ValueError(f"Invalid interface name format: {router2_interface}")

    # Validate VLAN ID for SVI/subinterface modes (1-4094)
    interface_mode = ospf_params.get('interface_mode')
    if interface_mode in ['svi', 'subinterface']:
        vlan_id = ospf_params.get('vlan_id')
        if not vlan_id or not isinstance(vlan_id, int) or vlan_id < 1 or vlan_id > 4094:
            raise ValueError(f"VLAN ID must be between 1 and 4094 for {interface_mode} mode")

    # Validate MD5 key when authentication is enabled
    if ospf_params.get('authentication') == 'md5':
        md5_key = ospf_params.get('md5_key')
        if not md5_key or not isinstance(md5_key, str) or len(md5_key) < 1:
            raise ValueError("MD5 key is required when MD5 authentication is enabled")

        md5_key_id = ospf_params.get('md5_key_id')
        if not md5_key_id or not isinstance(md5_key_id, int) or md5_key_id < 1 or md5_key_id > 255:
            raise ValueError("MD5 key ID must be between 1 and 255")

    return True, None


def build_vrf_config(vrf_params):
    """
    Build VRF configuration dictionary.

    Args:
        vrf_params: Dictionary with VRF configuration parameters
            {
                'name': 'INTERNET',
                'rd': '65000:100',
                'rt_export_enabled': True,
                'rt_export_value': '65000:100',
                'rt_import_enabled': False,
                'rt_import_value': None
            }

    Returns:
        Dictionary with validated VRF configuration
    """
    # Validate VRF name
    is_valid, error = validate_vrf_name(vrf_params.get('name'))
    if not is_valid:
        raise ValueError(f"Invalid VRF name: {error}")

    # Validate RD
    is_valid, error = validate_route_distinguisher(vrf_params.get('rd'))
    if not is_valid:
        raise ValueError(f"Invalid Route Distinguisher: {error}")

    vrf_config = {
        'name': vrf_params['name'],
        'rd': vrf_params['rd'],
        'rt_export_enabled': vrf_params.get('rt_export_enabled', False),
        'rt_import_enabled': vrf_params.get('rt_import_enabled', False)
    }

    # Validate and add RT export if enabled
    if vrf_config['rt_export_enabled']:
        rt_export = vrf_params.get('rt_export_value')
        is_valid, error = validate_route_distinguisher(rt_export)
        if not is_valid:
            raise ValueError(f"Invalid RT Export: {error}")
        vrf_config['rt_export_value'] = rt_export

    # Validate and add RT import if enabled
    if vrf_config['rt_import_enabled']:
        rt_import = vrf_params.get('rt_import_value')
        is_valid, error = validate_route_distinguisher(rt_import)
        if not is_valid:
            raise ValueError(f"Invalid RT Import: {error}")
        vrf_config['rt_import_value'] = rt_import

    return vrf_config


def build_ibgp_configs(fusion_routers, ibgp_params):
    """
    Build iBGP configuration for both fusion routers.

    Args:
        fusion_routers: List of fusion router configurations
        ibgp_params: Dict with iBGP parameters from user input
            {
                'enabled': True,
                'bfd_enabled': True,
                'bfd_interval': 250,
                'bfd_min_rx': 250,
                'bfd_multiplier': 3
            }

    Returns:
        List of iBGP configurations, one per router
    """
    if not ibgp_params or not ibgp_params.get('enabled') or len(fusion_routers) < 2:
        return []

    # Validate that both routers use the same AS
    as_numbers = [fr['as_number'] for fr in fusion_routers]
    if len(set(as_numbers)) > 1:
        raise ValueError(
            f"iBGP requires both fusion routers to use the same AS number. "
            f"Found: {', '.join(as_numbers)}"
        )

    ibgp_configs = []

    for i, router in enumerate(fusion_routers):
        # Determine peer router
        peer_router = fusion_routers[1] if i == 0 else fusion_routers[0]

        # Loopback-based iBGP (recommended and simpler)
        config = {
            'enabled': True,
            'router_id': router['router_id'],
            'peering_type': 'loopback',
            'peer_hostname': peer_router['hostname'],
            'peer_ip': peer_router['bgp_router_id'],
            'update_source': 'Loopback0',
            'bfd_enabled': ibgp_params.get('bfd_enabled', True),
            'bfd_interval': ibgp_params.get('bfd_interval', 250),
            'bfd_min_rx': ibgp_params.get('bfd_min_rx', 250),
            'bfd_multiplier': ibgp_params.get('bfd_multiplier', 3)
        }

        ibgp_configs.append(config)

    return ibgp_configs


def build_ospf_configs(fusion_routers, ospf_params):
    """
    Build OSPF underlay configuration for both fusion routers.

    Args:
        fusion_routers: List of fusion router configurations
        ospf_params: Dict with OSPF parameters from user input
            {
                'enabled': True,
                'process_id': 1,
                'area': 0,
                'interface_mode': 'physical|svi|subinterface',
                'router1_interface': 'GigabitEthernet0/0/10',
                'router1_ip': '10.255.255.0',
                'router2_interface': 'GigabitEthernet0/0/10',
                'router2_ip': '10.255.255.1',
                'subnet_mask': '255.255.255.252',
                'vlan_id': 999,  # for SVI/subinterface modes
                'cost': 100,  # optional
                'bfd_enabled': True,
                'bfd_interval': 250,
                'bfd_min_rx': 250,
                'bfd_multiplier': 3,
                'authentication': 'none|md5',
                'md5_key_id': 1,
                'md5_key': 'secret'
            }

    Returns:
        List of OSPF configurations, one per router
    """
    if not ospf_params or not ospf_params.get('enabled') or len(fusion_routers) < 2:
        return []

    # Validate OSPF parameters
    validate_ospf_params(ospf_params)

    # Calculate network address and wildcard mask
    router1_ip = ospf_params['router1_ip']
    subnet_mask = ospf_params['subnet_mask']

    # Create network from first IP and subnet mask
    network = ipaddress.IPv4Network(f"{router1_ip}/{subnet_mask}", strict=False)
    network_address = str(network.network_address)

    # Calculate wildcard mask (inverse of subnet mask)
    wildcard_mask = str(ipaddress.IPv4Address(int(ipaddress.IPv4Address('255.255.255.255')) - int(ipaddress.IPv4Address(subnet_mask))))

    # Build OSPF configs for each router
    ospf_configs = []

    for i, router in enumerate(fusion_routers):
        interface_mode = ospf_params['interface_mode']
        interface_name = ospf_params['router1_interface'] if i == 0 else ospf_params['router2_interface']
        ip_address = ospf_params['router1_ip'] if i == 0 else ospf_params['router2_ip']

        config = {
            'enabled': True,
            'router_id': router['router_id'],
            'process_id': ospf_params['process_id'],
            'area': ospf_params['area'],
            'network_address': network_address,
            'wildcard_mask': wildcard_mask,
            'interface_mode': interface_mode,
            'interface_name': interface_name,
            'ip_address': ip_address,
            'subnet_mask': subnet_mask,
            'cost': ospf_params.get('cost'),
            'bfd_enabled': ospf_params.get('bfd_enabled', True),
            'bfd_interval': ospf_params.get('bfd_interval', 250),
            'bfd_min_rx': ospf_params.get('bfd_min_rx', 250),
            'bfd_multiplier': ospf_params.get('bfd_multiplier', 3),
            'authentication': ospf_params.get('authentication', 'none'),
            'md5_key_id': ospf_params.get('md5_key_id'),
            'md5_key': ospf_params.get('md5_key')
        }

        # Add VLAN ID for SVI/subinterface modes
        if interface_mode in ['svi', 'subinterface']:
            config['vlan_id'] = ospf_params['vlan_id']

        # Add encapsulation for subinterface mode
        if interface_mode == 'subinterface':
            config['encapsulation'] = f"dot1Q {ospf_params['vlan_id']}"

        ospf_configs.append(config)

    return ospf_configs


def generate_fusion_router_config(fusion_router_params, border_nodes, handoffs, vrf_configs, ibgp_config=None, ospf_config=None):
    """
    Generate complete Cisco IOS configuration for fusion router(s).

    Args:
        fusion_router_params: Dict with fusion router parameters
            {
                'router_id': 1 or 2,
                'hostname': 'fusion-router-01',
                'bgp_router_id': '10.0.0.1',
                'as_number': '65000'
            }
        border_nodes: List of parsed border node configurations
        handoffs: List of handoff configurations
        vrf_configs: List of VRF configurations
        ibgp_config: Dict with iBGP configuration (optional)
            [
                {
                    'border_hostname': 'bn-01',
                    'border_vlan_id': '3704',
                    'fusion_router_id': 1,  # Which fusion router (1 or 2)
                    'interface_mode': 'routed|svi|subinterface',
                    'interface_name': 'GigabitEthernet0/0/1',  # For routed or parent for subinterface
                    'vlan_id': '100',  # For SVI mode
                    'subif_id': '100',  # For subinterface mode
                    'vrf_name': 'INTERNET',  # VRF on fusion router
                    'physical_interface': 'GigabitEthernet0/0/1',  # For SVI mode
                    'allowed_vlans': '100,200'  # For SVI mode (trunk config)
                }
            ]
        vrf_configs: List of VRF configurations
            [
                {
                    'name': 'INTERNET',
                    'rd': '65000:100',
                    'rt_export_enabled': True,
                    'rt_export_value': '65000:100',
                    'rt_import_enabled': True,
                    'rt_import_value': '65000:200'
                }
            ]

    Returns:
        String containing the complete Cisco IOS configuration
    """
    from jinja2 import Template

    # Filter handoffs for this specific fusion router
    router_id = fusion_router_params['router_id']
    router_handoffs = [h for h in handoffs if h['fusion_router_id'] == router_id]

    if not router_handoffs:
        # Return empty config if no handoffs for this router
        return f"! No handoffs configured for {fusion_router_params['hostname']}\n"

    # Prepare interface configurations based on mode
    interface_mode = router_handoffs[0]['interface_mode']
    interfaces_config = []
    physical_interfaces_config = []
    vlans_config = []
    bgp_neighbors_default = []
    bgp_neighbors_vrf = {}

    # Build VRF configurations
    vrf_definitions = []
    for vrf in vrf_configs:
        vrf_definitions.append(build_vrf_config(vrf))

    # Find border node info for each handoff
    for handoff in router_handoffs:
        bn_hostname = handoff['border_hostname']
        border_vlan_id = handoff['border_vlan_id']

        # Find border node config
        border_node = None
        for bn in border_nodes:
            if bn['hostname'] == bn_hostname:
                border_node = bn
                break

        if not border_node:
            continue

        # Find VLAN interface info
        vlan_info = None
        for vlan in border_node['vlan_interfaces']:
            if str(vlan['vlan']) == str(border_vlan_id):
                vlan_info = vlan
                break

        if not vlan_info:
            continue

        # Calculate fusion router IP
        fusion_ip = calculate_fusion_router_ip(vlan_info['ip_address'])
        if not fusion_ip:
            continue

        # Build interface configuration based on mode
        if interface_mode == 'routed':
            # Direct L3 interface
            interface_data = {
                'type': 'routed',
                'name': handoff['interface_name'],
                'ip_address': fusion_ip,
                'subnet_mask': vlan_info['subnet_mask'],
                'description': f"Handoff to {bn_hostname} VLAN{border_vlan_id}",
                'vrf': handoff['vrf_name'],
                'bfd_enabled': vlan_info['bfd_enabled'],
                'bfd_interval': vlan_info['bfd_interval'],
                'bfd_min_rx': vlan_info['bfd_min_rx'],
                'bfd_multiplier': vlan_info['bfd_multiplier']
            }
            interfaces_config.append(interface_data)
            source_interface = handoff['interface_name']

        elif interface_mode == 'svi':
            # SVI mode: VLAN interface + physical trunk
            vlan_id = handoff['vlan_id']

            # Add VLAN definition
            vlan_data = {
                'id': vlan_id,
                'name': f"HANDOFF_{border_vlan_id}"
            }
            vlans_config.append(vlan_data)

            # Add physical interface trunk config
            physical_if = {
                'name': handoff['physical_interface'],
                'description': f"Physical link to {bn_hostname}",
                'allowed_vlans': handoff.get('allowed_vlans', vlan_id)
            }
            # Check if physical interface already added
            if not any(p['name'] == physical_if['name'] for p in physical_interfaces_config):
                physical_interfaces_config.append(physical_if)

            # Add SVI interface
            interface_data = {
                'type': 'svi',
                'vlan_id': vlan_id,
                'ip_address': fusion_ip,
                'subnet_mask': vlan_info['subnet_mask'],
                'description': f"L3 Handoff to {bn_hostname} VLAN{border_vlan_id}",
                'vrf': handoff['vrf_name'],
                'bfd_enabled': vlan_info['bfd_enabled'],
                'bfd_interval': vlan_info['bfd_interval'],
                'bfd_min_rx': vlan_info['bfd_min_rx'],
                'bfd_multiplier': vlan_info['bfd_multiplier']
            }
            interfaces_config.append(interface_data)
            source_interface = f"Vlan{vlan_id}"

        elif interface_mode == 'subinterface':
            # Subinterface mode
            parent_if = handoff['interface_name']
            subif_id = handoff['subif_id']

            interface_data = {
                'type': 'subinterface',
                'parent_interface': parent_if,
                'subif_id': subif_id,
                'encapsulation': f"dot1Q {subif_id}",
                'ip_address': fusion_ip,
                'subnet_mask': vlan_info['subnet_mask'],
                'description': f"Subif to {bn_hostname} VLAN{border_vlan_id}",
                'vrf': handoff['vrf_name'],
                'bfd_enabled': vlan_info['bfd_enabled'],
                'bfd_interval': vlan_info['bfd_interval'],
                'bfd_min_rx': vlan_info['bfd_min_rx'],
                'bfd_multiplier': vlan_info['bfd_multiplier']
            }
            interfaces_config.append(interface_data)
            source_interface = f"{parent_if}.{subif_id}"

        # Prepare BGP neighbor configuration
        # Enable next-hop-self for eBGP neighbors when iBGP is configured
        neighbor_data = {
            'ip': vlan_info['ip_address'],  # Border node IP
            'remote_as': border_node['bgp']['as_number'],
            'source_interface': source_interface,
            'vrf': handoff['vrf_name'],
            'next_hop_self': ibgp_config and ibgp_config.get('enabled', False)
        }

        if handoff['vrf_name']:
            if handoff['vrf_name'] not in bgp_neighbors_vrf:
                bgp_neighbors_vrf[handoff['vrf_name']] = []
            bgp_neighbors_vrf[handoff['vrf_name']].append(neighbor_data)
        else:
            bgp_neighbors_default.append(neighbor_data)

    # Render configuration from template
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'fusion_router_config.j2')
    with open(template_path, 'r') as f:
        template = Template(f.read())

    config = template.render(
        hostname=fusion_router_params['hostname'],
        router_id=fusion_router_params['bgp_router_id'],
        as_number=fusion_router_params['as_number'],
        interface_mode=interface_mode,
        interfaces=interfaces_config,
        physical_interfaces=physical_interfaces_config,
        vlans=vlans_config,
        bgp_neighbors_default=bgp_neighbors_default,
        bgp_neighbors_vrf=bgp_neighbors_vrf,
        vrf_definitions=vrf_definitions,
        ibgp_config=ibgp_config,
        ospf_config=ospf_config,
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

    return config


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_configs():
    """Handle border node configuration file uploads."""
    if 'config_files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400

    files = request.files.getlist('config_files')

    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400

    parsed_configs = []

    for file in files:
        if file and allowed_file(file.filename):
            try:
                # Read and parse configuration
                config_text = file.read().decode('utf-8')
                parser = CiscoConfigParser(config_text)
                parsed_data = parser.parse()

                if not parsed_data['hostname']:
                    return jsonify({'error': f'Could not parse hostname from {file.filename}'}), 400

                parsed_configs.append(parsed_data)

            except Exception as e:
                return jsonify({'error': f'Error parsing {file.filename}: {str(e)}'}), 400
        else:
            return jsonify({'error': f'Invalid file type: {file.filename}'}), 400

    return jsonify({'configs': parsed_configs})


@app.route('/generate', methods=['POST'])
def generate_config():
    """Generate fusion router configuration(s)."""
    try:
        data = request.json

        # Validate input
        if not data.get('fusion_routers'):
            return jsonify({'error': 'Fusion router configuration is required'}), 400

        if not data.get('border_nodes'):
            return jsonify({'error': 'Border node configurations are required'}), 400

        if not data.get('handoffs'):
            return jsonify({'error': 'No handoffs configured'}), 400

        if not data.get('vrf_configs'):
            return jsonify({'error': 'VRF configurations are required'}), 400

        # Build iBGP configurations if enabled
        ibgp_configs = []
        if data.get('ibgp_params') and data['ibgp_params'].get('enabled'):
            try:
                ibgp_configs = build_ibgp_configs(
                    fusion_routers=data['fusion_routers'],
                    ibgp_params=data['ibgp_params']
                )
            except ValueError as e:
                return jsonify({'error': str(e)}), 400

        # Build OSPF configurations if enabled
        ospf_configs = []
        if data.get('ospf_params') and data['ospf_params'].get('enabled'):
            try:
                validate_ospf_params(data['ospf_params'])
                ospf_configs = build_ospf_configs(
                    fusion_routers=data['fusion_routers'],
                    ospf_params=data['ospf_params']
                )
            except ValueError as e:
                return jsonify({'error': str(e)}), 400

        # Generate configurations for each fusion router
        configs = {}
        fusion_routers = data['fusion_routers']

        for router_params in fusion_routers:
            try:
                # Find iBGP config for this router
                router_ibgp_config = None
                for ic in ibgp_configs:
                    if ic['router_id'] == router_params['router_id']:
                        router_ibgp_config = ic
                        break

                # Find OSPF config for this router
                router_ospf_config = None
                for oc in ospf_configs:
                    if oc['router_id'] == router_params['router_id']:
                        router_ospf_config = oc
                        break

                config = generate_fusion_router_config(
                    fusion_router_params=router_params,
                    border_nodes=data['border_nodes'],
                    handoffs=data['handoffs'],
                    vrf_configs=data['vrf_configs'],
                    ibgp_config=router_ibgp_config,
                    ospf_config=router_ospf_config
                )
                configs[router_params['hostname']] = config
            except Exception as e:
                return jsonify({'error': f"Error generating config for {router_params['hostname']}: {str(e)}"}), 500

        # Generate timestamp for this generation
        timestamp = generate_timestamp()

        # Save each fusion router config
        saved_files = []
        for hostname, config in configs.items():
            # Save to outputs directory
            filepath = save_config_to_file(config, hostname, timestamp)
            saved_files.append({
                'hostname': hostname,
                'filepath': filepath,
                'filename': os.path.basename(filepath)
            })

            # Log the save
            print(f"Config saved: {filepath}")

        # Create summary data
        interface_mode = data['handoffs'][0]['interface_mode'] if data['handoffs'] else 'unknown'

        # Build fusion router summary
        fusion_router_summary = []
        for idx, router_params in enumerate(fusion_routers):
            router_handoffs = [h for h in data['handoffs'] if h['fusion_router_id'] == router_params['router_id']]
            unique_vrfs = list(set([h['vrf_name'] for h in router_handoffs]))

            fusion_router_summary.append({
                'hostname': router_params['hostname'],
                'config_file': saved_files[idx]['filename'],
                'interface_mode': interface_mode,
                'handoff_count': len(router_handoffs),
                'vrfs': unique_vrfs
            })

        summary_data = {
            'timestamp': datetime.now().isoformat(),
            'border_nodes': [bn['hostname'] for bn in data['border_nodes']],
            'fusion_routers': fusion_router_summary,
            'interface_mode': interface_mode,
            'total_handoffs': len(data['handoffs'])
        }

        # Save summary
        summary_filepath = save_generation_summary(summary_data, timestamp)
        print(f"Summary saved: {summary_filepath}")

        return jsonify({
            'configs': configs,
            'saved_files': saved_files,
            'summary_file': os.path.basename(summary_filepath)
        })

    except Exception as e:
        return jsonify({'error': f'Error generating configuration: {str(e)}'}), 500


@app.route('/download', methods=['POST'])
def download_config():
    """Download generated configuration as a file."""
    try:
        data = request.json
        config = data.get('config', '')
        filename = data.get('filename', 'fusion-router-config.txt')

        # Create a file-like object
        config_bytes = io.BytesIO(config.encode('utf-8'))

        return send_file(
            config_bytes,
            mimetype='text/plain',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return jsonify({'error': f'Error downloading configuration: {str(e)}'}), 500


@app.route('/outputs', methods=['GET'])
def list_outputs():
    """List all saved configuration files."""
    try:
        outputs_dir = ensure_outputs_directory()

        files = []
        for filename in os.listdir(outputs_dir):
            if filename.endswith('.txt') or filename.endswith('.json'):
                filepath = os.path.join(outputs_dir, filename)
                files.append({
                    'filename': filename,
                    'size': os.path.getsize(filepath),
                    'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                })

        # Sort by modification time, newest first
        files.sort(key=lambda x: x['modified'], reverse=True)

        return jsonify({'files': files})

    except Exception as e:
        return jsonify({'error': f'Error listing outputs: {str(e)}'}), 500


@app.route('/outputs/<filename>', methods=['GET'])
def download_saved_config(filename):
    """Download a previously saved config."""
    try:
        outputs_dir = ensure_outputs_directory()
        filepath = os.path.join(outputs_dir, filename)

        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404

        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        return jsonify({'error': f'Error downloading saved config: {str(e)}'}), 500


@app.route('/outputs/<filename>', methods=['DELETE'])
def delete_saved_config(filename):
    """Delete a saved config file."""
    try:
        outputs_dir = ensure_outputs_directory()
        filepath = os.path.join(outputs_dir, filename)

        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404

        os.remove(filepath)
        return jsonify({'success': True, 'message': f'Deleted {filename}'})

    except Exception as e:
        return jsonify({'error': f'Error deleting config: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
