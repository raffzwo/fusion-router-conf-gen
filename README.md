# Cisco Fusion Router Configuration Generator

A production-ready web application for generating BGP/BFD configurations for fusion routers that peer with Cisco SDA (Software-Defined Access) fabric border nodes.

## Features

### Core Capabilities
- **Multi-Fusion Router Support**: Configure single or dual fusion routers (redundant pairs)
- **Flexible Interface Modes**:
  - Routed interfaces (direct L3 on physical ports)
  - SVI mode (L3 on VLANs, L2 trunks on physical)
  - Subinterface mode (802.1Q for WAN handoffs)
- **Advanced VRF Management**:
  - Automatic VRF detection from border nodes
  - Custom VRF mapping (global table → named VRF)
  - Configurable Route Distinguisher (RD)
  - Optional Route Target Import/Export
- **Border Node Configuration Parsing**:
  - Automatic extraction of VLAN interfaces, IP addresses, BFD parameters
  - Physical interface discovery
  - VRF status detection (global vs VRF routing table)
- **BGP Configuration Generation**:
  - IPv4 unicast address families
  - VRF-aware BGP neighbors
  - BFD integration for fast failover
  - Community propagation

### Enhanced Features (Version 2.0)

#### 1. VRF Handling for Non-VRF Border Node Traffic
When border nodes have interfaces in the global routing table but fusion routers require VRFs:
- User specifies VRF name for fusion router
- Application creates VRF on fusion router even though border uses global table
- Supports mapping: Border Node (Global) → Fusion Router (Named VRF)

#### 2. Multi-Fusion Router Support
Deploy redundant fusion router pairs:
- Configure up to 2 fusion routers
- Link specific border node VLANs to specific fusion routers
- Generate separate configuration files for each router
- Example:
  - Border Node 1 VLAN 3704 → Fusion Router 1
  - Border Node 1 VLAN 3705 → Fusion Router 2
  - Border Node 2 VLAN 3700 → Fusion Router 1

#### 3. Physical Interface Configuration (SVI Support)
For deployments using switched virtual interfaces:
- Extract physical interface configs from border nodes
- User assigns physical interfaces on fusion router
- Generates trunk configuration with allowed VLANs
- L3 configuration on SVI interfaces

#### 4. Subinterface Support (802.1Q)
For WAN/carrier handoffs using subinterfaces:
- Configure parent interface
- Auto-generate subinterface IDs from VLAN tags
- 802.1Q encapsulation configuration

#### 5. VRF Route Distinguisher & Route Target Control
Full control over VRF routing parameters:
- Custom Route Distinguisher (RD) in ASN:NN or IP:NN format
- Optional Route Target Export
- Optional Route Target Import
- Per-VRF configuration

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Setup

1. Clone or download this repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and navigate to:
```
http://localhost:5001
```

## Usage Guide

### Step-by-Step Workflow

#### Step 1: Upload Border Node Configurations
1. Click "Choose Files" and select one or more border node configuration files
2. Supported formats: `.txt`, `.cfg`, `.conf`
3. Click "Upload and Parse Configurations"
4. The application will automatically extract:
   - Hostname, Loopback0 IP, BGP AS number
   - VLAN interfaces with /30 subnets and BFD
   - VRF assignments
   - Physical interface configurations

#### Step 2: Fusion Router Setup
1. **Select Number of Fusion Routers**:
   - Single Fusion Router: Standalone deployment
   - Dual Fusion Routers: Redundant pair for high availability

2. **Configure Each Fusion Router**:
   - Hostname (e.g., `fusion-router-01`)
   - BGP Router ID (typically a loopback IP)
   - BGP AS Number

#### Step 3: Interface Mode Selection
Choose the interface configuration mode:

**Routed Interfaces**:
- Direct L3 configuration on physical interfaces
- Best for: Point-to-point connections, simple topologies
- Example: `GigabitEthernet0/0/1` with IP directly configured

**SVI Mode**:
- L3 on VLAN interfaces, L2 trunk on physical ports
- Best for: Multiple VLANs per physical link, flexible VLAN management
- Requires: Physical interface specification, VLAN ID assignment

**Subinterface Mode**:
- 802.1Q subinterfaces on parent interfaces
- Best for: WAN provider handoffs, MPLS circuits
- Example: `GigabitEthernet0/0/1.100` with dot1Q encapsulation

