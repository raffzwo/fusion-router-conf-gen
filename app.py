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

    def parse(self):
        """Parse the configuration and return all relevant information."""
        return {
            'hostname': self.get_hostname(),
            'loopback0_ip': self.get_loopback0_ip(),
            'bgp': self.get_bgp_config(),
            'vlan_interfaces': self.get_vlan_interfaces()
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


def generate_fusion_router_config(fusion_hostname, fusion_router_id, fusion_as_number,
                                  border_nodes, selected_interfaces):
    """
    Generate complete Cisco IOS configuration for fusion router.

    Args:
        fusion_hostname: Hostname for the fusion router
        fusion_router_id: BGP router ID for the fusion router
        fusion_as_number: BGP AS number for the fusion router
        border_nodes: List of parsed border node configurations
        selected_interfaces: Dict mapping border node hostname to list of selected VLAN interfaces

    Returns:
        String containing the complete Cisco IOS configuration
    """
    from jinja2 import Template

    # Prepare interface and BGP neighbor data
    interfaces_config = []
    bgp_neighbors_default = []
    bgp_neighbors_vrf = {}

    for bn in border_nodes:
        bn_hostname = bn['hostname']
        if bn_hostname not in selected_interfaces:
            continue

        for vlan in bn['vlan_interfaces']:
            vlan_id = vlan['vlan']
            if vlan_id not in selected_interfaces[bn_hostname]:
                continue

            # Calculate fusion router IP
            fusion_ip = calculate_fusion_router_ip(vlan['ip_address'])
            if not fusion_ip:
                continue

            # Prepare interface configuration
            interface_data = {
                'vlan': vlan_id,
                'ip_address': fusion_ip,
                'subnet_mask': vlan['subnet_mask'],
                'description': f"Connection to {bn_hostname} VLAN {vlan_id}",
                'bfd_enabled': vlan['bfd_enabled'],
                'bfd_interval': vlan['bfd_interval'],
                'bfd_min_rx': vlan['bfd_min_rx'],
                'bfd_multiplier': vlan['bfd_multiplier'],
                'vrf': vlan['vrf']
            }
            interfaces_config.append(interface_data)

            # Prepare BGP neighbor configuration
            neighbor_data = {
                'ip': vlan['ip_address'],  # Border node IP
                'remote_as': bn['bgp']['as_number'],
                'source_interface': f"Vlan{vlan_id}",
                'vrf': vlan['vrf']
            }

            if vlan['vrf']:
                if vlan['vrf'] not in bgp_neighbors_vrf:
                    bgp_neighbors_vrf[vlan['vrf']] = []
                bgp_neighbors_vrf[vlan['vrf']].append(neighbor_data)
            else:
                bgp_neighbors_default.append(neighbor_data)

    # Render configuration from template
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'fusion_router_config.j2')
    with open(template_path, 'r') as f:
        template = Template(f.read())

    config = template.render(
        hostname=fusion_hostname,
        router_id=fusion_router_id,
        as_number=fusion_as_number,
        interfaces=interfaces_config,
        bgp_neighbors_default=bgp_neighbors_default,
        bgp_neighbors_vrf=bgp_neighbors_vrf,
        vrfs=list(bgp_neighbors_vrf.keys()),
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
    """Generate fusion router configuration."""
    try:
        data = request.json

        # Validate input
        if not data.get('fusion_hostname'):
            return jsonify({'error': 'Fusion router hostname is required'}), 400

        if not data.get('fusion_router_id'):
            return jsonify({'error': 'Fusion router ID is required'}), 400

        if not data.get('fusion_as_number'):
            return jsonify({'error': 'Fusion AS number is required'}), 400

        if not data.get('border_nodes'):
            return jsonify({'error': 'Border node configurations are required'}), 400

        if not data.get('selected_interfaces'):
            return jsonify({'error': 'No interfaces selected'}), 400

        # Generate configuration
        config = generate_fusion_router_config(
            fusion_hostname=data['fusion_hostname'],
            fusion_router_id=data['fusion_router_id'],
            fusion_as_number=data['fusion_as_number'],
            border_nodes=data['border_nodes'],
            selected_interfaces=data['selected_interfaces']
        )

        return jsonify({'config': config})

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
