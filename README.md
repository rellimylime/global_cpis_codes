# Global CPI Detection

Detection of Central Pivot Irrigation Systems (CPIs) in Sentinel-2 satellite images using deep learning.

## Quick Start

**For detecting CPIs across all of Africa:** See [README_AFRICA.md](README_AFRICA.md)

**For testing on sample images:** See instructions below 

## Installation Requirements

- Operating system:  Ubuntu Linux (20.04)

- Python version: python v3.7

- CUDA version: 10.1

- Dependent libraries: gdal(3.2.0) +  PyTorch(1.6.0) + MMDetection(v2.7.0) + mmcv(1.2.4) + shapely(1.7.1)

- This project is based on [MMDetection](https://github.com/open-mmlab/mmdetection). Therefore the installation is the same as original MMDetection.


  
## How to Run Detection

### 1. Extract the Model (One-time Setup)

```bash
cd model
unrar x cascade_mask_rcnn_pointrend_cbam.part1.rar
cd ..
```

This creates `model/epoch_140.pth` (symlinked as `cascade_mask_rcnn_pointrend_cbam.pth`)

### 2. Test on Sample Images

```bash
python demo.py
```

Results will be in `result/` directory.

**Note:** Sample images are GeoTIFF format with 4 bands (Red-Green-Blue-NIR).

### 3. Process Your Own Images

Place your Sentinel-2 GeoTIFF files (4 bands: R-G-B-NIR) in `imgs/` directory and run `demo.py`.

## Africa-Scale Detection

To detect CPIs across all of Africa:

**See [README_AFRICA.md](README_AFRICA.md)** for the complete workflow using Google Earth Engine.

Quick summary:
```bash
# 1. Setup Google Earth Engine
pip install earthengine-api
earthengine authenticate

# 2. Download Africa tiles
python download_africa_gee.py

# 3. Process downloaded tiles
python batch_detect_africa.py
```
 
