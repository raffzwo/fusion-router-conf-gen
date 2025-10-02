# Testing Guide for Fusion Router Configuration Generator v2.0

## Quick Start Testing

### Prerequisites
```bash
cd /Users/raffaelziagas/code/fusion-router-conf-gen
python3 app.py
```
Access at: http://localhost:5001

---

## Test Scenario 1: Basic Functionality (Zoom & Anti-Overlap)

**Objective:** Verify zoom works on all elements and connections don't overlap

**Steps:**
1. Upload `bn-institut.txt` and `bn-villa.txt`
2. Configure 1 fusion router:
   - Hostname: `test-fusion-01`
   - BGP Router ID: `10.0.0.1`
   - AS Number: `65001`
3. Select "Routed" interface mode
4. In diagram, drag 3-5 VLANs from same border node to fusion router
5. Configure interfaces (any valid interface names)
6. **Test Zoom:**
   - Use mouse wheel to zoom in/out
   - Verify both boxes AND lines scale together
   - Click zoom in/out buttons
   - Verify nodes scale proportionally
7. **Test Overlap:**
   - Look at connection lines
   - Verify 35px vertical spacing between lines
   - Verify labels don't overlap lines or each other
   - Check interface labels on both ends

**Expected Result:**
- ✅ All elements zoom together
- ✅ Lines separated with clear spacing
- ✅ Labels readable and well-positioned

---

## Test Scenario 2: Separate Router Diagrams

**Objective:** Verify each router can be viewed separately

**Steps:**
1. Upload `bn-institut.txt` and `bn-villa.txt`
2. Configure 2 fusion routers:
   - Router 1: `fusion-router-01`, `10.0.0.1`, AS `65001`
   - Router 2: `fusion-router-02`, `10.0.0.2`, AS `65001`
3. Select "Routed" interface mode
4. In Step 4 (Handoff Mapping):
   - **Verify router selector appears** (top-left of diagram)
   - Should show: "All Routers | fusion-router-01 | fusion-router-02"
5. Click "All Routers" - see all connections
6. Click "fusion-router-01":
   - Should show only router 1 and its border nodes
   - Drag VLAN from bn-institut to fusion-router-01
   - Configure interface: `GigabitEthernet0/0/1`
7. Click "fusion-router-02":
   - Should show only router 2
   - Previous connection should be hidden
   - Drag VLAN from bn-villa to fusion-router-02
   - Configure interface: `GigabitEthernet0/0/2`
8. Click "All Routers" again:
   - Should see both connections now

**Expected Result:**
- ✅ Router selector visible with 2+ routers
- ✅ Each view shows only relevant connections
- ✅ Sidebar stays same across views
- ✅ Can add connections in any view
- ✅ "All Routers" view shows everything

---

## Test Scenario 3: VRF-Aware iBGP

**Objective:** Verify iBGP can be enabled in specific VRFs

**Steps:**
1. Upload border nodes and configure 2 fusion routers (same AS!)
2. Enable iBGP in Step 2
3. In Step 4, create connections using different VRFs:
   - Connection 1: Use VRF "INTERNET"
   - Connection 2: Use VRF "GUEST"
   - Connection 3: Leave empty (global table)
4. Proceed to Step 5 (VRF Configuration)
5. **Verify iBGP VRF Selection card appears:**
   - Should show checkboxes for:
     - Global Routing Table
     - VRF: INTERNET (checked)
     - VRF: GUEST (checked)
6. **Test Case A: All VRFs + Global**
   - Check all boxes
   - Generate configuration
   - Search for "iBGP peer" in config
   - Verify iBGP neighbor in:
     - `address-family ipv4` (global)
     - `address-family ipv4 vrf INTERNET`
     - `address-family ipv4 vrf GUEST`

7. **Test Case B: INTERNET VRF Only**
   - Uncheck "Global" and "GUEST"
   - Leave only "INTERNET" checked
   - Generate configuration
   - Verify iBGP neighbor ONLY in:
     - `address-family ipv4 vrf INTERNET`
   - Should NOT appear in global or GUEST

