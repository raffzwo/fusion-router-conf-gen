# Cisco Fusion Router Configuration Generator

A Flask web application that automatically generates Cisco IOS configurations for fusion routers that establish BGP peering with SDA (Software-Defined Access) fabric border nodes.

## Overview

This tool simplifies the process of configuring fusion routers by:

1. **Parsing existing border node configurations** to extract:
   - BGP AS numbers and neighbors
   - VLAN interface configurations with /30 subnets
   - BFD (Bidirectional Forwarding Detection) settings
   - VRF (Virtual Routing and Forwarding) information

2. **Automatically calculating IP addresses** for the fusion router based on border node IPs in /30 subnets

3. **Generating complete Cisco IOS configurations** with:
   - Interface configurations (VLAN SVIs)
   - BGP peering configuration with BFD
   - VRF definitions and route-targets
   - Best practice security and management settings

## Features

- Web-based interface with step-by-step wizard
- Support for multiple border node configurations
- Automatic IP address calculation for /30 point-to-point links
- VRF-aware BGP configuration
- BFD configuration for fast failure detection
- Interface selection (choose which VLANs to configure)
- Configuration preview before download
- Clean, network-engineer-friendly output

## Requirements

- Python 3.8 or higher
- Modern web browser (Chrome, Firefox, Safari, Edge)

## Installation

1. **Clone or download this repository:**
   ```bash
   cd fusion-router-conf-gen
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Starting the Application

1. **Run the Flask application:**
   ```bash
   python app.py
   ```

2. **Open your web browser and navigate to:**
   ```
   http://localhost:5000
   ```

### Configuration Workflow

#### Step 1: Upload Border Node Configurations

- Click "Choose Files" and select one or more Cisco IOS configuration files
- Supported formats: `.txt`, `.cfg`, `.conf`
- The application will parse and extract relevant information

#### Step 2: Configure Fusion Router Parameters

Review the detected border nodes and enter:
- **Fusion Router Hostname**: The hostname for your fusion router
- **BGP Router ID**: Typically a loopback IP address (e.g., 10.0.0.1)
- **BGP AS Number**: The autonomous system number for the fusion router (e.g., 64701)

#### Step 3: Select Interfaces

- Review all detected VLAN interfaces with /30 subnets
- Select which interfaces should be configured for BGP peering
- The application automatically calculates the fusion router IP for each interface
- Interface cards show:
  - VLAN ID and description
  - VRF assignment (if applicable)
  - Border node IP address
  - Calculated fusion router IP address
  - BFD settings

#### Step 4: Generate and Download

- Preview the generated configuration
- Download the configuration file
- The filename will be `<hostname>-config.txt`

## Architecture

### File Structure

```
fusion-router-conf-gen/
├── app.py                              # Main Flask application
├── requirements.txt                    # Python dependencies
├── README.md                           # This file
├── bn-institut.txt                     # Sample border node config
├── bn-villa.txt                        # Sample border node config
└── templates/
    ├── index.html                      # Web interface
    └── fusion_router_config.j2         # Cisco config template
```

### Key Components

#### CiscoConfigParser Class

Parses Cisco IOS configuration files to extract:
- Hostname
- Loopback0 IP address
- BGP configuration (AS number, neighbors)
- VLAN interface configurations with BFD settings

**Key Methods:**
- `get_hostname()`: Extracts device hostname
- `get_loopback0_ip()`: Retrieves Loopback0 IP
- `get_bgp_config()`: Parses BGP configuration
- `get_vlan_interfaces()`: Extracts VLAN SVIs with /30 subnets
- `parse()`: Returns complete parsed configuration

#### IP Address Calculation

The `calculate_fusion_router_ip()` function automatically determines the correct IP address for the fusion router in a /30 subnet:

```python
def calculate_fusion_router_ip(border_node_ip):
    """
    For /30 subnet (4 addresses):
    - Network address (unusable)
    - First usable (typically border node)
    - Second usable (typically fusion router)
    - Broadcast (unusable)
    """
```

**Example:**
- Border Node: 192.168.201.129/30 → Fusion Router: 192.168.201.130
- Border Node: 192.168.201.154/30 → Fusion Router: 192.168.201.153

#### Configuration Generation

Uses Jinja2 templates to generate complete Cisco IOS configurations including:
- VRF definitions with route-targets
- Loopback interface for BGP router ID
- VLAN interfaces with proper IP addressing
- BGP configuration with fall-over BFD
- BFD templates
- Basic security and management settings

## API Endpoints

### POST /upload
Upload and parse border node configuration files.

**Request:**
- Content-Type: `multipart/form-data`
- Files: One or more configuration files

**Response:**
```json
{
  "configs": [
    {
      "hostname": "stk-bxl-bn-institut",
      "loopback0_ip": "10.5.80.178",
      "bgp": {
        "as_number": "64700",
        "default_vrf_neighbors": [...],
        "vrf_neighbors": {...}
      },
      "vlan_interfaces": [...]
    }
  ]
}
```

### POST /generate
Generate fusion router configuration.

**Request:**
```json
{
  "fusion_hostname": "fusion-router-01",
  "fusion_router_id": "10.0.0.1",
  "fusion_as_number": "64701",
  "border_nodes": [...],
  "selected_interfaces": {
    "stk-bxl-bn-institut": ["3704", "3705"],
    "stk-bxl-bn-villa": ["3700", "3701"]
  }
}
```

**Response:**
```json
{
  "config": "! Cisco IOS Configuration\n..."
}
```

### POST /download
Download generated configuration as a file.

**Request:**
```json
{
  "config": "! Configuration text...",
  "filename": "fusion-router-01-config.txt"
}
```

**Response:**
- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="..."`