#### Step 4: Handoff Mapping Configuration
Configure each border node → fusion router handoff:

1. **Enable/Disable**: Select which handoffs to configure
2. **Border Node Info**: Automatically populated from parsed configs
3. **Border VRF Status**: Shows if border interface is in global table or VRF
4. **Fusion Router Selection**: Assign handoff to FR1 or FR2
5. **Fusion VRF Name**:
   - **REQUIRED** if border node interface is in global table
   - Optional (defaults to border VRF) if border already has VRF
   - Example VRF names: `INTERNET`, `WAN`, `EXTERNAL`

6. **Interface Configuration** (mode-specific):
   - **Routed Mode**: Specify fusion interface (e.g., `GigabitEthernet0/0/1`)
   - **SVI Mode**:
     - Fusion VLAN ID (e.g., `100`)
     - Physical interface (e.g., `GigabitEthernet0/0/1`)
   - **Subinterface Mode**:
     - Parent interface (e.g., `GigabitEthernet0/0/1`)
     - Subinterface ID (defaults to border VLAN ID)

7. **IP Addresses**: Automatically calculated from border node IPs

#### Step 5: VRF Configuration
For each unique VRF identified in Step 4:

1. **Route Distinguisher (RD)** - REQUIRED
   - Format: `ASN:NN` (e.g., `65000:100`)
   - Or: `IP:NN` (e.g., `10.0.0.1:100`)

2. **Route Target Export** - OPTIONAL
   - Enable checkbox to activate
   - Specify RT value (e.g., `65000:100`)

3. **Route Target Import** - OPTIONAL
   - Enable checkbox to activate
   - Specify RT value (e.g., `65000:200`)

#### Step 6: Generate and Download
1. Review generated configurations in tabbed interface
2. Download individual router configs or all at once
3. Configurations include:
   - VRF definitions with RD/RT
   - Interface configurations (routed/SVI/subinterface)
   - BGP configuration with VRF address families
   - BFD templates
   - Management and security baseline

## Configuration Examples

### Example 1: Dual Fusion Routers with SVI Mode

**Scenario**:
- 2 border nodes with multiple handoffs
- 2 fusion routers for redundancy
- SVI mode for VLAN flexibility
- Border nodes in Campus_VN VRF

**Configuration**:
- Upload: `bn-institut.txt`, `bn-villa.txt`
- Fusion Routers:
  - FR1: `fusion-bxl-01`, `10.0.0.1`, AS `64701`
  - FR2: `fusion-bxl-02`, `10.0.0.2`, AS `64702`
- Interface Mode: SVI
- Handoff Mapping:
  - BN-Institut VLAN3704 → FR1, VLAN100, Gi0/0/1
  - BN-Institut VLAN3705 → FR2, VLAN100, Gi0/0/1
  - BN-Villa VLAN3700 → FR1, VLAN101, Gi0/0/2
  - BN-Villa VLAN3701 → FR2, VLAN101, Gi0/0/2
- VRF Config:
  - VRF: `Campus_VN`
  - RD: `64700:100`
  - RT Export: `64700:100`
  - RT Import: `64700:100`

**Generated Output**:
```
vlan 100
 name HANDOFF_3704
!
interface GigabitEthernet0/0/1
 description Physical link to BN-Institut
 switchport mode trunk
 switchport trunk allowed vlan 100
 no shutdown
!
interface Vlan100
 description L3 Handoff to BN-Institut VLAN3704
 vrf forwarding Campus_VN
 ip address 192.168.201.154 255.255.255.252
 bfd interval 100 min_rx 100 multiplier 3
!
```

### Example 2: Single Router, Subinterface Mode, Global Table Mapping

**Scenario**:
- Border node has interface in global routing table (no VRF)
- Fusion router requires all traffic in named VRF
- WAN provider requires 802.1Q subinterfaces

**Configuration**:
- Interface Mode: Subinterface
- Handoff Mapping:
  - Border VRF Status: "Global Table" (no VRF)
  - Fusion VRF Name: `INTERNET` (user-specified)
  - Parent Interface: `GigabitEthernet0/0/1`
  - Subinterface ID: `3704`