8. **Test Case C: Global Table Only**
   - Check only "Global Routing Table"
   - Generate configuration
   - Verify iBGP neighbor only in:
     - `address-family ipv4`

**Expected Result:**
- ✅ VRF checkboxes appear in Step 5
- ✅ iBGP neighbors appear only in selected VRFs/table
- ✅ Generated config has correct address-family blocks

---

## Test Scenario 4: VRF-Aware OSPF

**Objective:** Verify OSPF can run in global table or specific VRF

**Steps:**
1. Configure 2 fusion routers (enable iBGP to show OSPF section)
2. In OSPF section (Step 2):
   - Process ID: `1`
   - Area: `0`
   - Interface Mode: Physical
   - Router 1 Interface: `GigabitEthernet0/0/10`
   - Router 1 IP: `10.255.255.0`
   - Router 2 Interface: `GigabitEthernet0/0/10`
   - Router 2 IP: `10.255.255.1`
   - Subnet: `/30`

3. Create connections with VRF "UNDERLAY"

4. In Step 5, **verify OSPF VRF Selection card:**
   - Should show radio buttons:
     - ● Global Routing Table (Recommended) - selected
     - ○ VRF: INTERNET
     - ○ VRF: GUEST
     - ○ VRF: UNDERLAY

5. **Test Case A: Global Table (default)**
   - Leave "Global Routing Table" selected
   - Generate configuration
   - Find `interface GigabitEthernet0/0/10` section
   - Should have:
     ```
     interface GigabitEthernet0/0/10
      ip address 10.255.255.0 255.255.255.252
      ip ospf 1 area 0
     ```
   - Should NOT have `vrf forwarding` command
   - Find `router ospf 1` section
   - Should NOT have `vrf UNDERLAY` command

6. **Test Case B: Specific VRF**
   - Select "VRF: UNDERLAY"
   - Generate configuration
   - Find interface section
   - Should have:
     ```
     interface GigabitEthernet0/0/10
      vrf forwarding UNDERLAY
      ip address 10.255.255.0 255.255.255.252
      ip ospf 1 area 0
     ```
   - Find OSPF process
   - Should have:
     ```
     router ospf 1
      vrf UNDERLAY
      router-id 10.0.0.1
     ```

**Expected Result:**
- ✅ OSPF VRF radio buttons appear in Step 5
- ✅ Global table = no VRF commands
- ✅ Specific VRF = vrf forwarding on interface + vrf in OSPF process
- ✅ Warning message about global table recommendation shows

---

## Test Scenario 5: All Features Combined

**Objective:** Full end-to-end test with all features

**Steps:**
1. Upload both border node configs
2. Configure 2 fusion routers (same AS)
3. Enable iBGP with BFD
4. Configure OSPF underlay (global table recommended)
5. Select interface mode: SVI
6. Switch to "fusion-router-01" view
7. Create 3 connections to router 1:
   - VLAN from bn-institut: VRF INTERNET
   - VLAN from bn-institut: VRF GUEST
   - VLAN from bn-villa: No VRF (global)
8. Switch to "fusion-router-02" view
9. Create 2 connections to router 2:
   - VLAN from bn-institut: VRF INTERNET
   - VLAN from bn-villa: VRF GUEST
10. Configure VRF parameters (RD, RT)
11. In iBGP VRF selection:
    - Check: Global Table
    - Check: INTERNET
    - Uncheck: GUEST
12. Generate both configs
13. Download and review:
    - Router 1 should have iBGP in global and INTERNET only
    - Router 2 should have iBGP in global and INTERNET only
    - Both should have OSPF in global table
    - All handoff interfaces configured correctly

**Expected Result:**
- ✅ All features work together
- ✅ No JavaScript errors
- ✅ Configs generated successfully
- ✅ Downloaded files have correct syntax
- ✅ iBGP appears only in selected VRFs
- ✅ OSPF in global table by default