## Configuration Template Details

The generated configuration includes:

### VRF Definitions
```cisco
vrf definition Campus_VN
 rd 1:4099
 address-family ipv4
  route-target export 1:4099
  route-target import 1:4099
 exit-address-family
```

### Interface Configuration
```cisco
interface Vlan3704
 description Connection to stk-bxl-bn-institut VLAN 3704
 vrf forwarding Campus_VN
 ip address 192.168.201.154 255.255.255.252
 no ip redirects
 no ip proxy-arp
 bfd interval 100 min_rx 100 multiplier 3
 no shutdown
```

### BGP Configuration
```cisco
router bgp 64701
 bgp router-id 10.0.0.1
 bgp log-neighbor-changes
 bgp graceful-restart
 no bgp default ipv4-unicast

 address-family ipv4 vrf Campus_VN
  neighbor 192.168.201.153 remote-as 64700
  neighbor 192.168.201.153 description Border Node - Vlan3704
  neighbor 192.168.201.153 update-source Vlan3704
  neighbor 192.168.201.153 fall-over bfd
  neighbor 192.168.201.153 activate
  neighbor 192.168.201.153 send-community both
 exit-address-family
```

## Example Workflow

Given the included sample configurations:

1. **Upload `bn-institut.txt` and `bn-villa.txt`**

2. **Application extracts:**
   - Institut: AS 64700, Loopback 10.5.80.178, 4 VLAN interfaces
   - Villa: AS 64700, Loopback 10.5.80.128, 4 VLAN interfaces

3. **Configure fusion router:**
   - Hostname: `fusion-router-bxl-01`
   - Router ID: `10.0.0.100`
   - AS Number: `64701`

4. **Select interfaces:**
   - From Institut: VLAN 3704, 3705 (Campus_VN VRF)
   - From Villa: VLAN 3700, 3701 (Campus_VN VRF)

5. **Generated config includes:**
   - 4 VLAN SVIs with calculated IPs
   - 4 BGP neighbors with BFD
   - Campus_VN VRF configuration
   - Complete router configuration ready to deploy

## Troubleshooting

### Configuration Not Parsing Correctly

- Ensure the configuration file is valid Cisco IOS format
- Check that the file includes `router bgp` and `interface Vlan` sections
- Verify the file is text-based (not binary)

### IP Address Calculation Issues

- Ensure border node VLAN interfaces use /30 subnet masks (255.255.255.252)
- Verify IP addresses are valid and properly formatted

### BFD Settings Not Detected

- Check that border node interfaces include `bfd interval` commands
- Ensure BFD configuration follows standard Cisco syntax

### Application Won't Start

```bash
# Check Python version
python --version  # Should be 3.8 or higher

# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Check for port conflicts
lsof -i :5000  # On Unix-like systems
netstat -ano | findstr :5000  # On Windows
```

## Technical Notes

### Parsing Strategy

The application uses regex and line-by-line parsing rather than libraries like ciscoconfparse to:
- Minimize dependencies
- Provide fine-grained control over parsing logic
- Handle edge cases in IOS configuration syntax
- Maintain simplicity and maintainability

### IP Address Calculation

Uses Python's `ipaddress` module for reliable IP address manipulation:
```python
import ipaddress
network = ipaddress.ip_network(f"{ip}/30", strict=False)
hosts = list(network.hosts())
```

### Security Considerations

- File uploads are limited to 5MB
- Only text-based configuration files are accepted
- Generated configurations should be reviewed before deployment
- No credentials or sensitive data are stored by the application

## Future Enhancements

Potential improvements:
- Support for additional routing protocols (OSPF, EIGRP)
- Configuration validation and syntax checking
- Support for IPv6
- Batch processing of multiple fusion routers
- Configuration templates for different deployment scenarios
- Integration with network automation tools (Ansible, Nornir)

## Contributing

Contributions are welcome! Areas for improvement:
- Enhanced error handling and validation
- Support for more complex BGP configurations
- Additional configuration templates
- Unit tests and integration tests
- Documentation improvements

## License

This project is provided as-is for educational and operational use.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review the sample configurations
3. Verify all requirements are installed
4. Check application logs for error messages

## Acknowledgments

Built with:
- Flask - Web framework
- Bootstrap 5 - UI framework
- Font Awesome - Icons
- Jinja2 - Template engine