- VRF Config:
  - VRF: `INTERNET`
  - RD: `65000:1`
  - RT Export: Disabled
  - RT Import: Disabled

**Generated Output**:
```
vrf definition INTERNET
 rd 65000:1
 !
 address-family ipv4
 exit-address-family
!
interface GigabitEthernet0/0/1.3704
 description Subif to BN VLAN3704
 encapsulation dot1Q 3704
 vrf forwarding INTERNET
 ip address 192.168.201.154 255.255.255.252
 bfd interval 100 min_rx 100 multiplier 3
!
```

### Example 3: Routed Mode with Mixed VRF Status

**Scenario**:
- Some border interfaces in Campus_VN VRF
- Some border interfaces in global table
- Fusion router consolidates all into named VRFs

**Configuration**:
- Interface Mode: Routed
- Handoff Mapping:
  ```
  Border VLAN 3704 (Campus_VN) → FR1, Campus_VN, Gi0/0/1
  Border VLAN 3705 (Global)    → FR1, INTERNET, Gi0/0/2
  Border VLAN 3706 (Campus_VN) → FR1, Campus_VN, Gi0/0/3
  ```
- VRF Configs:
  - Campus_VN: RD `1:4099`, RT Export/Import `1:4099`
  - INTERNET: RD `65000:100`, No RT

## Validation and Error Handling

### Input Validation

**VRF Names**:
- Maximum 32 characters
- Alphanumeric, underscores, and hyphens only
- Cannot be empty if border interface is in global table

**Route Distinguisher**:
- Must match format: `ASN:NN` or `IP:NN`
- ASN must be ≤ 4,294,967,295
- NN must be ≤ 65,535
- IP must be valid IPv4 address

**IP Addresses**:
- Must be valid IPv4 format
- Fusion IP automatically calculated from border IP

**Interface Names**:
- Required based on selected mode
- Standard Cisco interface naming (e.g., `GigabitEthernet0/0/1`)

### Production Deployment Checklist

Before deploying generated configurations:

1. **Review Generated Config**:
   - Verify all interface assignments
   - Check VRF names match your network design
   - Confirm BGP AS numbers
   - Validate IP addressing

2. **Test in Lab**:
   - Deploy to lab environment first
   - Test BGP neighbor establishment
   - Verify BFD sessions
   - Validate routing table

3. **Backup Existing Configs**:
   - Save running-config before changes
   - Document rollback procedure

4. **Deploy During Maintenance Window**:
   - BGP changes may cause brief traffic disruption
   - Plan for convergence time

5. **Post-Deployment Verification**:
   ```
   show ip bgp summary
   show ip bgp vrf <vrf-name> summary
   show bfd neighbors
   show ip route vrf <vrf-name>
   show ip interface brief
   ```

## Troubleshooting

### Common Issues

**Issue**: Border node config not parsing correctly
- **Solution**: Ensure config file has line numbers in format `NNN |content`
- Check file encoding is UTF-8
- Verify VLAN interfaces have /30 subnets (255.255.255.252)

**Issue**: VRF name required error
- **Solution**: Border interface is in global table, must specify VRF for fusion router
- Enter a VRF name like "INTERNET" or "WAN"

**Issue**: Generated config missing interfaces
- **Solution**: Check handoff is enabled (checkbox selected)
- Verify interface fields are filled correctly
- Check fusion router assignment

**Issue**: BGP neighbors not establishing
- **Verify**: IP connectivity between border and fusion router
- Check: VRF configuration matches on both sides
- Confirm: BGP AS numbers are correct
- Validate: BFD is configured on both ends

## Output Files

Generated configurations are automatically saved to the `outputs/` directory with timestamped filenames.

### File Naming Convention

- **Config files**: `{hostname}-config-{timestamp}.txt`
- **Summary files**: `generation-summary-{timestamp}.json`

### Example

```
outputs/
├── fr-bxl-01-config-20251001-143052.txt
├── fr-bxl-02-config-20251001-143052.txt
└── generation-summary-20251001-143052.json
```

### Automatic Saving

When you generate configurations through the web interface:
1. Each fusion router config is automatically saved to `outputs/`
2. A generation summary JSON file is created with metadata
3. The UI displays which files were saved
4. Files are timestamped to prevent overwrites

