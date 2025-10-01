# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This repository contains Cisco network device configuration files in IOS format. These are router/switch configurations, not source code for a software application.

## Configuration Files

The repository currently contains two Cisco IOS configuration files:
- `bn-institut.txt` - Configuration for device `stk-bxl-bn-institut` (Loopback0: 10.5.80.178)
- `bn-villa.txt` - Configuration for device `stk-bxl-bn-villa` (Loopback0: 10.5.80.128)

## Configuration Architecture

### Network Topology
Both devices are Cisco Catalyst switches running IOS-XE 17.12 in an SD-Access fabric deployment:

- **Fabric Role**: Both devices function as fabric border nodes with LISP-based overlay networking
- **Underlay Protocol**: IS-IS for routing between fabric nodes
- **Overlay Protocol**: LISP (Locator/ID Separation Protocol) with VXLAN encapsulation
- **Instance IDs**:
  - 4097: Global routing table (default VRF)
  - 4099: Campus_VN VRF
  - 8189, 8190: Layer 2 VNIs for VLANs 10 and 11

### VRFs (Virtual Routing and Forwarding)
- **Campus_VN** (RD 1:4099): User network traffic
- **Mgmt-vrf**: Management traffic

### External Connectivity
- **BGP AS**: 64700 (local), peering with AS 64701
- **bn-villa**: BGP neighbors at 192.168.201.134 and 192.168.201.142
- **bn-institut**: BGP neighbors at 192.168.201.150 and 192.168.201.158
- LISP routes are redistributed into BGP for external fabric access

### Key Services
- **AAA**: RADIUS-based authentication to Cisco DNA Center (10.1.136.151, 10.1.136.152)
- **LISP Map Servers**: 10.5.80.128 and 10.5.80.178 (the devices themselves)
- **Multicast RP**: Each device serves as its own RP (bn-villa: 10.5.80.129, bn-institut: 10.5.80.179)
- **Telemetry**: Model-driven telemetry streaming to DNA Center (10.1.136.141)

### Interface Configuration
- Multiple TwentyFiveGigE interfaces configured as fabric links with IS-IS, PIM, and BFD
- HundredGigE interfaces for high-speed fabric connectivity
- SVIs (Vlan interfaces) for L3 handoff to external routers and endpoint connectivity

## Working with Configurations

### Analyzing Changes
When comparing configurations:
- Focus on routing protocol changes (IS-IS, BGP, LISP)
- Check for VRF/VNI additions or modifications
- Review interface IP addressing and fabric link configurations
- Verify AAA and RADIUS server configurations
- Check LISP database mappings and locator sets

### Configuration Generation
If generating or modifying configurations:
- Maintain consistent IS-IS area addressing (49.0000.xxxx.xxxx.xxxx.00)
- Ensure LISP locator-set UUIDs are unique per device
- Verify BGP neighbor relationships match external router configurations
- Keep BFD timers consistent across fabric links (250ms intervals)
- Maintain telemetry subscriptions for DNA Center integration

### Important Considerations
- Passwords/keys are masked with "xxxxxxxx" - never generate actual secrets
- Device hostnames follow pattern: `stk-{location}-{site}`
- Domain: stk.bayern.de
- All fabric links use /31 subnets for point-to-point connections
- Certificate chains are present for secure communications (PKI)