---

## Regression Testing

**Test these still work after changes:**

1. **Single Router Mode**
   - Configure only 1 fusion router
   - Should NOT show router selector
   - All features should work

2. **Different Interface Modes**
   - Test Routed mode
   - Test SVI mode (with VLAN IDs)
   - Test Subinterface mode (with 802.1Q tags)

3. **BFD Configuration**
   - Enable BFD for eBGP
   - Enable BFD for iBGP
   - Enable BFD for OSPF
   - Verify all `bfd` commands in generated config

4. **OSPF Authentication**
   - Select MD5 authentication
   - Enter key ID and key string
   - Verify `ip ospf authentication` commands

5. **File Download**
   - Generate configs
   - Click download for each router
   - Verify files download with correct names
   - Check files are saved to `outputs/` directory

---

## Browser Compatibility Testing

Test in:
- ✅ Chrome/Edge (Chromium)
- ✅ Firefox
- ✅ Safari (macOS)

**Key features to verify in each browser:**
- SVG diagram rendering
- Drag and drop functionality
- Zoom and pan with mouse/trackpad
- Modal dialogs
- File upload
- File download

---

## Error Handling Testing

**Test invalid inputs:**

1. **Missing Required Fields**
   - Try to proceed without filling hostname
   - Should show alert

2. **Invalid IP Addresses**
   - Enter "999.999.999.999" as BGP Router ID
   - Should show validation error

3. **Invalid Interface Names**
   - Enter "InvalidInterface123"
   - Should show validation error with proper message

4. **Mismatched AS Numbers**
   - Configure router 1 with AS 65001
   - Configure router 2 with AS 65002
   - Enable iBGP
   - Should show error about AS mismatch

5. **No Connections**
   - Try to proceed to Step 5 without creating any connections
   - Should show alert

---

## Performance Testing

**Large Configuration:**
1. Create connections:
   - 10+ VLANs to fusion router 1
   - 10+ VLANs to fusion router 2
2. Test:
   - Diagram rendering time < 2 seconds
   - View switching instant < 500ms
   - Zoom/pan responsive
   - Configuration generation < 5 seconds

---

## Acceptance Criteria

| Feature | Status | Notes |
|---------|--------|-------|
| Zoom works on all elements | ✅ | Nodes and lines scale together |
| No overlapping connections | ✅ | 35px spacing implemented |
| No overlapping labels | ✅ | Better positioning |
| Router view selector | ✅ | Shows for 2+ routers |
| Separate router diagrams | ✅ | Filtered rendering works |
| VRF-aware iBGP UI | ✅ | Checkboxes in Step 5 |
| VRF-aware iBGP config | ✅ | Correct address-families |
| VRF-aware OSPF UI | ✅ | Radio buttons in Step 5 |
| VRF-aware OSPF config | ✅ | VRF commands when selected |
| No regressions | ✅ | All old features work |

---

## Troubleshooting

**Diagram not showing:**
- Check browser console for errors
- Verify border node configs uploaded successfully
- Ensure fusion routers configured

**Zoom not working:**
- Verify mouse is over SVG area
- Try zoom buttons instead of mouse wheel
- Check browser zoom level (should be 100%)

**VRF sections not appearing:**
- iBGP VRF selection: Only shows if iBGP enabled
- OSPF VRF selection: Only shows if iBGP enabled (OSPF depends on iBGP)
- Ensure connections use VRF names

**Configuration download fails:**
- Check browser download settings
- Verify popup blockers disabled
- Try "Download All" button

---

## Success Metrics

- ✅ All test scenarios pass
- ✅ No console errors
- ✅ Generated configs are syntactically valid
- ✅ All requested features implemented
- ✅ UI is intuitive and responsive
- ✅ Documentation is complete

**Testing Status: READY FOR ACCEPTANCE TESTING**