### Generation Summary Format

The JSON summary file contains:
```json
{
  "timestamp": "2025-10-01T14:30:52",
  "border_nodes": ["stk-bxl-bn-institut", "stk-bxl-bn-villa"],
  "fusion_routers": [
    {
      "hostname": "fr-bxl-01",
      "config_file": "fr-bxl-01-config-20251001-143052.txt",
      "interface_mode": "svi",
      "handoff_count": 4,
      "vrfs": ["INTERNET", "Campus_VN"]
    }
  ],
  "interface_mode": "svi",
  "total_handoffs": 8
}
```

### Managing Output Files

**List saved configs**:
```bash
curl http://localhost:5001/outputs
```

**Download saved config**:
```bash
curl http://localhost:5001/outputs/fr-bxl-01-config-20251001-143052.txt -O
```

**Delete saved config**:
```bash
curl -X DELETE http://localhost:5001/outputs/fr-bxl-01-config-20251001-143052.txt
```

### Cleanup

To clean up old output files:

```bash
# Remove all output files
rm outputs/*.txt outputs/*.json

# Remove outputs older than 30 days
find outputs -name "*.txt" -mtime +30 -delete
find outputs -name "*.json" -mtime +30 -delete
```

## API Reference

### Upload Endpoint
```
POST /upload
Content-Type: multipart/form-data

Parameters:
- config_files: One or more configuration files

Response:
{
  "configs": [
    {
      "hostname": "border-node-01",
      "loopback0_ip": "10.1.1.1",
      "bgp": { "as_number": "65001", ... },
      "vlan_interfaces": [...],
      "physical_interfaces": [...]
    }
  ]
}
```

### Generate Endpoint
```
POST /generate
Content-Type: application/json

Body:
{
  "fusion_routers": [
    {
      "router_id": 1,
      "hostname": "fusion-01",
      "bgp_router_id": "10.0.0.1",
      "as_number": "64701"
    }
  ],
  "border_nodes": [...],
  "handoffs": [
    {
      "border_hostname": "bn-01",
      "border_vlan_id": "3704",
      "fusion_router_id": 1,
      "interface_mode": "routed",
      "interface_name": "GigabitEthernet0/0/1",
      "vrf_name": "Campus_VN"
    }
  ],
  "vrf_configs": [
    {
      "name": "Campus_VN",
      "rd": "1:4099",
      "rt_export_enabled": true,
      "rt_export_value": "1:4099",
      "rt_import_enabled": true,
      "rt_import_value": "1:4099"
    }
  ]
}

Response:
{
  "configs": {
    "fusion-01": "! Configuration content...",
    "fusion-02": "! Configuration content..."
  },
  "saved_files": [
    {
      "hostname": "fusion-01",
      "filepath": "/path/to/outputs/fusion-01-config-20251001-143052.txt",
      "filename": "fusion-01-config-20251001-143052.txt"
    }
  ],
  "summary_file": "generation-summary-20251001-143052.json"
}
```

### List Outputs Endpoint
```
GET /outputs

Response:
{
  "files": [
    {
      "filename": "fr-bxl-01-config-20251001-143052.txt",
      "size": 4523,
      "modified": "2025-10-01T14:30:52"
    }
  ]
}
```

### Download Saved Config Endpoint
```
GET /outputs/<filename>

Response: File download
```

### Delete Saved Config Endpoint
```
DELETE /outputs/<filename>

Response:
{
  "success": true,
  "message": "Deleted fr-bxl-01-config-20251001-143052.txt"
}
```

### Download Endpoint
```
POST /download
Content-Type: application/json

Body:
{
  "config": "! Configuration content...",
  "filename": "fusion-router-config.txt"
}

Response: File download
```

## Architecture

### Backend (app.py)
- **Flask Framework**: Web server and routing
- **CiscoConfigParser**: Parses Cisco IOS configurations
  - Extracts hostnames, IPs, BGP configs
  - Identifies VLAN interfaces with /30 subnets
  - Detects VRF assignments
  - Discovers physical interfaces
- **Validation Functions**: Input validation (VRF names, RD format, IPs)
- **Config Generator**: Builds complete router configurations
- **Jinja2 Templates**: Template rendering for configs

