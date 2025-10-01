# Quick Start Guide

## Installation

```bash
# 1. Navigate to project directory
cd fusion-router-conf-gen

# 2. Create virtual environment
python3 -m venv venv

# 3. Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt
```

## Running the Application

```bash
# Start the Flask server
python app.py
```

The application will start on `http://localhost:5000`

Open your web browser and navigate to: **http://localhost:5000**

## Quick Demo with Included Samples

The repository includes two sample border node configurations:
- `bn-institut.txt` (stk-bxl-bn-institut)
- `bn-villa.txt` (stk-bxl-bn-villa)

### Demo Steps:

1. **Upload** both sample files (bn-institut.txt and bn-villa.txt)

2. **Configure Fusion Router:**
   - Hostname: `fusion-router-bxl-01`
   - Router ID: `10.0.0.100`
   - AS Number: `64701`

3. **Select Interfaces:**
   - From bn-institut: All 4 VLANs (3704-3707)
   - From bn-villa: All 4 VLANs (3700-3703)

4. **Generate & Download** configuration

## Expected Output

The generated configuration will include:
- **8 VLAN interfaces** with automatically calculated IP addresses
- **8 BGP neighbors** with BFD enabled
- **VRF Campus_VN** configuration
- Complete Cisco IOS configuration ready to deploy

## Testing the Parser

```bash
# Run the test script to validate parsing
python test_parser.py
```

Expected output:
```
SUCCESS: All tests passed! ✓
```

## Troubleshooting

### Application won't start
```bash
# Check Python version (requires 3.8+)
python3 --version

# Verify dependencies are installed
pip list | grep Flask
```

### Browser can't connect
- Ensure the application is running (check terminal for "Running on http://0.0.0.0:5000")
- Try accessing via `http://127.0.0.1:5000` or `http://localhost:5000`
- Check if port 5000 is available: `lsof -i :5000`

### File upload fails
- Verify file is in supported format (.txt, .cfg, .conf)
- Check file size is under 5MB
- Ensure file contains valid Cisco IOS configuration

## Next Steps

- Review the [README.md](README.md) for detailed documentation
- Customize the configuration template in `templates/fusion_router_config.j2`
- Modify `app.py` to add additional parsing logic or validation

## Support

For issues or questions, refer to:
- README.md - Full documentation
- app.py comments - Code documentation
- test_parser.py - Parser validation examples
