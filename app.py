#!/usr/bin/env python3
"""
Cisco Fusion Router Configuration Generator
Flask web application for generating BGP/BFD configurations for fusion routers
that peer with SDA fabric border nodes.
"""

import os
import re
import ipaddress
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


def generate_fusion_router_config(fusion_router_params, border_nodes, handoffs, vrf_configs):
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
        neighbor_data = {
            'ip': vlan_info['ip_address'],  # Border node IP
            'remote_as': border_node['bgp']['as_number'],
            'source_interface': source_interface,
            'vrf': handoff['vrf_name']
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

        # Generate configurations for each fusion router
        configs = {}
        fusion_routers = data['fusion_routers']

        for router_params in fusion_routers:
            try:
                config = generate_fusion_router_config(
                    fusion_router_params=router_params,
                    border_nodes=data['border_nodes'],
                    handoffs=data['handoffs'],
                    vrf_configs=data['vrf_configs']
                )
                configs[router_params['hostname']] = config
            except Exception as e:
                return jsonify({'error': f"Error generating config for {router_params['hostname']}: {str(e)}"}), 500

        return jsonify({'configs': configs})

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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