### Frontend (index.html)
- **Bootstrap 5**: Responsive UI framework
- **6-Step Wizard**: Guided configuration workflow
- **Real-time Validation**: Client-side input validation
- **Dynamic Tables**: Handoff mapping with mode-specific fields
- **Tabbed Preview**: Multi-router config display

### Configuration Template (fusion_router_config.j2)
- **Conditional Rendering**: Adapts to interface mode
- **VRF Definitions**: Dynamic VRF blocks with RT
- **Interface Configs**: Routed/SVI/Subinterface sections
- **BGP Configuration**: VRF-aware neighbors
- **BFD Templates**: Fast failover configuration

## File Structure

```
fusion-router-conf-gen/
├── app.py                          # Flask application & backend logic
├── requirements.txt                # Python dependencies
├── templates/
│   ├── index.html                  # Frontend UI
│   └── fusion_router_config.j2     # Cisco config template
├── outputs/                        # Auto-generated configs (gitignored)
│   ├── .gitkeep                    # Keep directory in git
│   ├── *-config-*.txt              # Generated router configs
│   └── generation-summary-*.json   # Generation metadata
├── bn-institut.txt                 # Sample border node config
├── bn-villa.txt                    # Sample border node config
└── README.md                       # This file
```

## Technology Stack

- **Backend**: Python 3.8+, Flask 3.0
- **Templating**: Jinja2 3.1
- **Frontend**: HTML5, JavaScript (ES6), Bootstrap 5.3
- **Icons**: Font Awesome 6.4
- **Networking Libraries**: Python ipaddress (standard library)

## Security Considerations

### Production Deployment
1. **Authentication**: Add authentication layer (not included in base version)
2. **HTTPS**: Deploy behind reverse proxy with TLS
3. **Input Sanitization**: All inputs are validated server-side
4. **File Size Limits**: 5MB max file upload
5. **CORS**: Configure appropriately for your environment
6. **Secrets Management**: Generated configs may contain sensitive data
   - Use secure channels for distribution
   - Implement access controls
   - Audit configuration downloads

## Performance

- **File Parsing**: < 1 second for typical border node configs (50KB)
- **Config Generation**: < 500ms for dual router setup
- **Concurrent Users**: Handles 10+ simultaneous sessions
- **Browser Compatibility**: Chrome, Firefox, Safari, Edge (latest versions)

## Contributing

To extend this application:

1. **Add New Interface Modes**: Extend `generate_fusion_router_config()` and template
2. **Support Additional Vendors**: Create new parser classes
3. **Enhanced Validation**: Add to validation functions in `app.py`
4. **UI Improvements**: Modify `index.html` templates
5. **API Extensions**: Add new Flask routes as needed

## License

This project is provided as-is for network automation purposes. Modify and distribute according to your organization's policies.

## Support

For issues, questions, or feature requests:
1. Review this README thoroughly
2. Check the Troubleshooting section
3. Verify input data format matches examples
4. Test with provided sample configs (`bn-institut.txt`, `bn-villa.txt`)

## Version History

### Version 2.1 (Current - 2025-10-01)
- **Automatic file generation to outputs/ directory**
- **Timestamped filenames to prevent overwrites**
- **Generation summary JSON with metadata**
- **API endpoints for listing/downloading/deleting saved configs**
- UI notifications showing saved files
- Multi-fusion router support (up to 2 routers)
- Interface mode selection (Routed/SVI/Subinterface)
- Advanced VRF configuration (RD/RT control)
- Global table → VRF mapping
- Physical interface extraction
- Enhanced validation
- Tabbed configuration preview
- 6-step wizard workflow

### Version 2.0
- Multi-fusion router support (up to 2 routers)
- Interface mode selection (Routed/SVI/Subinterface)
- Advanced VRF configuration (RD/RT control)
- Global table → VRF mapping
- Physical interface extraction
- Enhanced validation
- Tabbed configuration preview
- 6-step wizard workflow

### Version 1.0
- Single fusion router support
- Basic VLAN interface handoffs
- Simple VRF mapping
- BGP/BFD configuration
- File upload and parsing

## Acknowledgments

Built for Cisco SDA fabric deployments requiring fusion router integration with border nodes. Designed to simplify the complex task of coordinating VRF, BGP, and BFD configurations across multiple network devices.
