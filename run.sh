#!/bin/bash
# Fusion Router Configuration Generator - Startup Script

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================================${NC}"
echo -e "${BLUE}Cisco Fusion Router Configuration Generator${NC}"
echo -e "${BLUE}====================================================================${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${BLUE}Creating virtual environment...${NC}"
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to create virtual environment${NC}"
        exit 1
    fi
fi

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source venv/bin/activate

# Check if requirements are installed
if [ ! -f "venv/.installed" ]; then
    echo -e "${BLUE}Installing requirements...${NC}"
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to install requirements${NC}"
        exit 1
    fi
    touch venv/.installed
fi

# Run tests
echo ""
echo -e "${BLUE}Running tests...${NC}"
python test_parser.py
if [ $? -ne 0 ]; then
    echo -e "${RED}Tests failed!${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}====================================================================${NC}"
echo -e "${GREEN}Starting Flask application...${NC}"
echo -e "${GREEN}====================================================================${NC}"
echo ""
echo -e "Open your browser and navigate to: ${GREEN}http://localhost:5000${NC}"
echo ""
echo -e "Press ${RED}Ctrl+C${NC} to stop the server"
echo ""

# Start Flask application
python app.py
