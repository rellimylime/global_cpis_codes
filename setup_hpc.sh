#!/bin/bash
# Setup script for CPI Detection on HPC
# Run this after transferring files to HPC

set -e  # Exit on error

echo "=========================================="
echo "CPI Detection HPC Setup"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}➜ $1${NC}"
}

# Check if we're on HPC
print_info "Checking environment..."

# Step 1: Load modules
print_info "Step 1: Loading HPC modules..."
echo "Available modules:"
module avail 2>&1 | grep -E "(python|cuda|gdal|anaconda)" || echo "  (Use 'module avail' to see all)"

echo ""
echo "Recommended modules to load:"
echo "  module load python/3.7"
echo "  module load cuda/10.1"
echo "  module load gdal"
echo ""
read -p "Load modules automatically? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Try to load common module names
    module load python/3.7 2>/dev/null || module load python 2>/dev/null || print_error "Could not load python module"
    module load cuda/10.1 2>/dev/null || module load cuda 2>/dev/null || print_error "Could not load cuda module"
    module load gdal 2>/dev/null || print_info "GDAL module not loaded (may not be available)"
    print_success "Modules loaded"
fi

# Step 2: Create virtual environment
print_info "Step 2: Creating virtual environment..."
ENV_PATH="${HOME}/envs/cpi_detection"

if [ -d "$ENV_PATH" ]; then
    print_info "Environment already exists at $ENV_PATH"
    read -p "Remove and recreate? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$ENV_PATH"
        print_success "Removed old environment"
    else
        print_info "Skipping environment creation"
        exit 0
    fi
fi

# Check if conda is available
if command -v conda &> /dev/null; then
    print_info "Conda detected - creating conda environment..."

    if [ -f "environment.yml" ]; then
        conda env create -f environment.yml -n cpi_detection
        print_success "Conda environment created"
        echo "Activate with: conda activate cpi_detection"
    else
        print_info "No environment.yml found - creating from scratch"
        conda create -n cpi_detection python=3.7 -y
        conda activate cpi_detection
        print_success "Conda environment created"
    fi
else
    print_info "Creating Python virtual environment..."
    python -m venv "$ENV_PATH"
    source "$ENV_PATH/bin/activate"
    print_success "Virtual environment created"

    # Step 3: Install packages
    print_info "Step 3: Installing packages..."

    # Upgrade pip
    pip install --upgrade pip

    # Install PyTorch with CUDA 10.1
    print_info "Installing PyTorch 1.6.0 with CUDA 10.1..."
    pip install torch==1.6.0+cu101 torchvision==0.7.0+cu101 -f https://download.pytorch.org/whl/torch_stable.html
    print_success "PyTorch installed"

    # Install MMCV
    print_info "Installing MMCV 1.2.4..."
    pip install mmcv-full==1.2.4 -f https://download.openmmlab.com/mmcv/dist/cu101/torch1.6.0/index.html
    print_success "MMCV installed"

    # Install MMDetection
    print_info "Installing MMDetection 2.7.0..."
    pip install mmdet==2.7.0
    print_success "MMDetection installed"

    # Install other requirements
    if [ -f "requirements.txt" ]; then
        print_info "Installing other requirements..."
        pip install -r requirements.txt
        print_success "Requirements installed"
    fi
fi

# Step 4: Authenticate Earth Engine
print_info "Step 4: Google Earth Engine authentication..."
echo ""
echo "You need to authenticate Earth Engine to export tiles."
read -p "Authenticate now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    earthengine authenticate
fi

# Step 5: Setup rclone
print_info "Step 5: rclone setup (for Google Drive downloads)..."
echo ""
echo "rclone lets you download tiles from Google Drive to HPC."
read -p "Configure rclone now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if ! command -v rclone &> /dev/null; then
        print_info "Installing rclone..."
        curl https://rclone.org/install.sh | sudo bash || {
            print_error "Could not install rclone (needs sudo). Install manually."
        }
    fi
    rclone config
fi

# Step 6: Configure paths
print_info "Step 6: Configuring HPC paths..."
echo ""
echo "Edit hpc_config.py to set your storage paths:"
echo "  TILE_STORAGE = '/scratch/your_username/africa_tiles'"
echo "  RESULT_STORAGE = '/scratch/your_username/cpi_results'"
echo ""
python hpc_config.py

# Step 7: Extract model
print_info "Step 7: Extracting model files..."
if [ -f "model/cascade_mask_rcnn_pointrend_cbam.part1.rar" ]; then
    cd model
    if [ ! -f "epoch_140.pth" ]; then
        unrar x cascade_mask_rcnn_pointrend_cbam.part1.rar
        ln -s epoch_140.pth cascade_mask_rcnn_pointrend_cbam.pth
        print_success "Model extracted"
    else
        print_info "Model already extracted"
    fi
    cd ..
else
    print_error "Model files not found - make sure you transferred the model/ directory"
fi

# Step 8: Test installation
print_info "Step 8: Testing installation..."
python test_environment.py 2>/dev/null || {
    print_info "Running basic import tests..."
    python -c "import torch; print(f'PyTorch: {torch.__version__}')" || print_error "PyTorch import failed"
    python -c "import mmdet; print(f'MMDetection: {mmdet.__version__}')" || print_error "MMDetection import failed"
    python -c "import ee; print('Earth Engine: OK')" || print_error "Earth Engine import failed"
}

# Step 9: Create activation script
print_info "Step 9: Creating activation script..."
cat > ~/load_cpi_env.sh << 'EOF'
#!/bin/bash
# Load CPI Detection environment

# Load modules (adjust for your HPC)
module load python/3.7 2>/dev/null || true
module load cuda/10.1 2>/dev/null || true
module load gdal 2>/dev/null || true

# Activate environment
if command -v conda &> /dev/null && conda env list | grep -q cpi_detection; then
    conda activate cpi_detection
elif [ -d "$HOME/envs/cpi_detection" ]; then
    source "$HOME/envs/cpi_detection/bin/activate"
else
    echo "Error: CPI detection environment not found"
    exit 1
fi

echo "✓ CPI Detection environment loaded"
python --version
EOF

chmod +x ~/load_cpi_env.sh
print_success "Activation script created: ~/load_cpi_env.sh"

# Done!
echo ""
echo "=========================================="
print_success "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Activate environment:"
echo "   source ~/load_cpi_env.sh"
echo ""
echo "2. Test on sample images:"
echo "   python demo.py"
echo ""
echo "3. Export tiles from GEE:"
echo "   python download_africa_gee.py"
echo ""
echo "4. Download and process tiles:"
echo "   rclone sync gdrive:Africa_CPI_Sentinel2 /scratch/username/africa_tiles/"
echo "   python batch_detect_africa.py"
echo ""
echo "See HPC_SETUP.md for detailed documentation"
