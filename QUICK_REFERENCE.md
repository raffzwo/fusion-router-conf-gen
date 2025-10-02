# MP-BGP/VPNv4 Configuration - Quick Reference

## What Changed?

### 1. Single VRF Field (eBGP Requirement)
**Before:** Separate "Border Node VRF" and "Fusion Router VRF" fields
**After:** Single "VRF Name" field
**Why:** eBGP requires the same VRF on both sides

### 2. VRF Definitions (Step 5)
Configure for each VRF:
- **Route Distinguisher (RD):** Format `ASN:number` (e.g., `64800:100`)
- **Route Target Export:** Optional, format `ASN:number`
- **Route Target Import:** Optional, format `ASN:number`

### 3. MP-BGP/VPNv4 Architecture
```
Global Table:
  ├─ iBGP Peer (Loopback-based)
  └─ VPNv4 Address-Family (Route Exchange for ALL VRFs)

VRF INTERNET:
  └─ eBGP Neighbor (Border Node)

VRF MGMT:
  └─ eBGP Neighbor (Border Node)
```

## Generated Configuration Structure

```cisco
! 1. VRF Definitions
vrf definition INTERNET
 rd 64800:100
 address-family ipv4
  route-target export 64800:100
  route-target import 64800:100
 exit-address-family
!

! 2. BGP Base Config
router bgp 64800
 no bgp default ipv4-unicast
 neighbor <peer-loopback> remote-as 64800

! 3. VPNv4 Address-Family (iBGP)
 address-family vpnv4
  neighbor <peer-loopback> activate
  neighbor <peer-loopback> send-community extended
 exit-address-family

! 4. Per-VRF Address-Family (eBGP)
 address-family ipv4 vrf INTERNET
  neighbor <border-ip> remote-as 64700
  neighbor <border-ip> activate
  ! iBGP NOT here - routes via VPNv4
 exit-address-family
```

## Key Points

✅ **eBGP:** Same VRF on both sides (border + fusion)
✅ **iBGP:** Configured once in global table
✅ **VPNv4:** Automatic route exchange for all VRFs
✅ **RT Control:** Import/Export controls which routes share
✅ **Scalable:** Add VRFs without touching iBGP config

## Testing

Run validation tests:
```bash
python3 test_mpbgp_config.py        # Basic single-VRF test
python3 test_multi_vrf_config.py    # Multi-VRF scenario
```

## Files Modified

1. `templates/index.html` - UI changes for single VRF field
2. `app.py` - Backend VRF handling
3. `templates/fusion_router_config.j2` - MP-BGP/VPNv4 template

All changes validated and tested ✅
